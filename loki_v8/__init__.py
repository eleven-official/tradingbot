"""LOKI v8 — unified multi-market trading engine.

Consolidates the best parts of the Loki platform (and the merged
strategy repos) into one clean, testable core:

    data -> indicators -> strategy -> risk -> broker -> backtest
    (plus a Director->Quant->Risk->Execution multi-agent layer)

The engine is broker-agnostic: it trades US stocks, crypto, and NSE
instruments through a single interface, with a paper/live switch and
live market data in both modes.
"""

__version__ = "8.0.0"
__all__ = ["config", "data", "indicators", "strategy", "risk", "broker",
           "backtest", "bot", "regime", "agents"]
