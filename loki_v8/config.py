"""LOKI v8 unified configuration.

A single config object drives every subsystem so that paper/live mode,
risk limits, and the tradeable universe are all switchable in one place.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import List, Optional


@dataclass
class LokiConfig:
    # --- Trading mode -----------------------------------------------------
    mode: str = "paper"            # "paper" | "live"

    # --- Market universe (multi-market yfinance tickers) -----------------
    # US stocks/ETFs, crypto (CCC -USD), and NSE (.NS / ^NSEI index).
    symbols: List[str] = field(default_factory=lambda: [
        "AAPL", "MSFT", "NVDA", "SPY", "QQQ",
        "BTC-USD", "ETH-USD", "SOL-USD",
        "^NSEI", "RELIANCE.NS", "TCS.NS",
    ])

    # --- Data -------------------------------------------------------------
    timeframe: str = "1d"          # yfinance interval: 1m,5m,15m,1h,1d,1wk
    period: str = "2y"             # history window used for analysis/backtest
    lookback_bars: int = 250       # min bars a strategy requires

    # --- Account / execution ---------------------------------------------
    initial_cash: float = 100_000.0
    commission_per_trade: float = 0.0   # flat $ per fill (0 for crypto-style)
    slippage_bps: float = 3.0           # basis points of slippage per side

    # --- Risk management --------------------------------------------------
    risk_per_trade_pct: float = 1.0     # % of equity risked on each trade
    max_open_positions: int = 4
    stop_loss_atr: float = 2.0          # stop distance in ATR multiples
    take_profit_atr: float = 3.0        # target distance in ATR multiples
    trailing_stop_atr: float = 0.0      # >0 enables ATR trailing stop
    max_daily_loss_pct: float = 3.0     # halt trading after this daily loss
    max_consecutive_losses: int = 3     # halt after this many losses in a row

    # --- Strategy ---------------------------------------------------------
    signal_threshold: float = 20.0      # |score| (0-100) required to act
    min_confidence: float = 65.0        # min ensemble confidence (0-100)
    require_trend_filter: bool = True   # only trade with-trend signals
    regime_filter: bool = True          # block new longs while in a bear regime
    allow_short: bool = False           # enable short entries (crypto can short)
    max_hold_bars: int = 30             # time-stop: exit after N bars held
    max_atr_pct: float = 5.0            # skip entries when daily ATR% exceeds this

    # --- Live broker credentials (added later via .env) -------------------
    alpaca_api_key: Optional[str] = None
    alpaca_api_secret: Optional[str] = None
    binance_api_key: Optional[str] = None
    binance_api_secret: Optional[str] = None

    # --- Misc -------------------------------------------------------------
    state_dir: str = "state"
    log_level: str = "INFO"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "LokiConfig":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def default_config() -> LokiConfig:
    """Return the recommended default configuration."""
    return LokiConfig()
