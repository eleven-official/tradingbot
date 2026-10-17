"""
Loki Trading Platform
~~~~~~~~~~~~~~~~~~~~~

Enterprise-grade AI-powered algorithmic trading platform.

:copyright: (c) 2024-2026 by Loki Trading Systems.
:license: Proprietary
"""

from typing import TYPE_CHECKING

from loki.version import __version__, __version_info__

__all__ = ["__version__", "__version_info__"]

__all__.extend(["LokiBot", "StateManager", "get_LokiBot", "get_StateManager"])

def __getattr__(name: str):
    if name in ("LokiBot", "get_LokiBot"):
        try:
            from loki.bot import LokiBot
            return LokiBot
        except Exception:
            from loki_v8.bot import LokiBot
            return LokiBot
    if name in ("StateManager", "get_StateManager"):
        from core.state_manager import StateManager
        return StateManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

import logging
logging.getLogger(__name__).addHandler(logging.NullHandler())
