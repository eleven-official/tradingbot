"""
Alpaca Paper Trading Launcher
Real paper trading with Alpaca broker integration
"""
# --- UTF-8 stdio guard (auto-inserted) ---
import sys as _sys_io
if hasattr(_sys_io.stdout, "reconfigure"):
    _sys_io.stdout.reconfigure(encoding="utf-8", errors="replace")
    _sys_io.stderr.reconfigure(encoding="utf-8", errors="replace")

import asyncio
import logging
from datetime import datetime
import pandas as pd
import numpy as np
from pathlib import Path
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('alpaca_paper_trading.log'),
        logging.StreamHandler()
    ],
    encoding='utf-8'
)

logger = logging.getLogger(__name__)


class AlpacaPaperTradingLauncher:
    """
    Alpaca paper trading launcher with real market data and execution.
    """
    
    def __init__(self):
        self.config = self._load_config()
        self.alpaca_broker = None
        self.is_running = False
        
        # Popular stocks for paper trading
        self.symbols = ['AAPL', 'TSLA', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META']
        
        # Strategy settings
        self.strategy_name = 'momentum'
        self.position_size = 10  # Number of shares per trade
        
    def _load_config(self):
        """Load Alpaca configuration from .env.alpaca file."""
        config = {}
        env_file = Path('.env.alpaca')
        
        if env_file.exists():
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        config[key.strip()] = value.strip()
        else:
            logger.warning(".env.alpaca file not found - using defaults")
            config = {
                'ALPACA_API_KEY': 'YOUR_KEY',
                'ALPACA_API_SECRET': 'YOUR_SECRET',
                'ALPACA_ACCOUNT_TYPE': 'paper'
            }
        
        return config
    
    async def initialize(self):
        """Initialize the Alpaca broker connection."""
        logger.info("Initializing Alpaca Paper Trading System...")
        
        from core_engine.alpaca_broker import AlpacaBroker, AlpacaConfig, AccountType
        
        # Determine base URL based on account type
        account_type = AccountType.PAPER if self.config.get('ALPACA_ACCOUNT_TYPE') == 'paper' else AccountType.LIVE
        base_url = "https://paper-api.alpaca.markets" if account_type == AccountType.PAPER else "https://api.alpaca.markets"
        
        alpaca_config = AlpacaConfig(
            api_key=self.config.get('ALPACA_API_KEY'),
            api_secret=self.config.get('ALPACA_API_SECRET'),
            account_type=account_type,
            base_url=base_url
        )
        
        self.alpaca_broker = AlpacaBroker(alpaca_config)
        
        # Connect to Alpaca
        success = await self.alpaca_broker.initialize()
        
        if not success:
            logger.error("Failed to connect to Alpaca")
            return False
        
        # Display account info
        account = self.alpaca_broker.get_account()
        logger.info(f"Account ID: {account.get('id', 'N/A')}")
        logger.info(f"Buying Power: ${account.get('buying_power', 0):,.2f}")
        logger.info(f"Portfolio Value: ${account.get('portfolio_value', 0):,.2f}")
        logger.info(f"Account Type: {account_type.value}")
        
        # Check market clock
        clock = self.alpaca_broker.get_clock()
        logger.info(f"Market Open: {clock.get('is_open', False)}")
        
        return True
    
    async def run_paper_trading(self):
        """Run paper trading with Alpaca."""
        logger.info("Starting Alpaca Paper Trading Session...")
        self.is_running = True
        
        iteration = 0
        
        while self.is_running and iteration < 100:
            iteration += 1
            
            try:
                # Check if market is open
                clock = self.alpaca_broker.get_clock()
                if not clock.get('is_open', False):
                    logger.info("Market is closed - waiting...")
                    await asyncio.sleep(60)
                    continue
                
                # Get current positions
                positions = self.alpaca_broker.get_positions()
                logger.info(f"Current positions: {len(positions)}")
                
                # Trade each symbol
                for symbol in self.symbols:
                    # Get historical data
                    bars = self.alpaca_broker.get_bars(symbol, '1Day', limit=100)
                    
                    if bars is not None and len(bars) > 20:
                        # Generate signals using strategy
                        from core_engine.academic_strategies import StrategyLibrary
                        
                        if not hasattr(self, 'strategy_library'):
                            self.strategy_library = StrategyLibrary()
                        
                        strategy = self.strategy_library.get_strategy(self.strategy_name)
                        
                        if strategy:
                            # Attach symbol to data
                            bars_copy = bars.copy()
                            bars_copy.attrs["symbol"] = symbol
                            
                            signals = strategy.generate_signals(bars_copy)
                            
                            for signal in signals:
                                # Check if we should execute this signal
                                if self._should_execute_signal(signal, positions):
                                    await self._execute_signal(signal)
                
                # Display status every 10 iterations
                if iteration % 10 == 0:
                    account = self.alpaca_broker.get_account()
                    positions = self.alpaca_broker.get_positions()
                    logger.info(f"Iteration {iteration} | Portfolio: ${account.get('portfolio_value', 0):,.2f} | Positions: {len(positions)}")
                
                # Wait before next iteration
                await asyncio.sleep(30)  # Check every 30 seconds
                
                # Stop after 100 iterations for demo
                if iteration >= 100:
                    logger.info("Paper trading session complete (100 iterations)")
                    break
            
            except Exception as e:
                logger.error(f"Error in trading loop: {e}")
                await asyncio.sleep(10)
    
    def _should_execute_signal(self, signal, positions):
        """Determine if we should execute a signal."""
        # Check if we already have a position in this symbol
        symbol_positions = [p for p in positions if p.symbol == signal.symbol]
        
        if signal.action == 'BUY':
            # Only buy if we don't already have a position
            return len(symbol_positions) == 0
        
        elif signal.action == 'SELL':
            # Only sell if we have a long position
            return any(p.side == 'long' for p in symbol_positions)
        
        return False
    
    async def _execute_signal(self, signal):
        """Execute a trading signal on Alpaca."""
        try:
            logger.info(f"Executing {signal.action} signal for {signal.symbol}")
            
            # Calculate quantity (shares)
            # Alpaca requires integer shares
            qty = int(self.position_size)
            
            # Place order
            order = self.alpaca_broker.place_order(
                symbol=signal.symbol,
                side=signal.action.lower(),
                qty=qty,
                order_type='market'
            )
            
            if order:
                logger.info(f"Order placed: {order.side} {order.qty} {order.symbol} (ID: {order.id})")
            else:
                logger.warning(f"Failed to place order for {signal.symbol}")
        
        except Exception as e:
            logger.error(f"Error executing signal: {e}")
    
    async def stop(self):
        """Stop the paper trading session."""
        logger.info("Stopping Alpaca Paper Trading Session...")
        self.is_running = False
        
        if self.alpaca_broker:
            # Print final results
            await self._print_final_results()
            
            await self.alpaca_broker.shutdown()
        
        logger.info("Alpaca Paper Trading Session stopped")
    
    async def _print_final_results(self):
        """Print final trading results."""
        account = self.alpaca_broker.get_account()
        positions = self.alpaca_broker.get_positions()
        orders = self.alpaca_broker.get_orders()
        
        logger.info("")
        logger.info("="*60)
        logger.info("ALPACA PAPER TRADING RESULTS")
        logger.info("="*60)
        logger.info(f"Portfolio Value: ${account.get('portfolio_value', 0):,.2f}")
        logger.info(f"Cash: ${account.get('cash', 0):,.2f}")
        logger.info(f"Buying Power: ${account.get('buying_power', 0):,.2f}")
        logger.info(f"Open Positions: {len(positions)}")
        logger.info(f"Total Orders: {len(orders)}")
        
        if positions:
            logger.info("\nCurrent Positions:")
            for pos in positions:
                logger.info(f"  {pos.symbol}: {pos.qty} shares @ ${pos.avg_entry_price:.2f} | P&L: ${pos.unrealized_pl:.2f}")
        
        logger.info("="*60)
        logger.info("")


async def main():
    """Main entry point."""
    launcher = AlpacaPaperTradingLauncher()
    
    try:
        success = await launcher.initialize()
        if success:
            await launcher.run_paper_trading()
        else:
            logger.error("Failed to initialize")
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        await launcher.stop()


if __name__ == '__main__':
    print("""
============================================================
                                                             
         ALPACA PAPER TRADING SYSTEM
                                                             
    Real Stock Market Data - Free Paper Trading
    Direct Alpaca Integration - No Simulated Data
                                                             
============================================================
    """)
    
    asyncio.run(main())