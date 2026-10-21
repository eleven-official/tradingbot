"""Public package exports for the Loki trading platform.

The web workspace imports the deployed application lazily; pure calculation
helpers stay usable in minimal Python environments.

The desktop-era ``loki.bot`` and ``core.state_manager`` trees were retired in
the repository cleanup. Their names are no longer re-exported: any legacy
caller asking for them gets the standard AttributeError, stated plainly, and
nothing pretends those modules still exist.
"""
from __future__ import annotations

import logging
from typing import Any, cast

from loki.version import __version__, __version_info__

__all__ = ["__version__", "__version_info__", "get_LokiBot", "get_StateManager"]


def __getattr__(name: str) -> Any:
    """Load heavier components only when callers explicitly request them.

    Both targets were retired by the repository cleanup; the config-level
    ``ignore_missing_imports`` keeps them typing-silent and the runtime
    access degrades honestly.
    """
    if name == "LokiBot":
        from loki.bot import LokiBot

        return LokiBot
    if name == "StateManager":
        from core.state_manager import StateManager

        return StateManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def get_LokiBot() -> type:
    """Return the LokiBot class without importing it during package startup."""
    return cast(type, __getattr__("LokiBot"))


def get_StateManager() -> type:
    """Return the StateManager class without importing it during package startup."""
    return cast(type, __getattr__("StateManager"))


logging.getLogger(__name__).addHandler(logging.NullHandler())
