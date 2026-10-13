"""
Loki Trading Platform
~~~~~~~~~~~~~~~~~~~~~

Enterprise-grade AI-powered algorithmic trading platform.

:copyright: (c) 2024-2026 by Loki Trading Systems.
:license: Proprietary, see LICENSE for more details.
"""

from loki.version import __version__, __version_info__
from loki.bot import LokiBot
from core.state_manager import StateManager

__all__ = ['__version__', '__version_info__', 'LokiBot', 'StateManager']

# Metadata
__title__ = 'loki-trading-platform'
__author__ = 'Loki Trading Systems'
__license__ = 'Proprietary'
__copyright__ = 'Copyright 2024-2026 Loki Trading Systems'

# Initialize logging
import logging
logging.getLogger(__name__).addHandler(logging.NullHandler())
