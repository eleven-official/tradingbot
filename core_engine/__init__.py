"""Core engine exports, loaded only when a particular subsystem is requested.

Importing offline research utilities must not require network adapters, dashboard
servers or the complete live trading stack.
"""
from importlib import import_module

__all__ = ['QuantumTradingEngine', 'SystemState', 'MarketState', 'SystemHealth',
           'ChaosEngineering', 'ChaosScenario', 'ChaosTestResult']


def __getattr__(name):
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = ".chaos_engineering" if name.startswith("Chaos") else ".main"
    value = getattr(import_module(module, __name__), name)
    globals()[name] = value
    return value
