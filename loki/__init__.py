"""Public package exports for the Loki trading platform."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from loki.version import __version__, __version_info__

if TYPE_CHECKING:
    from core.state_manager import StateManager
    from loki.bot import LokiBot

__all__ = [
    "__version__",
    "__version_info__",
    "LokiBot",
    "StateManager",
    "get_LokiBot",
    "get_StateManager",
]


def __getattr__(name: str) -> Any:
    """Load heavier bot components only when callers request them."""
    if name == "LokiBot":
        from loki.bot import LokiBot

        return LokiBot
    if name == "StateManager":
        from core.state_manager import StateManager

        return StateManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def get_LokiBot() -> type:
    """Return the LokiBot class without importing it during package startup."""
    return __getattr__("LokiBot")


def get_StateManager() -> type:
    """Return the StateManager class without importing it during package startup."""
    return __getattr__("StateManager")


logging.getLogger(__name__).addHandler(logging.NullHandler())
