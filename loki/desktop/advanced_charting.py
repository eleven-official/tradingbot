"""
Loki Advanced Charting - TradingView-Style Charts
Professional trading charts with technical indicators, drawing tools, and pattern recognition
"""

import sys
from typing import List, Dict, Tuple, Optional
from datetime import datetime
import numpy as np
import pandas as pd

try:
    from PyQt6.QtWidgets import *
    from PyQt6.QtCore import *
    from PyQt6.QtGui import *

    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

try:
    import pyqtgraph as pg
    from pyqtgraph import PlotWidget, mkPen, InfiniteLine

    PYQTGRAPH_AVAILABLE = True
except ImportError:
    PYQTGRAPH_AVAILABLE = False


class CandlestickItem(pg.GraphicsObject):
    """Custom candlestick chart item"""

    def __init__(self, data):
        pg.GraphicsObject.__init__(self)
        self.data = data  # DataFrame with OHLC
        self.generatePicture()

    def generatePicture(self):
        """Generate the candlestick picture"""
        self.picture = QPicture()
        painter = QPainter(self.picture)

        w = 0.3  # Candle width

        for i, (idx, row) in enumerate(self.data.iterrows()):
            t = i
            open_price = row["open"]
            close_price = row["close"]
            high = row["high"]
            low = row["low"]

            # Determine color
            if close_price > open_price:
                # Bullish candle (green)
                painter.setPen(mkPen("#4ec9b0", width=1))
                painter.setBrush(QBrush(QColor("#4ec9b0")))
            else:
                # Bearish candle (red)
                painter.setPen(mkPen("#f48771", width=1))
                painter.setBrush(QBrush(QColor("#f48771")))

            # Draw high-low line
            painter.drawLine(QPointF(t, low), QPointF(t, high))

            # Draw body
            body_height = abs(close_price - open_price)
            body_bottom = min(open_price, close_price)

            painter.drawRect(QRectF(t - w / 2, body_bottom, w, body_height))

        painter.end()

    def paint(self, painter, option, widget):
        painter.drawPicture(0, 0, self.picture)

    def boundingRect(self):
        return QRectF(self.picture.boundingRect())


class TradingViewChart(QWidget):
    """Advanced TradingView-style chart with multiple features"""

    def __init__(self, symbol: str = "AAPL"):
        super().__init__()
        self.symbol = symbol
        self.timeframe = "1D"
        self.indicators_enabled = {
            "sma_20": True,
            "sma_50": True,
            "sma_200": False,
            "ema_12": False,
            "ema_26": False,
            "bollinger": True,
            "volume": True,
            "rsi": True,
            "macd": True,
        }
        self.drawing_mode = None  # 'trendline', 'horizontal', 'fibonacci', None
        self.drawings = []

        self.setup_ui()

    def setup_ui(self):
        """Setup the chart UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = self.create_toolbar()
        layout.addWidget(toolbar)

        if not PYQTGRAPH_AVAILABLE:
            label = QLabel("📈 Advanced charts require pyqtgraph\npip install pyqtgraph")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("color: #888; font-size: 14pt; padding: 50px;")
            layout.addWidget(label)
            return

        # Create chart area with linked axes
        self.graphics_layout = pg.GraphicsLayoutWidget()
        self.graphics_layout.setBackground("#1a1a1d")

        # Main price chart
        self.price_plot = self.graphics_layout.addPlot(row=0, col=0)
        self.price_plot.setLabel("left", "Price ($)", color="#ffffff")
        self.price_plot.showGrid(x=True, y=True, alpha=0.2)
        self.price_plot.setMenuEnabled(False)

        # Volume chart
        self.graphics_layout.nextRow()
        self.volume_plot = self.graphics_layout.addPlot(row=1, col=0)
        self.volume_plot.setLabel("left", "Volume", color="#ffffff")
        self.volume_plot.setMaximumHeight(150)
        self.volume_plot.showGrid(x=True, y=True, alpha=0.2)
        self.volume_plot.setXLink(self.price_plot)

        # RSI indicator
        self.graphics_layout.nextRow()
        self.rsi_plot = self.graphics_layout.addPlot(row=2, col=0)
        self.rsi_plot.setLabel("left", "RSI", color="#ffffff")
        self.rsi_plot.setMaximumHeight(100)
        self.rsi_plot.showGrid(x=True, y=True, alpha=0.2)
        self.rsi_plot.setXLink(self.price_plot)
        self.rsi_plot.setYRange(0, 100)

        # Add RSI overbought/oversold lines
        self.rsi_plot.addLine(y=70, pen=mkPen("#f48771", width=1, style=Qt.PenStyle.DashLine))
        self.rsi_plot.addLine(y=30, pen=mkPen("#4ec9b0", width=1, style=Qt.PenStyle.DashLine))

        # MACD indicator
        self.graphics_layout.nextRow()
        self.macd_plot = self.graphics_layout.addPlot(row=3, col=0)
        self.macd_plot.setLabel("left", "MACD", color="#ffffff")
        self.macd_plot.setMaximumHeight(100)
        self.macd_plot.showGrid(x=True, y=True, alpha=0.2)
        self.macd_plot.setXLink(self.price_plot)
        self.macd_plot.addLine(y=0, pen=mkPen("#666666", width=1))

        layout.addWidget(self.graphics_layout)

        # Initialize with demo data
        self.load_demo_data()

    def create_toolbar(self) -> QWidget:
        """Create chart toolbar"""
        toolbar = QWidget()
        toolbar.setFixedHeight(50)
        toolbar.setStyleSheet("""
            QWidget {
                background: rgba(30,30,33,0.95);
                border-bottom: 1px solid rgba(255,255,255,0.1);
            }
            QPushButton {
                background: rgba(60,60,63,0.5);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 6px;
                color: #cccccc;
                padding: 6px 12px;
                font-size: 10pt;
            }
            QPushButton:hover {
                background: rgba(80,80,83,0.8);
                border: 1px solid #007acc;
            }
            QPushButton:checked {
                background: rgba(0,122,204,0.5);
                border: 1px solid #00d4ff;
                color: #00d4ff;
            }
            QComboBox {
                background: rgba(60,60,63,0.5);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 6px;
                color: #cccccc;
                padding: 6px 12px;
                min-width: 80px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border: none;
            }
        """)

        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(10, 5, 10, 5)

        # Symbol selector
        symbol_label = QLabel("Symbol:")
        symbol_label.setStyleSheet("color: #999; background: transparent;")
        self.symbol_combo = QComboBox()
        self.symbol_combo.addItems(["AAPL", "MSFT", "GOOGL", "TSLA", "SPY", "QQQ"])
        self.symbol_combo.setCurrentText(self.symbol)

        # Timeframe selector
        tf_label = QLabel("Timeframe:")
        tf_label.setStyleSheet("color: #999; background: transparent;")
        self.timeframe_combo = QComboBox()
        self.timeframe_combo.addItems(["1m", "5m", "15m", "1h", "4h", "1D", "1W"])
        self.timeframe_combo.setCurrentText(self.timeframe)

        # Indicator toggles
        indicators_label = QLabel("Indicators:")
        indicators_label.setStyleSheet("color: #999; background: transparent;")

        self.sma_btn = QPushButton("SMA")
        self.sma_btn.setCheckable(True)
        self.sma_btn.setChecked(True)

        self.ema_btn = QPushButton("EMA")
        self.ema_btn.setCheckable(True)

        self.bb_btn = QPushButton("BB")
        self.bb_btn.setCheckable(True)
        self.bb_btn.setChecked(True)

        self.volume_btn = QPushButton("Volume")
        self.volume_btn.setCheckable(True)
        self.volume_btn.setChecked(True)

        self.rsi_btn = QPushButton("RSI")
        self.rsi_btn.setCheckable(True)
        self.rsi_btn.setChecked(True)

        self.macd_btn = QPushButton("MACD")
        self.macd_btn.setCheckable(True)
        self.macd_btn.setChecked(True)

        # Drawing tools
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setStyleSheet("background: rgba(255,255,255,0.1);")

        drawing_label = QLabel("Draw:")
        drawing_label.setStyleSheet("color: #999; background: transparent;")

        self.trendline_btn = QPushButton("📈 Trend")
        self.trendline_btn.setCheckable(True)

        self.horizontal_btn = QPushButton("➖ H-Line")
        self.horizontal_btn.setCheckable(True)

        self.fibonacci_btn = QPushButton("🎯 Fib")
        self.fibonacci_btn.setCheckable(True)

        self.clear_btn = QPushButton("🗑️ Clear")

        # Pattern recognition
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setStyleSheet("background: rgba(255,255,255,0.1);")

        self.patterns_btn = QPushButton("🔍 Patterns")
        self.patterns_btn.setCheckable(True)

        # Add to layout
        layout.addWidget(symbol_label)
        layout.addWidget(self.symbol_combo)
        layout.addWidget(tf_label)
        layout.addWidget(self.timeframe_combo)
        layout.addWidget(indicators_label)
        layout.addWidget(self.sma_btn)
        layout.addWidget(self.ema_btn)
        layout.addWidget(self.bb_btn)
        layout.addWidget(self.volume_btn)
        layout.addWidget(self.rsi_btn)
        layout.addWidget(self.macd_btn)
        layout.addWidget(sep1)
        layout.addWidget(drawing_label)
        layout.addWidget(self.trendline_btn)
        layout.addWidget(self.horizontal_btn)
        layout.addWidget(self.fibonacci_btn)
        layout.addWidget(self.clear_btn)
        layout.addWidget(sep2)
        layout.addWidget(self.patterns_btn)
        layout.addStretch()

        # Connect signals
        self.sma_btn.toggled.connect(self.update_chart)
        self.ema_btn.toggled.connect(self.update_chart)
        self.bb_btn.toggled.connect(self.update_chart)
        self.rsi_btn.toggled.connect(lambda checked: self.toggle_plot(self.rsi_plot, checked))
        self.macd_btn.toggled.connect(lambda checked: self.toggle_plot(self.macd_plot, checked))
        self.volume_btn.toggled.connect(lambda checked: self.toggle_plot(self.volume_plot, checked))

        return toolbar

    def toggle_plot(self, plot, visible: bool):
        """Toggle subplot visibility"""
        if visible:
            plot.show()
        else:
            plot.hide()

    def load_demo_data(self):
        """Load demo market data"""
        # Generate realistic demo data
        np.random.seed(42)
        n_bars = 200

        dates = pd.date_range(end=datetime.now(), periods=n_bars, freq="1D")

        # Generate price data with trend and noise
        base_price = 150
        trend = np.linspace(0, 20, n_bars)
        noise = np.random.randn(n_bars).cumsum() * 2
        close_prices = base_price + trend + noise

        # Generate OHLC from close
        opens = close_prices + np.random.randn(n_bars) * 0.5
        highs = np.maximum(opens, close_prices) + np.abs(np.random.randn(n_bars)) * 1.5
        lows = np.minimum(opens, close_prices) - np.abs(np.random.randn(n_bars)) * 1.5
        volumes = np.random.randint(1000000, 10000000, n_bars)

        self.data = pd.DataFrame(
            {
                "date": dates,
                "open": opens,
                "high": highs,
                "low": lows,
                "close": close_prices,
                "volume": volumes,
            }
        )

        self.update_chart()

    def update_chart(self):
        """Update chart with current data and indicators"""
        if not PYQTGRAPH_AVAILABLE or not hasattr(self, "data"):
            return

        # Clear existing plots
        self.price_plot.clear()
        self.volume_plot.clear()
        self.rsi_plot.clear()
        self.macd_plot.clear()

        # Plot candlesticks
        self.plot_candlesticks()

        # Plot indicators
        if self.sma_btn.isChecked():
            self.plot_sma()

        if self.ema_btn.isChecked():
            self.plot_ema()

        if self.bb_btn.isChecked():
            self.plot_bollinger_bands()

        if self.volume_btn.isChecked():
            self.plot_volume()

        if self.rsi_btn.isChecked():
            self.plot_rsi()

        if self.macd_btn.isChecked():
            self.plot_macd()

    def plot_candlesticks(self):
        """Plot candlestick chart"""
        x = np.arange(len(self.data))

        for i in range(len(self.data)):
            row = self.data.iloc[i]

            # Determine color
            color = "#4ec9b0" if row["close"] >= row["open"] else "#f48771"

            # Draw wick (high-low)
            wick = pg.PlotCurveItem(
                x=[i, i], y=[row["low"], row["high"]], pen=mkPen(color, width=1)
            )
            self.price_plot.addItem(wick)

            # Draw body (open-close)
            body_height = abs(row["close"] - row["open"])
            if body_height < 0.01:  # Doji
                body_height = 0.1

            body = pg.BarGraphItem(
                x=[i],
                height=[body_height],
                y0=[min(row["open"], row["close"])],
                width=0.6,
                brush=color,
                pen=mkPen(color, width=1),
            )
            self.price_plot.addItem(body)

    def plot_sma(self):
        """Plot Simple Moving Averages"""
        x = np.arange(len(self.data))

        # SMA 20
        sma_20 = self.data["close"].rolling(20).mean()
        self.price_plot.plot(x, sma_20, pen=mkPen("#ffa500", width=2), name="SMA 20")

        # SMA 50
        sma_50 = self.data["close"].rolling(50).mean()
        self.price_plot.plot(x, sma_50, pen=mkPen("#00d4ff", width=2), name="SMA 50")

    def plot_ema(self):
        """Plot Exponential Moving Averages"""
        x = np.arange(len(self.data))

        # EMA 12
        ema_12 = self.data["close"].ewm(span=12).mean()
        self.price_plot.plot(
            x, ema_12, pen=mkPen("#ff6b6b", width=2, style=Qt.PenStyle.DashLine), name="EMA 12"
        )

        # EMA 26
        ema_26 = self.data["close"].ewm(span=26).mean()
        self.price_plot.plot(
            x, ema_26, pen=mkPen("#4ecdc4", width=2, style=Qt.PenStyle.DashLine), name="EMA 26"
        )

    def plot_bollinger_bands(self):
        """Plot Bollinger Bands"""
        x = np.arange(len(self.data))

        sma = self.data["close"].rolling(20).mean()
        std = self.data["close"].rolling(20).std()

        upper_band = sma + (2 * std)
        lower_band = sma - (2 * std)

        # Plot bands
        self.price_plot.plot(
            x, upper_band, pen=mkPen("#9370db", width=1, style=Qt.PenStyle.DotLine), name="BB Upper"
        )
        self.price_plot.plot(
            x, lower_band, pen=mkPen("#9370db", width=1, style=Qt.PenStyle.DotLine), name="BB Lower"
        )

        # Fill between bands
        fill = pg.FillBetweenItem(
            self.price_plot.plot(x, upper_band, pen=None),
            self.price_plot.plot(x, lower_band, pen=None),
            brush=(147, 112, 219, 30),
        )
        self.price_plot.addItem(fill)

    def plot_volume(self):
        """Plot volume bars"""
        x = np.arange(len(self.data))

        # Color by price movement
        colors = []
        for i in range(len(self.data)):
            if self.data.iloc[i]["close"] >= self.data.iloc[i]["open"]:
                colors.append("#4ec9b0")
            else:
                colors.append("#f48771")

        # Create bar graph
        for i in range(len(self.data)):
            bar = pg.BarGraphItem(
                x=[i], height=[self.data.iloc[i]["volume"]], width=0.8, brush=colors[i], pen=None
            )
            self.volume_plot.addItem(bar)

    def plot_rsi(self):
        """Plot RSI indicator"""
        # Calculate RSI
        delta = self.data["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        x = np.arange(len(self.data))

        # Plot RSI line
        self.rsi_plot.plot(x, rsi, pen=mkPen("#9370db", width=2), name="RSI")

        # Color zones
        overbought_fill = pg.LinearRegionItem(
            values=[70, 100], orientation="horizontal", brush=(244, 135, 113, 30), movable=False
        )
        self.rsi_plot.addItem(overbought_fill)

        oversold_fill = pg.LinearRegionItem(
            values=[0, 30], orientation="horizontal", brush=(78, 201, 176, 30), movable=False
        )
        self.rsi_plot.addItem(oversold_fill)

    def plot_macd(self):
        """Plot MACD indicator"""
        # Calculate MACD
        ema_12 = self.data["close"].ewm(span=12).mean()
        ema_26 = self.data["close"].ewm(span=26).mean()
        macd_line = ema_12 - ema_26
        signal_line = macd_line.ewm(span=9).mean()
        histogram = macd_line - signal_line

        x = np.arange(len(self.data))

        # Plot MACD line
        self.macd_plot.plot(x, macd_line, pen=mkPen("#00d4ff", width=2), name="MACD")

        # Plot signal line
        self.macd_plot.plot(x, signal_line, pen=mkPen("#ffa500", width=2), name="Signal")

        # Plot histogram
        colors = ["#4ec9b0" if h >= 0 else "#f48771" for h in histogram]
        for i in range(len(self.data)):
            if not np.isnan(histogram.iloc[i]):
                bar = pg.BarGraphItem(
                    x=[i], height=[histogram.iloc[i]], width=0.8, brush=colors[i], pen=None
                )
                self.macd_plot.addItem(bar)


class MultiTimeframeChart(QWidget):
    """Multi-timeframe analysis chart"""

    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        """Setup multi-timeframe UI"""
        layout = QVBoxLayout(self)

        # Title
        title = QLabel("📊 Multi-Timeframe Analysis")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setStyleSheet("color: #00d4ff; padding: 10px;")

        # Create grid of charts
        grid = QGridLayout()

        timeframes = ["1m", "5m", "15m", "1h", "4h", "1D"]

        for i, tf in enumerate(timeframes):
            row = i // 3
            col = i % 3

            chart = TradingViewChart()
            chart.timeframe = tf
            chart.setMinimumHeight(250)

            # Add label
            label = QLabel(tf)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("""
                background: rgba(0,122,204,0.3);
                color: #00d4ff;
                padding: 5px;
                border-radius: 5px;
                font-weight: bold;
            """)

            container = QWidget()
            container_layout = QVBoxLayout(container)
            container_layout.setContentsMargins(5, 5, 5, 5)
            container_layout.addWidget(label)
            container_layout.addWidget(chart)

            grid.addWidget(container, row, col)

        layout.addWidget(title)
        layout.addLayout(grid)


def main():
    """Launch advanced charting demo"""
    if not PYQT_AVAILABLE:
        print("PyQt6 required: pip install PyQt6")
        return

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Dark palette
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(26, 26, 29))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(204, 204, 204))
    palette.setColor(QPalette.ColorRole.Base, QColor(30, 30, 33))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(45, 45, 48))
    palette.setColor(QPalette.ColorRole.Text, QColor(204, 204, 204))
    app.setPalette(palette)

    window = TradingViewChart()
    window.setWindowTitle("Loki Advanced Charting")
    window.resize(1400, 900)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
