"""
Configuration validation using Pydantic for robust configuration management.
"""
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field


class TradingBotError(Exception):
    """Base exception for trading bot errors."""
    pass


class ConfigurationError(TradingBotError):
    """Configuration validation errors."""
    pass


@dataclass
class ZerodhaConfig:
    """Zerodha API configuration."""
    api_key: str
    api_secret: str
    access_token: str = ""
    
    def __post_init__(self):
        if not self.api_key or not self.api_secret:
            raise ConfigurationError("Zerodha api_key and api_secret are required")


@dataclass
class GoogleAPIConfig:
    """Google API configuration."""
    api_key: str
    
    def __post_init__(self):
        if not self.api_key:
            raise ConfigurationError("Google API key is required")


@dataclass
class EmailConfig:
    """Email configuration."""
    send_daily_report: bool = True
    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 587
    sender_email: str = ""
    sender_password: str = ""
    receiver_email: str = ""
    
    def __post_init__(self):
        if self.send_daily_report:
            if not all([self.sender_email, self.receiver_email, self.sender_password]):
                raise ConfigurationError(
                    "Email settings required when send_daily_report is enabled"
                )


@dataclass
class TradingFlags:
    """Trading flags and parameters."""
    underlying_instrument: str = "NIFTY 50"
    chart_timeframe: str = "5minute"
    product_type: str = "MIS"
    order_variety: str = "REGULAR"
    risk_per_trade_percent: float = 1.0
    stop_loss_percent: float = 15.0
    max_trades_per_day: int = 5
    paper_trading: bool = True
    enable_gemini_loss_analysis: bool = True
    enable_natural_language_prompt: bool = True
    strategy_reassessment_period_minutes: int = 60
    use_rag: bool = False
    rag_min_trading_days: int = 5
    
    def __post_init__(self):
        if not 0 < self.risk_per_trade_percent <= 10:
            raise ConfigurationError(
                f"risk_per_trade_percent must be 0-10%, got {self.risk_per_trade_percent}"
            )
        if not 0 < self.stop_loss_percent <= 50:
            raise ConfigurationError(
                f"stop_loss_percent must be 0-50%, got {self.stop_loss_percent}"
            )
        if self.max_trades_per_day < 1 or self.max_trades_per_day > 20:
            raise ConfigurationError(
                f"max_trades_per_day must be 1-20, got {self.max_trades_per_day}"
            )
        if self.product_type not in ["MIS", "NRML"]:
            raise ConfigurationError(
                f"product_type must be 'MIS' or 'NRML', got {self.product_type}"
            )


@dataclass
class RiskManagement:
    """Risk management configuration."""
    atr_multiplier: float = 2.0
    enable_daily_loss_limit: bool = True
    enable_volatility_adjustment: bool = True
    high_vix_risk_reduction_factor: float = 0.5
    high_vix_threshold: float = 22.0
    max_daily_loss_percent: float = 2.5
    enable_consecutive_loss_limit: bool = True
    max_consecutive_losses: int = 3
    enable_weekly_loss_limit: bool = False
    max_weekly_loss_percent: float = 5.0
    
    def __post_init__(self):
        if not 0 < self.max_daily_loss_percent <= 20:
            raise ConfigurationError(
                f"max_daily_loss_percent must be 0-20%, got {self.max_daily_loss_percent}"
            )
        if not 0 < self.max_weekly_loss_percent <= 30:
            raise ConfigurationError(
                f"max_weekly_loss_percent must be 0-30%, got {self.max_weekly_loss_percent}"
            )
        if self.max_consecutive_losses < 1 or self.max_consecutive_losses > 10:
            raise ConfigurationError(
                f"max_consecutive_losses must be 1-10, got {self.max_consecutive_losses}"
            )
        if not 0 < self.high_vix_threshold <= 50:
            raise ConfigurationError(
                f"high_vix_threshold must be 0-50, got {self.high_vix_threshold}"
            )


@dataclass
class RiskTier:
    """Risk tier configuration."""
    max_capital: Optional[float]
    risk_pct: float
    
    def __post_init__(self):
        if not 0 < self.risk_pct <= 10:
            raise ConfigurationError(
                f"risk_pct must be 0-10%, got {self.risk_pct}"
            )


@dataclass
class ServerConfig:
    """Server configuration for headless mode."""
    headless: bool = False
    login_wait_minutes: float = 90
    dashboard_token: str = ""
    control_pin: str = ""
    
    def __post_init__(self):
        if self.headless and not self.dashboard_token:
            raise ConfigurationError(
                "dashboard_token is required in headless mode"
            )
        if not 0 < self.login_wait_minutes <= 180:
            raise ConfigurationError(
                f"login_wait_minutes must be 0-180, got {self.login_wait_minutes}"
            )


@dataclass
class MetricsConfig:
    """Metrics and monitoring configuration."""
    enabled: bool = True
    prometheus_port: Optional[int] = None
    log_metrics: bool = True


@dataclass
class ProfitPleasureConfig:
    """Profit pleasure notification system configuration."""
    enabled: bool = True
    profit_threshold: float = 100.0
    max_daily_celebrations: int = 10
    streak_multiplier: float = 1.5
    
    def __post_init__(self):
        if self.profit_threshold < 0:
            raise ConfigurationError(
                f"profit_threshold must be non-negative, got {self.profit_threshold}"
            )
        if self.max_daily_celebrations < 1 or self.max_daily_celebrations > 100:
            raise ConfigurationError(
                f"max_daily_celebrations must be 1-100, got {self.max_daily_celebrations}"
            )
        if self.streak_multiplier < 1.0 or self.streak_multiplier > 3.0:
            raise ConfigurationError(
                f"streak_multiplier must be 1.0-3.0, got {self.streak_multiplier}"
            )


@dataclass
class EvolutionaryOptimizerConfig:
    """Evolutionary optimizer configuration."""
    enabled: bool = False
    population_size: int = 10
    mutation_rate: float = 0.1
    elite_count: int = 2
    optimization_target: str = "balanced"
    evolution_interval_days: int = 7
    
    def __post_init__(self):
        if self.population_size < 2 or self.population_size > 50:
            raise ConfigurationError(
                f"population_size must be 2-50, got {self.population_size}"
            )
        if not 0 < self.mutation_rate <= 1.0:
            raise ConfigurationError(
                f"mutation_rate must be 0-1.0, got {self.mutation_rate}"
            )
        if self.elite_count < 1 or self.elite_count >= self.population_size:
            raise ConfigurationError(
                f"elite_count must be 1-(population_size-1), got {self.elite_count}"
            )
        valid_targets = ["maximize_profit", "maximize_win_rate", "minimize_drawdown", "balanced"]
        if self.optimization_target not in valid_targets:
            raise ConfigurationError(
                f"optimization_target must be one of {valid_targets}, got {self.optimization_target}"
            )
        if self.evolution_interval_days < 1 or self.evolution_interval_days > 30:
            raise ConfigurationError(
                f"evolution_interval_days must be 1-30, got {self.evolution_interval_days}"
            )


@dataclass
class TradingViewConfig:
    """TradingView integration configuration."""
    enabled: bool = False
    webhook_secret: str = ""
    require_signature: bool = True
    default_action: str = "execute"
    allowed_symbols: List[str] = field(default_factory=lambda: ["NIFTY", "BANKNIFTY"])
    max_position_size: int = 10
    
    def __post_init__(self):
        valid_actions = ["execute", "queue", "ignore", "require_confirmation"]
        if self.default_action not in valid_actions:
            raise ConfigurationError(
                f"default_action must be one of {valid_actions}, got {self.default_action}"
            )
        if self.max_position_size < 1 or self.max_position_size > 100:
            raise ConfigurationError(
                f"max_position_size must be 1-100, got {self.max_position_size}"
            )


class ConfigValidator:
    """Validates and transforms configuration dictionaries."""
    
    def __init__(self, config_dict: Dict[str, Any]):
        self.config = config_dict
        self._validated = False
    
    def validate(self) -> Dict[str, Any]:
        """Validate all configuration sections."""
        if self._validated:
            return self.config
        
        try:
            self._validate_zerodha()
            self._validate_trading_flags()
            self._validate_risk_management()
            self._validate_risk_tiers()
            self._validate_email()
            self._validate_server()
            self._validate_metrics()
            self._validate_profit_pleasure()
            self._validate_evolutionary_optimizer()
            self._validate_tradingview()
            
            self._validated = True
            logging.info("Configuration validation passed")
            return self.config
            
        except ConfigurationError as e:
            logging.error(f"Configuration validation failed: {e}")
            raise
    
    def _validate_zerodha(self):
        """Validate Zerodha configuration."""
        zerodha = self.config.get('zerodha', {})
        ZerodhaConfig(
            api_key=zerodha.get('api_key', ''),
            api_secret=zerodha.get('api_secret', ''),
            access_token=zerodha.get('access_token', '')
        )
    
    def _validate_trading_flags(self):
        """Validate trading flags."""
        flags = self.config.get('trading_flags', {})
        TradingFlags(**flags)
    
    def _validate_risk_management(self):
        """Validate risk management configuration."""
        risk = self.config.get('risk_management', {})
        RiskManagement(**risk)
    
    def _validate_risk_tiers(self):
        """Validate risk tiers configuration."""
        tiers = self.config.get('risk_tiers', [])
        for tier in tiers:
            RiskTier(
                max_capital=tier.get('max_capital'),
                risk_pct=tier.get('risk_pct')
            )
        
        # Check coherence: each tier's risk_pct should be <= max_daily_loss / 2
        max_daily_loss = self.config.get('risk_management', {}).get('max_daily_loss_percent', 2.5)
        for tier in tiers:
            risk_pct = tier.get('risk_pct', 0)
            if risk_pct > max_daily_loss / 2:
                logging.warning(
                    f"Risk tier risk_pct ({risk_pct}%) > max_daily_loss/2 ({max_daily_loss/2:.1f}%)"
                )
    
    def _validate_email(self):
        """Validate email configuration."""
        email = self.config.get('email_settings', {})
        EmailConfig(**email)
    
    def _validate_server(self):
        """Validate server configuration."""
        server = self.config.get('server', {})
        ServerConfig(**server)
    
    def _validate_metrics(self):
        """Validate metrics configuration."""
        metrics = self.config.get('metrics', {})
        MetricsConfig(**metrics)
    
    def _validate_profit_pleasure(self):
        """Validate profit pleasure configuration."""
        profit_pleasure = self.config.get('profit_pleasure', {})
        ProfitPleasureConfig(**profit_pleasure)
    
    def _validate_evolutionary_optimizer(self):
        """Validate evolutionary optimizer configuration."""
        evo_config = self.config.get('evolutionary_optimizer', {})
        EvolutionaryOptimizerConfig(**evo_config)
    
    def _validate_tradingview(self):
        """Validate TradingView configuration."""
        tradingview = self.config.get('tradingview', {})
        TradingViewConfig(**tradingview)
    
    def get_paper_trading_mode(self) -> bool:
        """Check if paper trading mode is enabled."""
        return self.config.get('trading_flags', {}).get('paper_trading', True)
    
    def get_underlying_instrument(self) -> str:
        """Get the underlying instrument."""
        return self.config.get('trading_flags', {}).get('underlying_instrument', 'NIFTY 50')
    
    def get_chart_timeframe(self) -> str:
        """Get the chart timeframe."""
        return self.config.get('trading_flags', {}).get('chart_timeframe', '5minute')


def validate_config(config_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Convenience function to validate configuration."""
    validator = ConfigValidator(config_dict)
    return validator.validate()