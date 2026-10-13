"""
Professional Candlestick Chart Widget
Beautiful, interactive candlestick charts with indicators
"""
import sys
from typing import List, Dict, Optional
import numpy as np
import pandas as pd

try:
    from PyQt6.QtWidgets import *
    from PyQt6.QtCore import *
    from PyQt6.QtGui import *
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False
    print("PyQt6 required: pip install PyQt6")

try:
    import pyqtgraph as pg
    PYQTGRAPH_AVAILABLE = True
except ImportError:
    PYQTGRAPH_AVAILABLE = False
    print("pyqtgraph required: pip install pyqtgraph")


# Hard-depend on the optional GUI stack so importing this module raises a
# clean ImportError (instead of a NameError) when PyQt6/pyqtgraph are absent.
if not (PYQT_AVAILABLE and PYQTGRAPH_AVAILABLE):
    raise ImportError("PyQt6 and pyqtgraph are required for loki.ui.candlestick_chart")


class CandlestickItem(pg.GraphicsObject):
    """Custom candlestick graphics item"""
    
    def __init__(self, data: pd.DataFrame):
        pg.GraphicsObject.__init__(self)
        self.data = data
        self.picture = None
        self.generatePicture()
    
    def generatePicture(self):
        """Generate candlestick picture"""
        self.picture = QPicture()
        painter = QPainter(self.picture)
        
        w = 0.7  # Candle width
        
        for i in range(len(self.data)):
            row = self.data.iloc[i]
            
            open_price = row['open']
            close_price = row['close']
            high = row['high']
            low = row['low']
            
            # Determine color (green for bullish, red for bearish)
            if close_price >= open_price:
                color = QColor(78, 201, 176)  # Green
                brush = QBrush(color)
            else:
                color = QColor(244, 135, 113)  # Red
                brush = QBrush(color)
            
            painter.setPen(pg.mkPen(color, width=1))
            painter.setBrush(brush)
            
            # Draw high-low wick
            painter.drawLine(QPointF(i, low), QPointF(i, high))
            
            # Draw open-close body
            body_height = abs(close_price - open_price)
            if body_height < 0.01:  # Doji
                body_height = 0.1
            
            body_bottom = min(open_price, close_price)
            
            painter.drawRect(QRectF(i - w/2, body_bottom, w, body_height))
        
        painter.end()
    
    def paint(self, painter, option, widget):
        """Paint the candlesticks"""
        painter.drawPicture(0, 0, self.picture)
    
    def boundingRect(self):
        """Return bounding rectangle"""
        return QRectF(self.picture.boundingRect())


class ProfessionalCandlestickChart(QWidget):
    """
    Professional candlestick chart with:
    - Real-time updates
    - Zoom and pan
    - Multiple indicators
    - Clean design
    - Volume bars
    """
    
    def __init__(self, symbol: str = "AAPL"):
        super().__init__()
        self.symbol = symbol
        self.data = None
        self.indicators_visible = {
            'sma_20': True,
            'sma_50': True,
            'volume': True,
            'rsi': False,
            'macd': False
        }
        
        self.setup_ui()
    
    def setup_ui(self):
        """Setup chart UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        if not PYQTGRAPH_AVAILABLE:
            label = QLabel("📈 Candlestick Chart\n(pyqtgraph required)\n\npip install pyqtgraph")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("color: #888; font-size: 14pt; padding: 50px;")
            layout.addWidget(label)
            return
        
        # Create toolbar
        toolbar = self.create_toolbar()
        layout.addWidget(toolbar)
        
        # Create graphics layout
        self.graphics_layout = pg.GraphicsLayoutWidget()
        self.graphics_layout.setBackground('#1a1a1d')
        
        # Main price chart
        self.price_plot = self.graphics_layout.addPlot(row=0, col=0)
        self.price_plot.setLabel('left', 'Price ($)', color='#ffffff')
        self.price_plot.showGrid(x=True, y=True, alpha=0.2)
        self.price_plot.setMenuEnabled(False)
        
        # Add legend
        self.legend = self.price_plot.addLegend(offset=(10, 10))
        
        # Volume chart
        self.graphics_layout.nextRow()
        self.volume_plot = self.graphics_layout.addPlot(row=1, col=0)
        self.volume_plot.setLabel('left', 'Volume', color='#ffffff')
        self.volume_plot.setMaximumHeight(150)
        self.volume_plot.showGrid(x=True, y=True, alpha=0.2)
        self.volume_plot.setXLink(self.price_plot)
        
        layout.addWidget(self.graphics_layout)
        
        # Load initial data
        self.load_data()
    
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
            QLabel {
                color: #ffffff;
                background: transparent;
                font-size: 14pt;
                font-weight: bold;
                padding: 0 20px;
            }
        """)
        
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(10, 5, 10, 5)
        
        # Symbol label
        symbol_label = QLabel(f"📊 {self.symbol}")
        layout.addWidget(symbol_label)
        
        # Timeframe buttons
        timeframe_label = QLabel("Timeframe:")
        timeframe_label.setStyleSheet("color: #999; font-size: 10pt; background: transparent;")
        layout.addWidget(timeframe_label)
        
        self.tf_1d = QPushButton("1D")
        self.tf_1d.setCheckable(True)
        self.tf_1d.setChecked(True)
        self.tf_1d.clicked.connect(lambda: self.change_timeframe("1D"))
        
        self.tf_1w = QPushButton("1W")
        self.tf_1w.setCheckable(True)
        self.tf_1w.clicked.connect(lambda: self.change_timeframe("1W"))
        
        self.tf_1m = QPushButton("1M")
        self.tf_1m.setCheckable(True)
        self.tf_1m.clicked.connect(lambda: self.change_timeframe("1M"))
        
        layout.addWidget(self.tf_1d)
        layout.addWidget(self.tf_1w)
        layout.addWidget(self.tf_1m)
        
        # Indicator toggles
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setStyleSheet("background: rgba(255,255,255,0.1);")
        layout.addWidget(sep1)
        
        indicators_label = QLabel("Indicators:")
        indicators_label.setStyleSheet("color: #999; font-size: 10pt; background: transparent;")
        layout.addWidget(indicators_label)
        
        self.sma_btn = QPushButton("SMA 20/50")
        self.sma_btn.setCheckable(True)
        self.sma_btn.setChecked(True)
        self.sma_btn.clicked.connect(self.update_chart)
        
        self.volume_btn = QPushButton("Volume")
        self.volume_btn.setCheckable(True)
        self.volume_btn.setChecked(True)
        self.volume_btn.clicked.connect(lambda: self.toggle_volume())
        
        layout.addWidget(self.sma_btn)
        layout.addWidget(self.volume_btn)
        
        # Refresh button
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setStyleSheet("background: rgba(255,255,255,0.1);")
        layout.addWidget(sep2)
        
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.clicked.connect(self.load_data)
        layout.addWidget(refresh_btn)
        
        layout.addStretch()
        
        return toolbar
    
    def load_data(self, symbol: str = None, period: str = "6mo"):
        """Load market data"""
        if symbol:
            self.symbol = symbol
        
        try:
            from loki.data import get_stock_data
            
            self.data = get_stock_data(self.symbol, period=period, timeframe="1Day")
            
            if len(self.data) > 0:
                self.update_chart()
            else:
                print(f"No data available for {self.symbol}")
        
        except Exception as e:
            print(f"Error loading data: {e}")
            # Generate demo data
            self.data = self._generate_demo_data()
            self.update_chart()
    
    def _generate_demo_data(self) -> pd.DataFrame:
        """Generate demo candlestick data"""
        dates = pd.date_range(end=pd.Timestamp.now(), periods=100, freq='D')
        
        base_price = 150.0
        returns = np.random.normal(0.001, 0.02, len(dates))
        close_prices = base_price * (1 + returns).cumprod()
        
        data = []
        for close in close_prices:
            vol = 0.015
            open_price = close * (1 + np.random.uniform(-vol, vol))
            high = max(open_price, close) * (1 + abs(np.random.normal(0, vol/2)))
            low = min(open_price, close) * (1 - abs(np.random.normal(0, vol/2)))
            volume = np.random.randint(1000000, 10000000)
            
            data.append({
                'open': open_price,
                'high': high,
                'low': low,
                'close': close,
                'volume': volume
            })
        
        return pd.DataFrame(data, index=dates)
    
    def update_chart(self):
        """Update chart with current data"""
        if self.data is None or not PYQTGRAPH_AVAILABLE:
            return
        
        # Clear plots
        self.price_plot.clear()
        self.volume_plot.clear()
        
        # Plot candlesticks
        candlestick = CandlestickItem(self.data)
        self.price_plot.addItem(candlestick)
        
        # Plot indicators
        if self.sma_btn.isChecked():
            self.plot_moving_averages()
        
        # Plot volume
        if self.volume_btn.isChecked():
            self.plot_volume()
        
        # Update axis
        self.price_plot.setXRange(0, len(self.data))
        
        # Add current price label
        current_price = self.data['close'].iloc[-1]
        prev_price = self.data['close'].iloc[-2]
        change = current_price - prev_price
        change_pct = (change / prev_price) * 100
        
        color = "#4ec9b0" if change >= 0 else "#f48771"
        arrow = "▲" if change >= 0 else "▼"
        
        price_text = f"${current_price:.2f} {arrow} {change_pct:+.2f}%"
        
        # Update price in title
        self.price_plot.setTitle(price_text, color=color, size='12pt')
    
    def plot_moving_averages(self):
        """Plot SMA 20 and 50"""
        x = np.arange(len(self.data))
        
        # SMA 20
        sma_20 = self.data['close'].rolling(20).mean()
        self.price_plot.plot(
            x, sma_20,
            pen=pg.mkPen('#ffa500', width=2),
            name='SMA 20'
        )
        
        # SMA 50
        sma_50 = self.data['close'].rolling(50).mean()
        self.price_plot.plot(
            x, sma_50,
            pen=pg.mkPen('#00d4ff', width=2),
            name='SMA 50'
        )
    
    def plot_volume(self):
        """Plot volume bars"""
        x = np.arange(len(self.data))
        
        # Color by price movement
        for i in range(len(self.data)):
            row = self.data.iloc[i]
            
            if row['close'] >= row['open']:
                color = '#4ec9b0'  # Green
            else:
                color = '#f48771'  # Red
            
            bar = pg.BarGraphItem(
                x=[i],
                height=[row['volume']],
                width=0.8,
                brush=color,
                pen=None
            )
            self.volume_plot.addItem(bar)
    
    def toggle_volume(self):
        """Toggle volume chart visibility"""
        if self.volume_btn.isChecked():
            self.volume_plot.show()
        else:
            self.volume_plot.hide()
    
    def change_timeframe(self, timeframe: str):
        """Change chart timeframe"""
        # Uncheck all timeframe buttons
        self.tf_1d.setChecked(timeframe == "1D")
        self.tf_1w.setChecked(timeframe == "1W")
        self.tf_1m.setChecked(timeframe == "1M")
        
        # Reload data with new timeframe
        period_map = {
            "1D": "6mo",
            "1W": "2y",
            "1M": "5y"
        }
        self.load_data(period=period_map.get(timeframe, "6mo"))


def main():
    """Test the candlestick chart"""
    if not PYQT_AVAILABLE:
        print("PyQt6 required: pip install PyQt6")
        return
    
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    # Dark palette
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(26, 26, 29))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(204, 204, 204))
    app.setPalette(palette)
    
    # Create window
    window = QMainWindow()
    window.setWindowTitle("Loki - Professional Candlestick Chart")
    window.resize(1200, 700)
    
    chart = ProfessionalCandlestickChart("AAPL")
    window.setCentralWidget(chart)
    
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
