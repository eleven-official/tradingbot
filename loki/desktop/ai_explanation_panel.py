"""
Loki Real-Time AI Explanation Panel
Live visualization of AI decision-making process with step-by-step reasoning
"""

import sys
from typing import List, Dict, Optional
from datetime import datetime
from dataclasses import dataclass

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


@dataclass
class ReasoningStep:
    """Single step in AI reasoning"""

    step_number: int
    category: str  # "observation", "analysis", "decision", "execution"
    title: str
    description: str
    confidence: float
    data: Dict
    timestamp: datetime


class ReasoningStepWidget(QFrame):
    """Visual representation of a single reasoning step"""

    def __init__(self, step: ReasoningStep):
        super().__init__()
        self.step = step
        self.setup_ui()

    def setup_ui(self):
        """Setup step UI"""
        self.setStyleSheet("""
            QFrame {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(45, 45, 48, 0.5),
                    stop:1 rgba(35, 35, 38, 0.5)
                );
                border-left: 3px solid {color};
                border-radius: 8px;
                padding: 15px;
                margin: 5px 0;
            }
            QFrame:hover {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(50, 50, 53, 0.6),
                    stop:1 rgba(40, 40, 43, 0.6)
                );
            }}
        """.format(color=self.get_category_color()))

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Header
        header_layout = QHBoxLayout()

        # Step number badge
        step_badge = QLabel(f"{self.step.step_number}")
        step_badge.setFixedSize(30, 30)
        step_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        step_badge.setStyleSheet(f"""
            background: {self.get_category_color()};
            color: white;
            border-radius: 15px;
            font-weight: bold;
            font-size: 12pt;
        """)

        # Category icon and title
        icon = self.get_category_icon()
        title_label = QLabel(f"{icon} {self.step.title}")
        title_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #ffffff; background: transparent;")

        # Confidence meter
        confidence_label = QLabel(f"{self.step.confidence:.0f}%")
        confidence_label.setFont(QFont("Segoe UI", 10))
        confidence_label.setStyleSheet(f"""
            color: {self.get_confidence_color()};
            background: transparent;
        """)

        header_layout.addWidget(step_badge)
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(confidence_label)

        # Description
        desc_label = QLabel(self.step.description)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("""
            color: #cccccc;
            background: transparent;
            padding: 5px 0;
        """)

        # Data visualization (if available)
        if self.step.data:
            data_widget = self.create_data_visualization()
            layout.addLayout(header_layout)
            layout.addWidget(desc_label)
            layout.addWidget(data_widget)
        else:
            layout.addLayout(header_layout)
            layout.addWidget(desc_label)

        # Timestamp
        time_label = QLabel(self.step.timestamp.strftime("%H:%M:%S"))
        time_label.setStyleSheet("color: #666; background: transparent; font-size: 9pt;")
        layout.addWidget(time_label)

    def get_category_color(self) -> str:
        """Get color for category"""
        colors = {
            "observation": "#00d4ff",
            "analysis": "#9370db",
            "decision": "#4ec9b0",
            "execution": "#ffa500",
            "result": "#f48771",
        }
        return colors.get(self.step.category, "#666666")

    def get_category_icon(self) -> str:
        """Get emoji icon for category"""
        icons = {
            "observation": "👁️",
            "analysis": "🔍",
            "decision": "🎯",
            "execution": "⚡",
            "result": "📊",
        }
        return icons.get(self.step.category, "•")

    def get_confidence_color(self) -> str:
        """Get color based on confidence level"""
        if self.step.confidence >= 80:
            return "#4ec9b0"
        elif self.step.confidence >= 60:
            return "#ffa500"
        else:
            return "#f48771"

    def create_data_visualization(self) -> QWidget:
        """Create visualization for step data"""
        widget = QFrame()
        widget.setStyleSheet("""
            QFrame {
                background: rgba(0,0,0,0.2);
                border: 1px solid rgba(255,255,255,0.05);
                border-radius: 6px;
                padding: 10px;
            }
        """)

        layout = QVBoxLayout(widget)

        for key, value in self.step.data.items():
            row = QHBoxLayout()

            key_label = QLabel(f"{key}:")
            key_label.setStyleSheet("color: #9e9e9e; background: transparent;")
            key_label.setFont(QFont("Segoe UI", 9))

            value_label = QLabel(str(value))
            value_label.setStyleSheet("color: #ffffff; background: transparent;")
            value_label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))

            row.addWidget(key_label)
            row.addWidget(value_label)
            row.addStretch()

            layout.addLayout(row)

        return widget


class AIThinkingAnimation(QWidget):
    """Animated thinking indicator"""

    def __init__(self):
        super().__init__()
        self.setFixedSize(200, 60)
        self.dots = 0
        self.setup_ui()

        # Animation timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_animation)
        self.timer.start(300)

    def setup_ui(self):
        """Setup animation UI"""
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.status_label = QLabel("🧠 AI Thinking")
        self.status_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("""
            color: #9370db;
            background: transparent;
        """)

        self.dots_label = QLabel("...")
        self.dots_label.setFont(QFont("Segoe UI", 16))
        self.dots_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.dots_label.setStyleSheet("""
            color: #00d4ff;
            background: transparent;
        """)

        layout.addWidget(self.status_label)
        layout.addWidget(self.dots_label)

    def update_animation(self):
        """Update thinking animation"""
        self.dots = (self.dots + 1) % 4
        self.dots_label.setText("." * max(1, self.dots))


class DecisionTreeView(QWidget):
    """Visual decision tree"""

    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        """Setup decision tree visualization"""
        layout = QVBoxLayout(self)

        if PYQTGRAPH_AVAILABLE:
            # Create graph view
            self.view = pg.GraphicsLayoutWidget()
            self.view.setBackground("#1a1a1d")

            self.plot = self.view.addPlot()
            self.plot.hideAxis("left")
            self.plot.hideAxis("bottom")
            self.plot.setXRange(-5, 5)
            self.plot.setYRange(-5, 5)

            layout.addWidget(self.view)

            # Draw sample decision tree
            self.draw_sample_tree()
        else:
            label = QLabel("📊 Decision Tree\n(pyqtgraph required)")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("color: #888; font-size: 12pt;")
            layout.addWidget(label)

    def draw_sample_tree(self):
        """Draw a sample decision tree"""
        # Root node
        self.add_node(0, 4, "Market Analysis", "#00d4ff")

        # Level 1
        self.add_node(-2, 2, "Technical", "#9370db")
        self.add_node(2, 2, "Fundamental", "#9370db")

        self.add_edge(0, 4, -2, 2, "#00d4ff")
        self.add_edge(0, 4, 2, 2, "#00d4ff")

        # Level 2
        self.add_node(-3, 0, "Momentum ✓", "#4ec9b0")
        self.add_node(-1, 0, "Trend ✓", "#4ec9b0")
        self.add_node(1, 0, "Value", "#ffa500")
        self.add_node(3, 0, "Growth ✓", "#4ec9b0")

        self.add_edge(-2, 2, -3, 0, "#9370db")
        self.add_edge(-2, 2, -1, 0, "#9370db")
        self.add_edge(2, 2, 1, 0, "#9370db")
        self.add_edge(2, 2, 3, 0, "#9370db")

        # Decision
        self.add_node(0, -2, "BUY", "#4ec9b0")

        self.add_edge(-3, 0, 0, -2, "#4ec9b0")
        self.add_edge(-1, 0, 0, -2, "#4ec9b0")
        self.add_edge(3, 0, 0, -2, "#4ec9b0")

    def add_node(self, x: float, y: float, label: str, color: str):
        """Add a node to the tree"""
        # Draw circle
        circle = pg.QtWidgets.QGraphicsEllipseItem(x - 0.5, y - 0.5, 1, 1)
        circle.setBrush(pg.mkBrush(color))
        circle.setPen(pg.mkPen(color, width=2))
        self.plot.addItem(circle)

        # Add text
        text = pg.TextItem(label, color="white", anchor=(0.5, 0.5))
        text.setPos(x, y)
        self.plot.addItem(text)

    def add_edge(self, x1: float, y1: float, x2: float, y2: float, color: str):
        """Add an edge between nodes"""
        line = pg.PlotCurveItem([x1, x2], [y1, y2], pen=pg.mkPen(color, width=2))
        self.plot.addItem(line)


class AIExplanationPanel(QWidget):
    """Complete AI explanation panel with real-time reasoning"""

    def __init__(self):
        super().__init__()
        self.reasoning_steps: List[ReasoningStep] = []
        self.setup_ui()

    def setup_ui(self):
        """Setup explanation panel UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # Header
        header = QFrame()
        header.setStyleSheet("""
            QFrame {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(147,112,219,0.3),
                    stop:1 rgba(0,212,255,0.3)
                );
                border-radius: 12px;
                padding: 15px;
            }
        """)

        header_layout = QHBoxLayout(header)

        title = QLabel("🧠 AI Decision Explanation")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title.setStyleSheet("color: #ffffff; background: transparent;")

        self.status_indicator = QLabel("● IDLE")
        self.status_indicator.setStyleSheet("color: #666; background: transparent;")

        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(self.status_indicator)

        # Tabs for different views
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
                background: rgba(147,112,219,0.3);
                color: #9370db;
            }
        """)

        # Step-by-step tab
        self.steps_tab = self.create_steps_tab()
        self.tabs.addTab(self.steps_tab, "📋 Step-by-Step")

        # Decision tree tab
        self.tree_tab = DecisionTreeView()
        self.tabs.addTab(self.tree_tab, "🌳 Decision Tree")

        # Confidence breakdown tab
        self.confidence_tab = self.create_confidence_tab()
        self.tabs.addTab(self.confidence_tab, "📊 Confidence")

        # Risk assessment tab
        self.risk_tab = self.create_risk_tab()
        self.tabs.addTab(self.risk_tab, "⚠️ Risk")

        layout.addWidget(header)
        layout.addWidget(self.tabs)

    def create_steps_tab(self) -> QWidget:
        """Create step-by-step reasoning tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Thinking animation (initially visible)
        self.thinking_animation = AIThinkingAnimation()
        self.thinking_animation.setVisible(False)
        layout.addWidget(self.thinking_animation, alignment=Qt.AlignmentFlag.AlignCenter)

        # Scroll area for steps
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                background: rgba(45,45,48,0.5);
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: rgba(147,112,219,0.5);
                border-radius: 5px;
            }
        """)

        self.steps_container = QWidget()
        self.steps_layout = QVBoxLayout(self.steps_container)
        self.steps_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.steps_layout.setSpacing(10)

        scroll.setWidget(self.steps_container)
        layout.addWidget(scroll)

        return widget

    def create_confidence_tab(self) -> QWidget:
        """Create confidence breakdown tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        if PYQTGRAPH_AVAILABLE:
            # Bar chart of confidence factors
            self.confidence_chart = pg.PlotWidget()
            self.confidence_chart.setBackground("#1a1a1d")
            self.confidence_chart.setLabel("left", "Confidence Impact (%)")
            self.confidence_chart.setLabel("bottom", "Factors")
            self.confidence_chart.showGrid(y=True, alpha=0.3)

            layout.addWidget(self.confidence_chart)

            # Add sample data
            self.update_confidence_chart(
                {"Technical": 85, "Momentum": 75, "Volume": 65, "Sentiment": 70, "Risk": 60}
            )
        else:
            label = QLabel("📊 Confidence Breakdown\n(pyqtgraph required)")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label)

        return widget

    def create_risk_tab(self) -> QWidget:
        """Create risk assessment tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Risk metrics
        metrics = [
            ("Volatility", "Medium", 65, "#ffa500"),
            ("Drawdown Risk", "Low", 30, "#4ec9b0"),
            ("Correlation", "Low", 25, "#4ec9b0"),
            ("Market Risk", "Medium", 55, "#ffa500"),
            ("Position Size", "Safe", 40, "#4ec9b0"),
        ]

        for name, level, value, color in metrics:
            metric_frame = QFrame()
            metric_frame.setStyleSheet(f"""
                QFrame {{
                    background: rgba(45,45,48,0.3);
                    border-left: 3px solid {color};
                    border-radius: 8px;
                    padding: 15px;
                    margin: 5px 0;
                }}
            """)

            metric_layout = QVBoxLayout(metric_frame)

            # Name and level
            header_layout = QHBoxLayout()
            name_label = QLabel(name)
            name_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            name_label.setStyleSheet("color: #ffffff; background: transparent;")

            level_label = QLabel(level)
            level_label.setStyleSheet(f"color: {color}; background: transparent;")

            header_layout.addWidget(name_label)
            header_layout.addStretch()
            header_layout.addWidget(level_label)

            # Progress bar
            progress = QProgressBar()
            progress.setRange(0, 100)
            progress.setValue(value)
            progress.setFixedHeight(8)
            progress.setTextVisible(False)
            progress.setStyleSheet(f"""
                QProgressBar {{
                    border: none;
                    border-radius: 4px;
                    background: rgba(255,255,255,0.1);
                }}
                QProgressBar::chunk {{
                    background: {color};
                    border-radius: 4px;
                }}
            """)

            metric_layout.addLayout(header_layout)
            metric_layout.addWidget(progress)

            layout.addWidget(metric_frame)

        layout.addStretch()
        return widget

    def update_confidence_chart(self, factors: Dict[str, float]):
        """Update confidence breakdown chart"""
        if not PYQTGRAPH_AVAILABLE:
            return

        self.confidence_chart.clear()

        x = list(range(len(factors)))
        heights = list(factors.values())
        labels = list(factors.keys())

        # Create bar graph
        colors = ["#4ec9b0" if h >= 70 else "#ffa500" if h >= 50 else "#f48771" for h in heights]

        bar_graph = pg.BarGraphItem(x=x, height=heights, width=0.8, brushes=colors)
        self.confidence_chart.addItem(bar_graph)

        # Set x-axis labels
        ax = self.confidence_chart.getAxis("bottom")
        ax.setTicks([[(i, labels[i]) for i in range(len(labels))]])

    def add_reasoning_step(self, step: ReasoningStep):
        """Add a new reasoning step"""
        self.reasoning_steps.append(step)

        # Create widget
        step_widget = ReasoningStepWidget(step)
        self.steps_layout.addWidget(step_widget)

        # Scroll to bottom
        QTimer.singleShot(100, lambda: self.scroll_to_bottom())

        # Update status
        self.status_indicator.setText(f"● {step.category.upper()}")
        self.status_indicator.setStyleSheet(f"""
            color: {step_widget.get_category_color()};
            background: transparent;
            font-weight: bold;
        """)

    def scroll_to_bottom(self):
        """Scroll to bottom of steps"""
        scroll_area = self.steps_tab.findChild(QScrollArea)
        if scroll_area:
            scroll_area.verticalScrollBar().setValue(scroll_area.verticalScrollBar().maximum())

    def start_thinking(self):
        """Show thinking animation"""
        self.thinking_animation.setVisible(True)
        self.status_indicator.setText("● THINKING")
        self.status_indicator.setStyleSheet("color: #9370db; background: transparent;")

    def stop_thinking(self):
        """Hide thinking animation"""
        self.thinking_animation.setVisible(False)

    def clear_steps(self):
        """Clear all reasoning steps"""
        # Remove all step widgets
        while self.steps_layout.count():
            child = self.steps_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        self.reasoning_steps.clear()
        self.status_indicator.setText("● IDLE")
        self.status_indicator.setStyleSheet("color: #666; background: transparent;")


def main():
    """Demo the AI explanation panel"""
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

    # Create window
    window = QMainWindow()
    window.setWindowTitle("Loki AI Explanation Panel")
    window.resize(800, 900)

    panel = AIExplanationPanel()
    window.setCentralWidget(panel)

    # Add demo steps
    def add_demo_steps():
        steps = [
            ReasoningStep(
                1,
                "observation",
                "Market Data Collected",
                "Gathered OHLCV data for AAPL, current price $175.50",
                100,
                {"Symbol": "AAPL", "Price": "$175.50", "Volume": "2.5M"},
                datetime.now(),
            ),
            ReasoningStep(
                2,
                "analysis",
                "Technical Analysis",
                "Analyzed 50+ technical indicators. Strong bullish momentum detected with RSI at 65 and MACD positive.",
                85,
                {"RSI": "65", "MACD": "Positive", "Trend": "Bullish"},
                datetime.now(),
            ),
            ReasoningStep(
                3,
                "analysis",
                "Risk Assessment",
                "Calculated risk metrics. Volatility within acceptable range, position sizing optimized.",
                75,
                {"Volatility": "Medium", "Risk Score": "6/10", "Max Loss": "3%"},
                datetime.now(),
            ),
            ReasoningStep(
                4,
                "decision",
                "Strategy Selection",
                "Multi-factor strategy selected with 82% confidence. Momentum and breakout signals aligned.",
                82,
                {"Strategy": "Multi-Factor", "Momentum": "Strong", "Breakout": "Confirmed"},
                datetime.now(),
            ),
            ReasoningStep(
                5,
                "execution",
                "Trade Execution",
                "BUY signal generated. Entry: $175.50, Target: $184.00, Stop: $171.00",
                88,
                {"Action": "BUY", "Shares": "100", "Risk/Reward": "2.5"},
                datetime.now(),
            ),
        ]

        for i, step in enumerate(steps):
            QTimer.singleShot(i * 1000, lambda s=step: panel.add_reasoning_step(s))

    # Add steps after a short delay
    QTimer.singleShot(500, add_demo_steps)

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
