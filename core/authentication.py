"""
Authentication and token management for the trading bot.
Extracted from trading_bot.py for better code organization.
"""
import logging
import os
import re
import time
import datetime
from typing import Optional
from kiteconnect import KiteConnect, exceptions


_ENV_VAR_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")


def _substitute_env(value):
    """Recursively replace ${VAR} placeholders with values from os.environ."""
    if isinstance(value, str):
        def repl(match):
            return os.environ.get(match.group(1), match.group(0))
        return _ENV_VAR_PATTERN.sub(repl, value)
    if isinstance(value, dict):
        return {k: _substitute_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_env(v) for v in value]
    return value


def load_config():
    """Loads config.yaml and substitutes ${VAR} placeholders from the environment."""
    import yaml
    with open('config.yaml', 'r') as file:
        raw = yaml.safe_load(file)
    return _substitute_env(raw)


def persist_access_token(token: str, env_path: str = '.env'):
    """Persists the daily Zerodha access token to .env (not config.yaml)."""
    lines = []
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            lines = f.readlines()
    found = False
    for i, line in enumerate(lines):
        if line.startswith('ZERODHA_ACCESS_TOKEN='):
            lines[i] = f'ZERODHA_ACCESS_TOKEN={token}\n'
            found = True
            break
    if not found:
        lines.append(f'ZERODHA_ACCESS_TOKEN={token}\n')
    with open(env_path, 'w') as f:
        f.writelines(lines)
    os.chmod(env_path, 0o600)  # owner-only: .env holds live credentials
    os.environ['ZERODHA_ACCESS_TOKEN'] = token


class AuthenticationManager:
    """Handles Kite Connect authentication and token management."""
    
    def __init__(self, config):
        self.config = config
        # debug=True logs full HTTP requests/responses (token-bearing URLs) —
        # never in normal runs. Opt in explicitly with KITE_DEBUG=1 when needed.
        self.kite = KiteConnect(
            api_key=config['zerodha']['api_key'], 
            timeout=120,
            debug=bool(os.environ.get('KITE_DEBUG'))
        )
        
    def authenticate(self, request_token_override=None, is_headless=False, 
                     await_phone_login_callback=None):
        """
        Handles authentication three ways:
          1. request_token_override — API-driven flows.
          2. Headless (server) mode — reuse a still-valid token from .env, else
             wait for the phone login via the dashboard callback.
          3. Console mode — print the login URL and prompt for request_token.
        """
        logging.info("Attempting authentication...")
        
        if not request_token_override and is_headless:
            # Fast path: a token from earlier today may still be valid (.env).
            existing = (os.environ.get('ZERODHA_ACCESS_TOKEN')
                        or (self.config.get('zerodha') or {}).get('access_token') or '').strip()
            if existing and self._adopt_access_token(existing):
                return True
            if await_phone_login_callback:
                tok = await_phone_login_callback()
                return bool(tok and self._adopt_access_token(tok))
            return False

        if not request_token_override:
            # Print (don't log) the login URL: it carries the api_key as a query
            # param, and log files shouldn't accumulate credential-bearing URLs.
            print(f"\nLogin URL: {self.kite.login_url()}")
            logging.info("Login URL printed to terminal (not logged — contains api_key).")
            request_token = input("Enter request_token: ")
        else:
            request_token = request_token_override

        try:
            data = self.kite.generate_session(
                request_token, 
                api_secret=self.config['zerodha']['api_secret']
            )
            return self._adopt_access_token(data['access_token'])
        except Exception as e:
            logging.error(f"Authentication failed: {e}", exc_info=True)
            return False
    
    def _adopt_access_token(self, access_token: str) -> bool:
        """Set + validate an access token, persist it."""
        try:
            self.kite.set_access_token(access_token)
            self.config['zerodha']['access_token'] = access_token
            profile = self.kite.profile()
            persist_access_token(access_token)
            logging.info(f"Authentication successful. Connected as {profile.get('user_name', 'user')}.")
            return True
        except Exception as e:
            logging.warning(f"Access token rejected: {e}")
            return False
    
    async def validate_token(self) -> bool:
        """
        Confirms the current Zerodha access token is still valid by making a
        cheap API call (profile). Returns True if valid.
        """
        import asyncio
        try:
            await asyncio.to_thread(self.kite.profile)
            return True
        except Exception as exc:
            login_url = self.kite.login_url() if self.kite else "https://kite.zerodha.com"
            logging.error(
                f"Token validation failed: {exc}\n"
                f"Refresh your token at: {login_url}"
            )
            return False
    
    def get_kite_client(self):
        """Returns the authenticated KiteConnect client."""
        return self.kite