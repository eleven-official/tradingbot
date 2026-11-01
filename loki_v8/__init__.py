"""LOKI v8 — unified multi-market trading engine.

Consolidates the best parts of the Loki platform (and the merged
strategy repos) into one clean, testable core:

    data -> indicators -> strategy -> risk -> broker -> backtest
    (plus a Director->Quant->Risk->Execution multi-agent layer)

The engine is broker-agnostic: it trades US stocks, crypto, and NSE
instruments through a single interface, with a paper/live switch and
live market data in both modes.

New in v8.8:
- portfolio: correlation-aware portfolio construction
- stress: scenario stress testing & Monte Carlo
- importance: feature importance & trade attribution
- journal: trade journaling & decision logging
- report: automated research report generation
- features: advanced factor engineering & regime-gated signals
- validation: purged walk-forward CV with embargo
- meta: meta-learning ensemble (regime-conditioned weights)
- position_mgr: dynamic position sizing & trade lifecycle
- monitor: real-time signal monitor & alerting
"""

__version__ = "8.8.0"
__all__ = [
    "config", "data", "indicators", "strategy", "risk", "broker",
    "backtest", "bot", "regime", "agents",
    "portfolio", "stress", "importance", "journal", "report",
    "features", "validation", "meta", "position_mgr", "monitor",
    "crypto_paper", "train", "train_crypto", "synthetic", "learn", "persistence",
]
