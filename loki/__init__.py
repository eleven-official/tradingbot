"""
Loki Trading Platform
~~~~~~~~~~~~~~~~~~~~~

Enterprise-grade AI-powered algorithmic trading platform.

:copyright: (c) 2024-2026 by Loki Trading Systems.
:license: Proprietary
"""

from typing import TYPE_CHECKING

from loki.version import __version__, __version_info__

# Public, lightweight package exports. Avoid importing heavy/optional
# runtime components (Flask, brokers, state manager) at import time so
# importing `loki` does not pull in optional dependencies.
__all__ = ["__version__", "__version_info__"]

if TYPE_CHECKING:
    from loki.bot import LokiBot  # pragma: no cover
    from core.state_manager import StateManager  # pragma: no cover
else:
    def get_LokiBot():
        """Return the LokiBot class (imported lazily)."""
        from loki.bot import LokiBot
        return LokiBot

    def get_StateManager():
        """Return the StateManager class (imported lazily)."""
        from core.state_manager import StateManager
        return StateManager

    __all__.extend(["get_LokiBot", "get_StateManager"])

import logging
logging.getLogger(__name__).addHandler(logging.NullHandler())
