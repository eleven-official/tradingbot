"""Loki User Interface Module"""

try:
    from loki.ui.candlestick_chart import ProfessionalCandlestickChart, CandlestickItem

    __all__ = ["ProfessionalCandlestickChart", "CandlestickItem"]
except ImportError:
    # PyQt6 / pyqtgraph not installed: the GUI classes are unavailable but the
    # `loki` package still imports cleanly for headless (CLI/paper) use.
    __all__ = []
