"""
Loki Portfolio Optimization Visualization
Efficient frontier, risk-return analysis, allocation optimization, and correlation heatmaps
"""

import sys
import numpy as np
import pandas as pd
from typing import List, Dict, Tuple

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


class EfficientFrontierChart(QWidget):
    """Efficient frontier visualization"""

    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        """Setup efficient frontier chart"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if not PYQTGRAPH_AVAILABLE:
            label = QLabel("📈 Efficient Frontier\n(pyqtgraph required)")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label)
            return

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground("#1a1a1d")
        self.plot_widget.setTitle("Efficient Frontier", color="#ffffff", size="14pt")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setLabel("left", "Expected Return (%)", color="#ffffff")
        self.plot_widget.setLabel("bottom", "Risk (Volatility %)", color="#ffffff")

        layout.addWidget(self.plot_widget)

        self.update_chart()

    def update_chart(self):
        """Update efficient frontier chart"""
        if not PYQTGRAPH_AVAILABLE:
            return

        # Generate efficient frontier
        n_portfolios = 10000
        n_assets = 5

        # Random portfolios
        returns = []
        risks = []
        sharpe_ratios = []

        for _ in range(n_portfolios):
            # Random weights
            weights = np.random.random(n_assets)
            weights /= weights.sum()

            # Expected return (5-20% range)
            expected_return = np.dot(weights, np.random.uniform(5, 20, n_assets))

            # Risk (volatility 10-30%)
            cov_matrix = np.random.rand(n_assets, n_assets)
            cov_matrix = np.dot(cov_matrix, cov_matrix.T) * 100  # Make symmetric
            portfolio_variance = np.dot(weights, np.dot(cov_matrix, weights))
            portfolio_risk = np.sqrt(portfolio_variance)

            # Sharpe ratio
            risk_free_rate = 2.0
            sharpe = (expected_return - risk_free_rate) / portfolio_risk

            returns.append(expected_return)
            risks.append(portfolio_risk)
            sharpe_ratios.append(sharpe)

        returns = np.array(returns)
        risks = np.array(risks)
        sharpe_ratios = np.array(sharpe_ratios)

        # Color by Sharpe ratio
        # Normalize Sharpe ratios for coloring
        sharpe_norm = (sharpe_ratios - sharpe_ratios.min()) / (
            sharpe_ratios.max() - sharpe_ratios.min()
        )

        # Create scatter plot with color gradient
        scatter = pg.ScatterPlotItem(
            x=risks,
            y=returns,
            size=5,
            pen=None,
            brush=[pg.mkBrush(self.sharpe_to_color(s)) for s in sharpe_norm],
        )
        self.plot_widget.addItem(scatter)

        # Mark current portfolio
        current_risk = 12
        current_return = 15
        current_portfolio = pg.ScatterPlotItem(
            x=[current_risk],
            y=[current_return],
            size=15,
            pen=pg.mkPen("#00d4ff", width=2),
            brush=pg.mkBrush("#00d4ff"),
            symbol="star",
        )
        self.plot_widget.addItem(current_portfolio)

        # Add text label
        text = pg.TextItem("Current Portfolio", color="#00d4ff", anchor=(0.5, 1.5))
        text.setPos(current_risk, current_return)
        self.plot_widget.addItem(text)

        # Mark optimal portfolio (max Sharpe)
        optimal_idx = np.argmax(sharpe_ratios)
        optimal_risk = risks[optimal_idx]
        optimal_return = returns[optimal_idx]

        optimal_portfolio = pg.ScatterPlotItem(
            x=[optimal_risk],
            y=[optimal_return],
            size=15,
            pen=pg.mkPen("#4ec9b0", width=2),
            brush=pg.mkBrush("#4ec9b0"),
            symbol="star",
        )
        self.plot_widget.addItem(optimal_portfolio)

        optimal_text = pg.TextItem("Optimal", color="#4ec9b0", anchor=(0.5, -0.5))
        optimal_text.setPos(optimal_risk, optimal_return)
        self.plot_widget.addItem(optimal_text)

    def sharpe_to_color(self, sharpe_norm: float) -> Tuple[int, int, int]:
        """Convert normalized Sharpe ratio to color"""
        # Red -> Yellow -> Green gradient
        if sharpe_norm < 0.5:
            # Red to Yellow
            r = 255
            g = int(255 * sharpe_norm * 2)
            b = 0
        else:
            # Yellow to Green
            r = int(255 * (1 - (sharpe_norm - 0.5) * 2))
            g = 255
            b = 0

        return (r, g, b)


class AllocationPieChart(QWidget):
    """Portfolio allocation pie chart"""

    def __init__(self):
        super().__init__()
        self.allocations = {"AAPL": 25, "MSFT": 20, "GOOGL": 18, "TSLA": 15, "SPY": 12, "Cash": 10}
        self.setup_ui()

    def setup_ui(self):
        """Setup pie chart"""
        layout = QVBoxLayout(self)

        # Title
        title = QLabel("📊 Portfolio Allocation")
        title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        title.setStyleSheet("color: #ffffff; background: transparent;")
        layout.addWidget(title)

        # Allocation bars
        colors = ["#4ec9b0", "#00d4ff", "#9370db", "#ffa500", "#ff6b6b", "#666666"]

        for (symbol, pct), color in zip(self.allocations.items(), colors):
            bar_widget = self.create_allocation_bar(symbol, pct, color)
            layout.addWidget(bar_widget)

        layout.addStretch()

    def create_allocation_bar(self, symbol: str, percentage: float, color: str) -> QWidget:
        """Create allocation bar for a symbol"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 5, 0, 5)

        # Symbol label
        symbol_label = QLabel(symbol)
        symbol_label.setFixedWidth(80)
        symbol_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        symbol_label.setStyleSheet("color: #ffffff; background: transparent;")

        # Progress bar
        progress = QProgressBar()
        progress.setRange(0, 100)
        progress.setValue(int(percentage))
        progress.setFormat(f"{percentage}%")
        progress.setFixedHeight(25)
        progress.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid rgba(255,255,255,0.2);
                border-radius: 4px;
                background: rgba(0,0,0,0.3);
                text-align: center;
                color: white;
                font-weight: bold;
            }}
            QProgressBar::chunk {{
                background: {color};
                border-radius: 4px;
            }}
        """)

        # Value label
        value_label = QLabel(f"${percentage * 1000:,.0f}")
        value_label.setFixedWidth(100)
        value_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        value_label.setStyleSheet(f"color: {color}; background: transparent;")

        layout.addWidget(symbol_label)
        layout.addWidget(progress)
        layout.addWidget(value_label)

        return widget


class CorrelationHeatmap(QWidget):
    """Correlation matrix heatmap"""

    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        """Setup correlation heatmap"""
        layout = QVBoxLayout(self)

        # Title
        title = QLabel("🔥 Correlation Heatmap")
        title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        title.setStyleSheet("color: #ffffff; background: transparent;")
        layout.addWidget(title)

        if not PYQTGRAPH_AVAILABLE:
            label = QLabel("(pyqtgraph required)")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label)
            return

        # Create image view
        self.image_view = pg.ImageView()
        self.image_view.ui.roiBtn.hide()
        self.image_view.ui.menuBtn.hide()

        layout.addWidget(self.image_view)

        self.update_heatmap()

    def update_heatmap(self):
        """Update correlation heatmap"""
        if not PYQTGRAPH_AVAILABLE:
            return

        # Generate correlation matrix
        symbols = ["AAPL", "MSFT", "GOOGL", "TSLA", "SPY"]
        n = len(symbols)

        # Create realistic correlation matrix
        corr_matrix = np.eye(n)
        for i in range(n):
            for j in range(i + 1, n):
                # Tech stocks more correlated
                if i < 4 and j < 4:
                    corr = np.random.uniform(0.6, 0.9)
                else:
                    corr = np.random.uniform(0.3, 0.7)
                corr_matrix[i, j] = corr
                corr_matrix[j, i] = corr

        # Display heatmap
        self.image_view.setImage(corr_matrix, axes={"x": 1, "y": 0})

        # Set color map (red to green)
        colors = [
            (0, (180, 50, 50)),  # Low correlation - red
            (0.5, (200, 200, 50)),  # Medium - yellow
            (1, (50, 180, 50)),  # High correlation - green
        ]
        cmap = pg.ColorMap(pos=[c[0] for c in colors], color=[c[1] for c in colors])
        self.image_view.setColorMap(cmap)


class RiskReturnScatter(QWidget):
    """Individual asset risk-return scatter plot"""

    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        """Setup risk-return scatter"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if not PYQTGRAPH_AVAILABLE:
            label = QLabel("📊 Risk-Return Analysis\n(pyqtgraph required)")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label)
            return

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground("#1a1a1d")
        self.plot_widget.setTitle("Asset Risk-Return Profile", color="#ffffff", size="14pt")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setLabel("left", "Expected Return (%)", color="#ffffff")
        self.plot_widget.setLabel("bottom", "Risk (Volatility %)", color="#ffffff")

        layout.addWidget(self.plot_widget)

        self.update_chart()

    def update_chart(self):
        """Update risk-return scatter"""
        if not PYQTGRAPH_AVAILABLE:
            return

        # Sample assets
        assets = [
            ("AAPL", 18, 25, "#4ec9b0"),
            ("MSFT", 16, 22, "#00d4ff"),
            ("GOOGL", 15, 24, "#9370db"),
            ("TSLA", 25, 45, "#ffa500"),
            ("SPY", 12, 18, "#ff6b6b"),
            ("QQQ", 14, 20, "#66d9ef"),
        ]

        for symbol, ret, risk, color in assets:
            # Plot point
            scatter = pg.ScatterPlotItem(
                x=[risk],
                y=[ret],
                size=15,
                pen=pg.mkPen(color, width=2),
                brush=pg.mkBrush(color),
                symbol="o",
            )
            self.plot_widget.addItem(scatter)

            # Add label
            text = pg.TextItem(symbol, color=color, anchor=(0.5, 1.5))
            text.setPos(risk, ret)
            self.plot_widget.addItem(text)


class OptimizationSuggestions(QWidget):
    """AI-driven optimization suggestions"""

    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        """Setup suggestions panel"""
        layout = QVBoxLayout(self)

        # Title
        title = QLabel("🤖 AI Optimization Suggestions")
        title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        title.setStyleSheet("color: #ffffff; background: transparent;")
        layout.addWidget(title)

        # Suggestions
        suggestions = [
            {
                "title": "Reduce TSLA Allocation",
                "reason": "High volatility (45%) increasing portfolio risk",
                "action": "Reduce from 15% to 10%",
                "impact": "Portfolio volatility: 22% → 19%",
                "priority": "HIGH",
                "color": "#f48771",
            },
            {
                "title": "Increase Diversification",
                "reason": "Tech stocks highly correlated (0.85)",
                "action": "Add bonds or international exposure",
                "impact": "Sharpe ratio: 1.85 → 2.10",
                "priority": "MEDIUM",
                "color": "#ffa500",
            },
            {
                "title": "Rebalance Portfolio",
                "reason": "Allocations drifted from targets",
                "action": "Sell AAPL (+5%), Buy SPY (-3%)",
                "impact": "Return to target allocation",
                "priority": "LOW",
                "color": "#00d4ff",
            },
        ]

        for suggestion in suggestions:
            card = self.create_suggestion_card(suggestion)
            layout.addWidget(card)

        layout.addStretch()

    def create_suggestion_card(self, suggestion: Dict) -> QWidget:
        """Create suggestion card"""
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: rgba(45,45,48,0.5);
                border-left: 4px solid {suggestion['color']};
                border-radius: 8px;
                padding: 15px;
                margin: 5px 0;
            }}
            QFrame:hover {{
                background: rgba(50,50,53,0.7);
            }}
        """)

        layout = QVBoxLayout(card)

        # Header
        header_layout = QHBoxLayout()

        title_label = QLabel(suggestion["title"])
        title_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #ffffff; background: transparent;")

        priority_badge = QLabel(suggestion["priority"])
        priority_badge.setStyleSheet(f"""
            background: {suggestion['color']};
            color: white;
            border-radius: 4px;
            padding: 4px 12px;
            font-weight: bold;
            font-size: 9pt;
        """)
        priority_badge.setFixedHeight(25)

        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(priority_badge)

        # Reason
        reason_label = QLabel(f"📋 {suggestion['reason']}")
        reason_label.setStyleSheet("color: #cccccc; background: transparent;")
        reason_label.setWordWrap(True)

        # Action
        action_label = QLabel(f"💡 {suggestion['action']}")
        action_label.setStyleSheet("color: #00d4ff; background: transparent;")
        action_label.setWordWrap(True)

        # Impact
        impact_label = QLabel(f"📊 {suggestion['impact']}")
        impact_label.setStyleSheet("color: #4ec9b0; background: transparent; font-weight: bold;")

        # Apply button
        apply_btn = QPushButton("Apply Suggestion")
        apply_btn.setStyleSheet("""
            QPushButton {
                background: rgba(78,201,176,0.2);
                border: 1px solid #4ec9b0;
                border-radius: 6px;
                color: #4ec9b0;
                padding: 8px 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(78,201,176,0.3);
            }
        """)

        layout.addLayout(header_layout)
        layout.addWidget(reason_label)
        layout.addWidget(action_label)
        layout.addWidget(impact_label)
        layout.addWidget(apply_btn)

        return card


class PortfolioOptimizationDashboard(QWidget):
    """Complete portfolio optimization dashboard"""

    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        """Setup optimization dashboard"""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # Top row: Efficient frontier and allocation
        top_layout = QHBoxLayout()

        self.efficient_frontier = EfficientFrontierChart()
        self.allocation_chart = AllocationPieChart()

        top_layout.addWidget(self.efficient_frontier, stretch=2)
        top_layout.addWidget(self.allocation_chart, stretch=1)

        # Middle row: Correlation and risk-return
        middle_layout = QHBoxLayout()

        self.correlation_heatmap = CorrelationHeatmap()
        self.risk_return_scatter = RiskReturnScatter()

        middle_layout.addWidget(self.correlation_heatmap)
        middle_layout.addWidget(self.risk_return_scatter)

        # Bottom: AI suggestions
        self.optimization_suggestions = OptimizationSuggestions()

        layout.addLayout(top_layout)
        layout.addLayout(middle_layout)
        layout.addWidget(self.optimization_suggestions)


def main():
    """Demo portfolio optimization dashboard"""
    if not PYQT_AVAILABLE:
        print("PyQt6 required: pip install PyQt6")
        return

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Dark palette
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(26, 26, 29))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(204, 204, 204))
    app.setPalette(palette)

    window = QMainWindow()
    window.setWindowTitle("Loki Portfolio Optimization")
    window.resize(1400, 900)

    dashboard = PortfolioOptimizationDashboard()

    # Add scroll area
    scroll = QScrollArea()
    scroll.setWidget(dashboard)
    scroll.setWidgetResizable(True)
    scroll.setStyleSheet("QScrollArea { border: none; }")

    window.setCentralWidget(scroll)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
