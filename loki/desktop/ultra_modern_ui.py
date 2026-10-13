"""
Loki Ultra-Modern UI - Stunning Interface with Glassmorphism
Professional trading interface with advanced visualizations
"""
import sys
from typing import Optional, Dict, List
from datetime import datetime
import numpy as np

try:
    from PyQt6.QtWidgets import *
    from PyQt6.QtCore import *
    from PyQt6.QtGui import *
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

if not PYQT_AVAILABLE:
    raise ImportError("PyQt6 is required: pip install PyQt6")


try:
    import pyqtgraph as pg
    PYQTGRAPH_AVAILABLE = True
except ImportError:
    PYQTGRAPH_AVAILABLE = False


class GlassCard(QFrame):
    """Modern glassmorphism card widget"""
    
    def __init__(self, title: str = "", color: str = "#007acc"):
        super().__init__()
        self.color = color
        self.setup_ui(title)
        
    def setup_ui(self, title: str):
        """Setup glassmorphism UI"""
        self.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(45, 45, 48, 0.7),
                    stop:1 rgba(30, 30, 33, 0.7)
                );
                border-radius: 16px;
                border: 1px solid rgba(255, 255, 255, 0.1);
                backdrop-filter: blur(10px);
                padding: 20px;
            }}
            QFrame:hover {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(50, 50, 53, 0.75),
                    stop:1 rgba(35, 35, 38, 0.75)
                );
                border: 1px solid {self.color};
            }}
        """)
        
        layout = QVBoxLayout(self)
        
        if title:
            title_label = QLabel(title)
            title_label.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
            title_label.setStyleSheet(f"""
                color: {self.color};
                background: transparent;
                padding: 0;
                margin-bottom: 10px;
            """)
            layout.addWidget(title_label)


class MetricCard(GlassCard):
    """Animated metric display card"""
    
    def __init__(self, title: str, value: str, change: str, 
                 icon: str = "📊", color: str = "#007acc"):
        super().__init__("", color)
        
        layout = self.layout()
        
        # Header with icon
        header = QHBoxLayout()
        icon_label = QLabel(icon)
        icon_label.setFont(QFont("Segoe UI", 24))
        icon_label.setStyleSheet("background: transparent;")
        
        title_label = QLabel(title)
        title_label.setFont(QFont("Segoe UI", 11))
        title_label.setStyleSheet("color: #9e9e9e; background: transparent;")
        
        header.addWidget(icon_label)
        header.addWidget(title_label)
        header.addStretch()
        
        # Value with animation
        self.value_label = QLabel(value)
        self.value_label.setFont(QFont("Segoe UI", 32, QFont.Weight.Bold))
        self.value_label.setStyleSheet(f"""
            color: {color};
            background: transparent;
            padding: 5px 0;
        """)
        
        # Change indicator
        self.change_label = QLabel(change)
        self.change_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        change_color = "#4ec9b0" if "+" in change or "↑" in change else "#f48771"
        self.change_label.setStyleSheet(f"""
            color: {change_color};
            background: transparent;
        """)
        
        layout.addLayout(header)
        layout.addWidget(self.value_label)
        layout.addWidget(self.change_label)
        layout.addStretch()
        
        self.setMinimumHeight(160)
        
        # Add pulsing animation
        self.animation = QPropertyAnimation(self, b"geometry")
        self.animation.setDuration(2000)
        self.animation.setLoopCount(-1)
    
    def update_value(self, value: str, change: str):
        """Update metric with smooth animation"""
        self.value_label.setText(value)
        self.change_label.setText(change)
        
        # Animate color pulse
        effect = QGraphicsOpacityEffect()
        self.value_label.setGraphicsEffect(effect)
        
        anim = QPropertyAnimation(effect, b"opacity")
        anim.setDuration(500)
        anim.setStartValue(0.5)
        anim.setEndValue(1.0)
        anim.start()


class LiveChartWidget(QWidget):
    """Advanced live chart with multiple indicators"""
    
    def __init__(self, title: str = "Price Chart"):
        super().__init__()
        self.title = title
        self.data_points = []
        self.setup_ui()
    
    def setup_ui(self):
        """Setup chart UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        if PYQTGRAPH_AVAILABLE:
            # Create plot widget
            self.plot_widget = pg.PlotWidget()
            self.plot_widget.setBackground('#1e1e1e')
            self.plot_widget.setTitle(self.title, color='#ffffff', size='14pt')
            self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
            self.plot_widget.setLabel('left', 'Price', color='#ffffff')
            self.plot_widget.setLabel('bottom', 'Time', color='#ffffff')
            
            # Style the plot
            self.plot_widget.getAxis('left').setTextPen('#ffffff')
            self.plot_widget.getAxis('bottom').setTextPen('#ffffff')
            
            # Create multiple data series
            self.price_curve = self.plot_widget.plot(
                pen=pg.mkPen(color='#00d4ff', width=2),
                name='Price'
            )
            self.sma_curve = self.plot_widget.plot(
                pen=pg.mkPen(color='#ffa500', width=1, style=Qt.PenStyle.DashLine),
                name='SMA'
            )
            self.ema_curve = self.plot_widget.plot(
                pen=pg.mkPen(color='#4ec9b0', width=1, style=Qt.PenStyle.DotLine),
                name='EMA'
            )
            
            # Add legend
            self.plot_widget.addLegend()
            
            layout.addWidget(self.plot_widget)
        else:
            # Fallback to simple label
            label = QLabel("📈 Chart (pyqtgraph required)")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("color: #888; font-size: 14pt;")
            layout.addWidget(label)
    
    def update_data(self, price_data: List[float], sma_data: List[float], ema_data: List[float]):
        """Update chart with new data"""
        if PYQTGRAPH_AVAILABLE and hasattr(self, 'price_curve'):
            x = list(range(len(price_data)))
            self.price_curve.setData(x, price_data)
            if sma_data:
                self.sma_curve.setData(x[-len(sma_data):], sma_data)
            if ema_data:
                self.ema_curve.setData(x[-len(ema_data):], ema_data)


class AIReasoningPanel(GlassCard):
    """Real-time AI reasoning explanation panel"""
    
    def __init__(self):
        super().__init__("🧠 AI Reasoning Engine", "#9370db")
        
        layout = self.layout()
        
        # Thinking indicator
        thinking_layout = QHBoxLayout()
        self.thinking_label = QLabel("💭 Analyzing...")
        self.thinking_label.setFont(QFont("Segoe UI", 11))
        self.thinking_label.setStyleSheet("color: #4ec9b0; background: transparent;")
        
        self.confidence_label = QLabel("Confidence: --")
        self.confidence_label.setFont(QFont("Segoe UI", 10))
        self.confidence_label.setStyleSheet("color: #9e9e9e; background: transparent;")
        
        thinking_layout.addWidget(self.thinking_label)
        thinking_layout.addStretch()
        thinking_layout.addWidget(self.confidence_label)
        
        # Confidence meter
        self.confidence_bar = QProgressBar()
        self.confidence_bar.setRange(0, 100)
        self.confidence_bar.setValue(0)
        self.confidence_bar.setTextVisible(False)
        self.confidence_bar.setFixedHeight(8)
        self.confidence_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                border-radius: 4px;
                background: rgba(255,255,255,0.1);
            }
            QProgressBar::chunk {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4ec9b0,
                    stop:1 #00d4ff
                );
                border-radius: 4px;
            }
        """)
        
        # Reasoning text
        self.reasoning_text = QTextEdit()
        self.reasoning_text.setReadOnly(True)
        self.reasoning_text.setMaximumHeight(150)
        self.reasoning_text.setStyleSheet("""
            QTextEdit {
                background: rgba(0,0,0,0.3);
                border: 1px solid rgba(255,255,255,0.05);
                border-radius: 8px;
                color: #cccccc;
                font-size: 10pt;
                padding: 10px;
            }
        """)
        
        # Decision indicators
        self.decision_label = QLabel("Decision: ANALYZING")
        self.decision_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.decision_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.decision_label.setStyleSheet("""
            color: #ffa500;
            background: rgba(255,165,0,0.1);
            border-radius: 8px;
            padding: 10px;
            margin-top: 10px;
        """)
        
        layout.addLayout(thinking_layout)
        layout.addWidget(self.confidence_bar)
        layout.addWidget(self.reasoning_text)
        layout.addWidget(self.decision_label)
        
        # Start thinking animation
        self.start_thinking_animation()
    
    def start_thinking_animation(self):
        """Animate thinking indicator"""
        self.thinking_timer = QTimer()
        self.thinking_states = ["💭 Analyzing.", "💭 Analyzing..", "💭 Analyzing..."]
        self.thinking_index = 0
        
        def update_thinking():
            self.thinking_label.setText(self.thinking_states[self.thinking_index])
            self.thinking_index = (self.thinking_index + 1) % len(self.thinking_states)
        
        self.thinking_timer.timeout.connect(update_thinking)
        self.thinking_timer.start(500)
    
    def update_reasoning(self, decision: str, confidence: float, reasoning: List[str]):
        """Update AI reasoning display"""
        # Update confidence
        self.confidence_label.setText(f"Confidence: {confidence:.1f}%")
        self.confidence_bar.setValue(int(confidence))
        
        # Update reasoning text
        reasoning_html = "<br>".join([f"• {r}" for r in reasoning])
        self.reasoning_text.setHtml(f"<div style='line-height: 1.5;'>{reasoning_html}</div>")
        
        # Update decision
        self.decision_label.setText(f"Decision: {decision}")
        
        # Color based on decision
        if "BUY" in decision:
            color = "#4ec9b0"
            bg = "rgba(78,201,176,0.15)"
        elif "SELL" in decision:
            color = "#f48771"
            bg = "rgba(244,135,113,0.15)"
        else:
            color = "#ffa500"
            bg = "rgba(255,165,0,0.1)"
        
        self.decision_label.setStyleSheet(f"""
            color: {color};
            background: {bg};
            border-radius: 8px;
            padding: 10px;
            margin-top: 10px;
            font-weight: bold;
        """)


class MarketRegimeWidget(GlassCard):
    """Market regime and trend indicator"""
    
    def __init__(self):
        super().__init__("📈 Market Regime", "#00d4ff")
        
        layout = self.layout()
        
        # Regime display
        self.regime_label = QLabel("ANALYZING")
        self.regime_label.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        self.regime_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.regime_label.setStyleSheet("""
            color: #00d4ff;
            background: rgba(0,212,255,0.1);
            border-radius: 12px;
            padding: 15px;
        """)
        
        # Trend strength indicator
        trend_layout = QHBoxLayout()
        trend_layout.addWidget(QLabel("Trend Strength:"))
        
        self.trend_bar = QProgressBar()
        self.trend_bar.setRange(0, 100)
        self.trend_bar.setValue(0)
        self.trend_bar.setFixedHeight(20)
        self.trend_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid rgba(255,255,255,0.2);
                border-radius: 10px;
                background: rgba(0,0,0,0.3);
                text-align: center;
                color: white;
            }
            QProgressBar::chunk {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #f48771,
                    stop:0.5 #ffa500,
                    stop:1 #4ec9b0
                );
                border-radius: 10px;
            }
        """)
        
        trend_layout.addWidget(self.trend_bar)
        
        # Momentum indicator
        self.momentum_label = QLabel("Momentum: --")
        self.momentum_label.setStyleSheet("color: #9e9e9e; background: transparent;")
        
        # Volatility indicator
        self.volatility_label = QLabel("Volatility: --")
        self.volatility_label.setStyleSheet("color: #9e9e9e; background: transparent;")
        
        layout.addWidget(self.regime_label)
        layout.addLayout(trend_layout)
        layout.addWidget(self.momentum_label)
        layout.addWidget(self.volatility_label)
    
    def update_regime(self, regime: str, trend_strength: int, 
                      momentum: float, volatility: float):
        """Update market regime display"""
        self.regime_label.setText(regime.upper())
        self.trend_bar.setValue(trend_strength)
        self.trend_bar.setFormat(f"{trend_strength}%")
        
        # Momentum with emoji
        momentum_emoji = "🚀" if momentum > 50 else "📉" if momentum < -50 else "→"
        self.momentum_label.setText(f"Momentum: {momentum_emoji} {momentum:.1f}")
        
        # Volatility with emoji
        vol_emoji = "⚡" if volatility > 75 else "📊" if volatility > 50 else "😴"
        self.volatility_label.setText(f"Volatility: {vol_emoji} {volatility:.1f}%")
        
        # Color regime based on type
        if "BULL" in regime:
            color, bg = "#4ec9b0", "rgba(78,201,176,0.15)"
        elif "BEAR" in regime:
            color, bg = "#f48771", "rgba(244,135,113,0.15)"
        else:
            color, bg = "#ffa500", "rgba(255,165,0,0.1)"
        
        self.regime_label.setStyleSheet(f"""
            color: {color};
            background: {bg};
            border-radius: 12px;
            padding: 15px;
        """)


class NotificationBadge(QLabel):
    """Animated notification badge"""
    
    def __init__(self, text: str = "1", parent=None):
        super().__init__(text, parent)
        self.setFixedSize(24, 24)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("""
            background: #f44336;
            color: white;
            border-radius: 12px;
            font-weight: bold;
            font-size: 10pt;
        """)
        
        # Pulse animation
        self.effect = QGraphicsOpacityEffect()
        self.setGraphicsEffect(self.effect)
        
        self.animation = QPropertyAnimation(self.effect, b"opacity")
        self.animation.setDuration(1000)
        self.animation.setStartValue(0.5)
        self.animation.setEndValue(1.0)
        self.animation.setLoopCount(-1)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        self.animation.start()


class LokiUltraModernUI(QMainWindow):
    """Ultra-modern Loki trading interface"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Loki AI Trading Platform")
        self.setMinimumSize(1400, 900)
        
        self.setup_ui()
        self.apply_dark_theme()
        
        # Start update timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_live_data)
        self.update_timer.start(2000)  # Update every 2 seconds
    
    def setup_ui(self):
        """Setup the main UI"""
        central = QWidget()
        self.setCentralWidget(central)
        
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Top metrics row
        metrics_layout = QHBoxLayout()
        
        self.portfolio_card = MetricCard(
            "Portfolio Value", "$125,450.00", "+$2,450.00 (+1.99%)",
            "💰", "#4ec9b0"
        )
        self.daily_pnl_card = MetricCard(
            "Daily P&L", "+$1,234.56", "+0.99% Today",
            "📈", "#4ec9b0"
        )
        self.win_rate_card = MetricCard(
            "Win Rate", "68.5%", "↑ 2.3% vs Last Week",
            "🎯", "#00d4ff"
        )
        self.ai_status_card = MetricCard(
            "AI Status", "ACTIVE", "🟢 Trading",
            "🤖", "#9370db"
        )
        
        metrics_layout.addWidget(self.portfolio_card)
        metrics_layout.addWidget(self.daily_pnl_card)
        metrics_layout.addWidget(self.win_rate_card)
        metrics_layout.addWidget(self.ai_status_card)
        
        # Middle row - Charts and AI
        middle_layout = QHBoxLayout()
        
        # Left: Charts
        charts_container = QWidget()
        charts_layout = QVBoxLayout(charts_container)
        
        self.price_chart = LiveChartWidget("Price & Indicators")
        self.volume_chart = LiveChartWidget("Volume")
        self.volume_chart.setMaximumHeight(200)
        
        charts_layout.addWidget(self.price_chart, stretch=3)
        charts_layout.addWidget(self.volume_chart, stretch=1)
        
        # Right: AI panels
        ai_container = QWidget()
        ai_layout = QVBoxLayout(ai_container)
        
        self.ai_reasoning = AIReasoningPanel()
        self.market_regime = MarketRegimeWidget()
        
        ai_layout.addWidget(self.ai_reasoning, stretch=2)
        ai_layout.addWidget(self.market_regime, stretch=1)
        
        middle_layout.addWidget(charts_container, stretch=2)
        middle_layout.addWidget(ai_container, stretch=1)
        
        # Bottom tabs
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: none;
                background: transparent;
            }
            QTabBar::tab {
                background: rgba(45,45,48,0.5);
                color: #9e9e9e;
                padding: 10px 20px;
                margin-right: 5px;
                border-radius: 8px 8px 0 0;
            }
            QTabBar::tab:selected {
                background: rgba(0,122,204,0.3);
                color: #00d4ff;
            }
            QTabBar::tab:hover {
                background: rgba(60,60,63,0.7);
            }
        """)
        
        # Positions tab
        positions_tab = self.create_positions_tab()
        self.tabs.addTab(positions_tab, "📊 Positions")
        
        # Orders tab
        orders_tab = self.create_orders_tab()
        self.tabs.addTab(orders_tab, "📋 Orders")
        
        # Analytics tab
        analytics_tab = self.create_analytics_tab()
        self.tabs.addTab(analytics_tab, "📈 Analytics")
        
        # AI Log tab
        ai_log_tab = self.create_ai_log_tab()
        self.tabs.addTab(ai_log_tab, "🤖 AI Decisions")
        
        # Add all to main layout
        main_layout.addLayout(metrics_layout)
        main_layout.addLayout(middle_layout, stretch=1)
        main_layout.addWidget(self.tabs)
    
    def create_positions_tab(self) -> QWidget:
        """Create positions table tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        table = QTableWidget()
        table.setColumnCount(7)
        table.setHorizontalHeaderLabels([
            "Symbol", "Qty", "Entry", "Current", "P&L", "P&L %", "Actions"
        ])
        table.horizontalHeader().setStretchLastSection(True)
        
        # Style the table
        table.setStyleSheet("""
            QTableWidget {
                background: rgba(30,30,33,0.5);
                gridline-color: rgba(255,255,255,0.1);
                color: #cccccc;
                border: none;
            }
            QTableWidget::item {
                padding: 10px;
            }
            QHeaderView::section {
                background: rgba(45,45,48,0.7);
                color: #00d4ff;
                padding: 10px;
                border: none;
                font-weight: bold;
            }
        """)
        
        layout.addWidget(table)
        return widget
    
    def create_orders_tab(self) -> QWidget:
        """Create orders tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels([
            "Time", "Symbol", "Type", "Side", "Qty", "Status"
        ])
        table.horizontalHeader().setStretchLastSection(True)
        table.setStyleSheet("""
            QTableWidget {
                background: rgba(30,30,33,0.5);
                gridline-color: rgba(255,255,255,0.1);
                color: #cccccc;
                border: none;
            }
            QHeaderView::section {
                background: rgba(45,45,48,0.7);
                color: #00d4ff;
                padding: 10px;
                border: none;
                font-weight: bold;
            }
        """)
        
        layout.addWidget(table)
        return widget
    
    def create_analytics_tab(self) -> QWidget:
        """Create analytics dashboard"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Performance charts
        grid = QGridLayout()
        
        if PYQTGRAPH_AVAILABLE:
            equity_chart = pg.PlotWidget(title="Equity Curve")
            equity_chart.setBackground('#1e1e1e')
            grid.addWidget(equity_chart, 0, 0)
            
            drawdown_chart = pg.PlotWidget(title="Drawdown")
            drawdown_chart.setBackground('#1e1e1e')
            grid.addWidget(drawdown_chart, 0, 1)
            
            returns_chart = pg.PlotWidget(title="Daily Returns")
            returns_chart.setBackground('#1e1e1e')
            grid.addWidget(returns_chart, 1, 0)
            
            sharpe_chart = pg.PlotWidget(title="Rolling Sharpe Ratio")
            sharpe_chart.setBackground('#1e1e1e')
            grid.addWidget(sharpe_chart, 1, 1)
        else:
            label = QLabel("📊 Analytics (pyqtgraph required)")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(label, 0, 0, 2, 2)
        
        layout.addLayout(grid)
        return widget
    
    def create_ai_log_tab(self) -> QWidget:
        """Create AI decision log"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        log = QTextEdit()
        log.setReadOnly(True)
        log.setStyleSheet("""
            QTextEdit {
                background: rgba(30,30,33,0.5);
                color: #cccccc;
                border: none;
                font-family: 'Consolas', monospace;
                font-size: 10pt;
                padding: 10px;
            }
        """)
        
        # Add sample log entries
        log.append("🤖 [12:34:56] AI Agent started")
        log.append("📊 [12:35:01] Analyzing AAPL - Strong bullish momentum detected")
        log.append("✓ [12:35:03] Decision: BUY AAPL, Confidence: 85.3%")
        log.append("💰 [12:35:10] Order executed: Bought 100 shares @ $175.50")
        
        layout.addWidget(log)
        return widget
    
    def apply_dark_theme(self):
        """Apply modern dark theme"""
        self.setStyleSheet("""
            QMainWindow {
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1a1a1d,
                    stop:1 #0d0d0f
                );
            }
            QWidget {
                color: #cccccc;
                font-family: 'Segoe UI', Arial;
            }
            QLabel {
                background: transparent;
            }
            QPushButton {
                background: rgba(0,122,204,0.8);
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(0,122,204,1.0);
            }
            QPushButton:pressed {
                background: rgba(0,100,180,1.0);
            }
        """)
    
    def update_live_data(self):
        """Update live data (demo)"""
        import random
        
        # Generate demo data
        price_data = [100 + random.gauss(0, 2) + i * 0.1 for i in range(100)]
        sma_data = [sum(price_data[max(0, i-20):i+1]) / min(i+1, 20) 
                    for i in range(len(price_data))]
        ema_data = price_data.copy()
        
        # Update charts
        self.price_chart.update_data(price_data, sma_data, ema_data)
        
        # Update AI reasoning (demo)
        if random.random() > 0.7:  # Random updates
            decisions = ["BUY", "SELL", "HOLD", "STRONG_BUY"]
            decision = random.choice(decisions)
            confidence = random.uniform(60, 95)
            reasoning = [
                "✓ Strong momentum detected",
                "✓ Price above key moving averages",
                "⚠ Moderate volatility present",
                "✓ High probability of continuation"
            ]
            self.ai_reasoning.update_reasoning(decision, confidence, reasoning)
        
        # Update regime (demo)
        regimes = ["BULL", "BEAR", "NEUTRAL", "VOLATILE"]
        self.market_regime.update_regime(
            random.choice(regimes),
            random.randint(40, 90),
            random.uniform(-50, 80),
            random.uniform(30, 85)
        )


def main():
    """Launch ultra-modern UI"""
    if not PYQT_AVAILABLE:
        print("ERROR: PyQt6 required!")
        print("Install: pip install PyQt6 pyqtgraph")
        return
    
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    window = LokiUltraModernUI()
    window.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
