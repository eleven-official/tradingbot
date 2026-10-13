"""
Loki Performance Analytics Dashboard
Comprehensive performance tracking with equity curve, drawdown, Sharpe ratio, and more
"""
import sys
import numpy as np
import pandas as pd
from typing import List, Dict, Tuple
from datetime import datetime, timedelta

try:
    from PyQt6.QtWidgets import *
    from PyQt6.QtCore import *
    from PyQt6.QtGui import *
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

try:
    import pyqtgraph as pg
    PYQTGRAPH_AVAILABLE = True
except ImportError:
    PYQTGRAPH_AVAILABLE = False


class PerformanceMetricsCard(QFrame):
    """Card displaying a single performance metric"""
    
    def __init__(self, title: str, value: str, subtitle: str = "", color: str = "#00d4ff"):
        super().__init__()
        self.setup_ui(title, value, subtitle, color)
    
    def setup_ui(self, title: str, value: str, subtitle: str, color: str):
        """Setup metric card"""
        self.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(45, 45, 48, 0.6),
                    stop:1 rgba(35, 35, 38, 0.6)
                );
                border-radius: 12px;
                border: 1px solid rgba(255, 255, 255, 0.1);
                padding: 15px;
            }}
            QFrame:hover {{
                border: 1px solid {color};
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(50, 50, 53, 0.7),
                    stop:1 rgba(40, 40, 43, 0.7)
                );
            }}
        """)
        
        layout = QVBoxLayout(self)
        
        # Title
        title_label = QLabel(title)
        title_label.setFont(QFont("Segoe UI", 10))
        title_label.setStyleSheet("color: #9e9e9e; background: transparent;")
        
        # Value
        value_label = QLabel(value)
        value_label.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        value_label.setStyleSheet(f"color: {color}; background: transparent;")
        
        # Subtitle
        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setFont(QFont("Segoe UI", 9))
            subtitle_label.setStyleSheet("color: #888; background: transparent;")
            layout.addWidget(subtitle_label)
        
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        layout.addStretch()
        
        self.setMinimumHeight(120)


class EquityCurveChart(QWidget):
    """Equity curve chart with multiple series"""
    
    def __init__(self):
        super().__init__()
        self.setup_ui()
    
    def setup_ui(self):
        """Setup equity curve chart"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        if not PYQTGRAPH_AVAILABLE:
            label = QLabel("📈 Equity Curve\n(pyqtgraph required)")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label)
            return
        
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('#1a1a1d')
        self.plot_widget.setTitle("Portfolio Equity Curve", color='#ffffff', size='14pt')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setLabel('left', 'Portfolio Value ($)', color='#ffffff')
        self.plot_widget.setLabel('bottom', 'Date', color='#ffffff')
        self.plot_widget.addLegend()
        
        # Style axes
        self.plot_widget.getAxis('left').setTextPen('#ffffff')
        self.plot_widget.getAxis('bottom').setTextPen('#ffffff')
        
        layout.addWidget(self.plot_widget)
        
        # Generate demo data
        self.update_chart()
    
    def update_chart(self):
        """Update equity curve with new data"""
        if not PYQTGRAPH_AVAILABLE:
            return
        
        # Generate demo equity curve
        days = 252  # Trading days in a year
        dates = pd.date_range(end=datetime.now(), periods=days, freq='B')
        
        # Portfolio equity (with growth and volatility)
        returns = np.random.normal(0.0008, 0.015, days)  # 20% annual return, 15% vol
        equity = 100000 * (1 + returns).cumprod()
        
        # Benchmark (SPY)
        benchmark_returns = np.random.normal(0.0006, 0.012, days)  # 15% return, 12% vol
        benchmark = 100000 * (1 + benchmark_returns).cumprod()
        
        x = np.arange(len(equity))
        
        # Plot equity curve
        self.plot_widget.plot(
            x, equity,
            pen=pg.mkPen('#4ec9b0', width=2),
            name='Portfolio'
        )
        
        # Plot benchmark
        self.plot_widget.plot(
            x, benchmark,
            pen=pg.mkPen('#ffa500', width=2, style=Qt.PenStyle.DashLine),
            name='Benchmark (SPY)'
        )


class DrawdownChart(QWidget):
    """Drawdown chart showing peak-to-trough declines"""
    
    def __init__(self):
        super().__init__()
        self.setup_ui()
    
    def setup_ui(self):
        """Setup drawdown chart"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        if not PYQTGRAPH_AVAILABLE:
            label = QLabel("📉 Drawdown\n(pyqtgraph required)")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label)
            return
        
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('#1a1a1d')
        self.plot_widget.setTitle("Drawdown Analysis", color='#ffffff', size='14pt')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setLabel('left', 'Drawdown (%)', color='#ffffff')
        self.plot_widget.setLabel('bottom', 'Date', color='#ffffff')
        
        layout.addWidget(self.plot_widget)
        
        self.update_chart()
    
    def update_chart(self):
        """Update drawdown chart"""
        if not PYQTGRAPH_AVAILABLE:
            return
        
        # Generate demo drawdown
        days = 252
        returns = np.random.normal(0.0008, 0.015, days)
        equity = 100000 * (1 + returns).cumprod()
        
        # Calculate drawdown
        running_max = np.maximum.accumulate(equity)
        drawdown = (equity - running_max) / running_max * 100
        
        x = np.arange(len(drawdown))
        
        # Fill area below zero
        self.plot_widget.plot(
            x, drawdown,
            pen=pg.mkPen('#f48771', width=2),
            fillLevel=0,
            brush=(244, 135, 113, 100)
        )


class ReturnsDistributionChart(QWidget):
    """Histogram of daily returns distribution"""
    
    def __init__(self):
        super().__init__()
        self.setup_ui()
    
    def setup_ui(self):
        """Setup returns distribution chart"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        if not PYQTGRAPH_AVAILABLE:
            label = QLabel("📊 Returns Distribution\n(pyqtgraph required)")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label)
            return
        
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('#1a1a1d')
        self.plot_widget.setTitle("Daily Returns Distribution", color='#ffffff', size='14pt')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setLabel('left', 'Frequency', color='#ffffff')
        self.plot_widget.setLabel('bottom', 'Daily Return (%)', color='#ffffff')
        
        layout.addWidget(self.plot_widget)
        
        self.update_chart()
    
    def update_chart(self):
        """Update returns distribution"""
        if not PYQTGRAPH_AVAILABLE:
            return
        
        # Generate returns
        returns = np.random.normal(0.08, 1.5, 252)  # Daily returns in %
        
        # Create histogram
        hist, bin_edges = np.histogram(returns, bins=30)
        
        # Create bar graph
        bar_width = bin_edges[1] - bin_edges[0]
        
        colors = ['#4ec9b0' if edge >= 0 else '#f48771' for edge in bin_edges[:-1]]
        
        for i in range(len(hist)):
            bar = pg.BarGraphItem(
                x=[bin_edges[i] + bar_width/2],
                height=[hist[i]],
                width=bar_width * 0.9,
                brush=colors[i],
                pen=None
            )
            self.plot_widget.addItem(bar)


class RollingSharpeChart(QWidget):
    """Rolling Sharpe ratio chart"""
    
    def __init__(self):
        super().__init__()
        self.setup_ui()
    
    def setup_ui(self):
        """Setup Sharpe ratio chart"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        if not PYQTGRAPH_AVAILABLE:
            label = QLabel("📈 Rolling Sharpe Ratio\n(pyqtgraph required)")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label)
            return
        
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('#1a1a1d')
        self.plot_widget.setTitle("Rolling 60-Day Sharpe Ratio", color='#ffffff', size='14pt')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setLabel('left', 'Sharpe Ratio', color='#ffffff')
        self.plot_widget.setLabel('bottom', 'Date', color='#ffffff')
        
        # Add reference line at 1.0 (good Sharpe)
        self.plot_widget.addLine(y=1.0, pen=pg.mkPen('#ffa500', width=1, style=Qt.PenStyle.DashLine))
        
        layout.addWidget(self.plot_widget)
        
        self.update_chart()
    
    def update_chart(self):
        """Update Sharpe ratio chart"""
        if not PYQTGRAPH_AVAILABLE:
            return
        
        # Generate returns
        days = 252
        returns = np.random.normal(0.0008, 0.015, days)
        
        # Calculate rolling Sharpe (60-day window)
        window = 60
        rolling_sharpe = []
        
        for i in range(window, len(returns)):
            window_returns = returns[i-window:i]
            sharpe = np.mean(window_returns) / np.std(window_returns) * np.sqrt(252)
            rolling_sharpe.append(sharpe)
        
        x = np.arange(window, len(returns))
        
        # Color line based on value
        self.plot_widget.plot(
            x, rolling_sharpe,
            pen=pg.mkPen('#00d4ff', width=2)
        )


class WinRateAnalysis(QWidget):
    """Win rate and profit factor analysis"""
    
    def __init__(self):
        super().__init__()
        self.setup_ui()
    
    def setup_ui(self):
        """Setup win rate visualization"""
        layout = QVBoxLayout(self)
        
        # Title
        title = QLabel("🎯 Trade Analysis")
        title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        title.setStyleSheet("color: #ffffff; background: transparent;")
        layout.addWidget(title)
        
        # Stats grid
        stats_layout = QGridLayout()
        
        # Sample stats
        stats = [
            ("Total Trades", "156", "#00d4ff"),
            ("Winning Trades", "107", "#4ec9b0"),
            ("Losing Trades", "49", "#f48771"),
            ("Win Rate", "68.6%", "#4ec9b0"),
            ("Avg Win", "$487", "#4ec9b0"),
            ("Avg Loss", "$-234", "#f48771"),
            ("Profit Factor", "2.08", "#00d4ff"),
            ("Expectancy", "$253", "#4ec9b0")
        ]
        
        for i, (label, value, color) in enumerate(stats):
            row = i // 2
            col = i % 2
            
            card = QFrame()
            card.setStyleSheet(f"""
                QFrame {{
                    background: rgba(45,45,48,0.5);
                    border-left: 3px solid {color};
                    border-radius: 8px;
                    padding: 10px;
                }}
            """)
            
            card_layout = QVBoxLayout(card)
            
            label_widget = QLabel(label)
            label_widget.setStyleSheet("color: #9e9e9e; background: transparent;")
            label_widget.setFont(QFont("Segoe UI", 9))
            
            value_widget = QLabel(value)
            value_widget.setStyleSheet(f"color: {color}; background: transparent;")
            value_widget.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
            
            card_layout.addWidget(label_widget)
            card_layout.addWidget(value_widget)
            
            stats_layout.addWidget(card, row, col)
        
        layout.addLayout(stats_layout)
        
        # Win/Loss pie chart (if pyqtgraph available)
        if PYQTGRAPH_AVAILABLE:
            self.add_pie_chart(layout, 107, 49)
    
    def add_pie_chart(self, layout: QVBoxLayout, wins: int, losses: int):
        """Add simple win/loss visualization"""
        chart_widget = QWidget()
        chart_layout = QHBoxLayout(chart_widget)
        
        total = wins + losses
        win_pct = wins / total * 100
        loss_pct = losses / total * 100
        
        # Win bar
        win_bar = QProgressBar()
        win_bar.setRange(0, 100)
        win_bar.setValue(int(win_pct))
        win_bar.setFormat(f"Wins: {win_pct:.1f}%")
        win_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                border-radius: 8px;
                background: rgba(255,255,255,0.1);
                text-align: center;
                color: white;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background: #4ec9b0;
                border-radius: 8px;
            }
        """)
        win_bar.setFixedHeight(40)
        
        # Loss bar
        loss_bar = QProgressBar()
        loss_bar.setRange(0, 100)
        loss_bar.setValue(int(loss_pct))
        loss_bar.setFormat(f"Losses: {loss_pct:.1f}%")
        loss_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                border-radius: 8px;
                background: rgba(255,255,255,0.1);
                text-align: center;
                color: white;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background: #f48771;
                border-radius: 8px;
            }
        """)
        loss_bar.setFixedHeight(40)
        
        chart_layout.addWidget(win_bar)
        chart_layout.addWidget(loss_bar)
        
        layout.addWidget(chart_widget)


class PerformanceAnalyticsDashboard(QWidget):
    """Complete performance analytics dashboard"""
    
    def __init__(self):
        super().__init__()
        self.setup_ui()
    
    def setup_ui(self):
        """Setup dashboard UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Top metrics row
        metrics_layout = QHBoxLayout()
        
        self.total_return_card = PerformanceMetricsCard(
            "Total Return", "+27.5%", "Since Inception", "#4ec9b0"
        )
        self.sharpe_card = PerformanceMetricsCard(
            "Sharpe Ratio", "1.85", "Risk-Adjusted", "#00d4ff"
        )
        self.max_dd_card = PerformanceMetricsCard(
            "Max Drawdown", "-8.3%", "Peak to Trough", "#f48771"
        )
        self.alpha_card = PerformanceMetricsCard(
            "Alpha", "+4.2%", "vs Benchmark", "#9370db"
        )
        
        metrics_layout.addWidget(self.total_return_card)
        metrics_layout.addWidget(self.sharpe_card)
        metrics_layout.addWidget(self.max_dd_card)
        metrics_layout.addWidget(self.alpha_card)
        
        # Charts grid
        charts_grid = QGridLayout()
        
        self.equity_curve = EquityCurveChart()
        self.drawdown_chart = DrawdownChart()
        self.returns_dist = ReturnsDistributionChart()
        self.sharpe_chart = RollingSharpeChart()
        
        charts_grid.addWidget(self.equity_curve, 0, 0, 1, 2)
        charts_grid.addWidget(self.drawdown_chart, 1, 0)
        charts_grid.addWidget(self.returns_dist, 1, 1)
        charts_grid.addWidget(self.sharpe_chart, 2, 0)
        charts_grid.addWidget(WinRateAnalysis(), 2, 1)
        
        layout.addLayout(metrics_layout)
        layout.addLayout(charts_grid)


def main():
    """Demo performance analytics dashboard"""
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
    
    window = QMainWindow()
    window.setWindowTitle("Loki Performance Analytics")
    window.resize(1400, 900)
    
    dashboard = PerformanceAnalyticsDashboard()
    
    # Add scroll area
    scroll = QScrollArea()
    scroll.setWidget(dashboard)
    scroll.setWidgetResizable(True)
    scroll.setStyleSheet("QScrollArea { border: none; }")
    
    window.setCentralWidget(scroll)
    window.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
