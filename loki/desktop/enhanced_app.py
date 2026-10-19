"""
Loki Trading Platform - Enhanced Desktop Application
Ultra-modern interface with improved performance and features
"""

import sys
import logging
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime
import json

try:
    from PyQt6.QtWidgets import (
        QApplication,
        QMainWindow,
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QTabWidget,
        QSystemTrayIcon,
        QMenu,
        QLabel,
        QPushButton,
        QTableWidget,
        QTableWidgetItem,
        QSplitter,
        QStatusBar,
        QToolBar,
        QMessageBox,
        QDockWidget,
        QTextEdit,
        QProgressBar,
        QComboBox,
        QSpinBox,
        QCheckBox,
        QFrame,
        QScrollArea,
        QGridLayout,
    )
    from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QSize
    from PyQt6.QtGui import QIcon, QAction, QFont, QColor, QPalette

    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

if not PYQT_AVAILABLE:
    raise ImportError("PyQt6 is not installed. Please install: pip install PyQt6")


try:
    import pyqtgraph as pg

    PYQTGRAPH_AVAILABLE = True
except ImportError:
    print("pyqtgraph not available. Charts disabled.")
    PYQTGRAPH_AVAILABLE = False

logger = logging.getLogger(__name__)


class ModernCard(QFrame):
    """Modern card-style widget with shadow and hover effects"""

    def __init__(self, title: str, value: str, change: str, color: str = "#007acc"):
        super().__init__()
        self.setFrameStyle(QFrame.Shape.Box)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: #2d2d30;
                border-radius: 12px;
                border: 1px solid #3e3e42;
                padding: 20px;
            }}
            QFrame:hover {{
                border: 1px solid {color};
                background-color: #323235;
            }}
        """)

        layout = QVBoxLayout()

        # Title
        title_label = QLabel(title)
        title_label.setFont(QFont("Segoe UI", 11))
        title_label.setStyleSheet("color: #9e9e9e; border: none; padding: 0;")

        # Value
        value_label = QLabel(value)
        value_label.setFont(QFont("Segoe UI", 28, QFont.Weight.Bold))
        value_label.setStyleSheet(f"color: {color}; border: none; padding: 0;")

        # Change
        change_label = QLabel(change)
        change_label.setFont(QFont("Segoe UI", 10))
        change_color = "#4ec9b0" if "+" in change else "#f48771"
        change_label.setStyleSheet(f"color: {change_color}; border: none; padding: 0;")

        layout.addWidget(title_label)
        layout.addWidget(value_label)
        layout.addWidget(change_label)
        layout.addStretch()

        self.setLayout(layout)
        self.setMinimumHeight(150)


class AIStatusWidget(QWidget):
    """Live AI status indicator"""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()

        # AI Brain animation
        self.status_label = QLabel("🤖 AI Status")
        self.status_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))

        # Status indicators
        self.thinking_label = QLabel("💭 Thinking: Idle")
        self.confidence_label = QLabel("📊 Confidence: --")
        self.state_label = QLabel("🎭 State: Neutral")
        self.decisions_label = QLabel("🎯 Decisions: 0")

        # Progress bar for confidence
        self.confidence_bar = QProgressBar()
        self.confidence_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #3e3e42;
                border-radius: 5px;
                text-align: center;
                background-color: #1e1e1e;
            }
            QProgressBar::chunk {
                background-color: #4ec9b0;
                border-radius: 3px;
            }
        """)

        for label in [
            self.thinking_label,
            self.confidence_label,
            self.state_label,
            self.decisions_label,
        ]:
            label.setStyleSheet("color: #cccccc; padding: 5px;")

        layout.addWidget(self.status_label)
        layout.addWidget(self.thinking_label)
        layout.addWidget(self.confidence_label)
        layout.addWidget(self.confidence_bar)
        layout.addWidget(self.state_label)
        layout.addWidget(self.decisions_label)
        layout.addStretch()

        self.setLayout(layout)
        self.setStyleSheet("""
            QWidget {
                background-color: #2d2d30;
                border-radius: 10px;
                padding: 15px;
            }
        """)

    def update_status(self, thinking: str, confidence: float, state: str, decisions: int):
        """Update AI status"""
        self.thinking_label.setText(f"💭 Thinking: {thinking}")
        self.confidence_label.setText(f"📊 Confidence: {confidence:.1f}%")
        self.confidence_bar.setValue(int(confidence))
        self.state_label.setText(f"🎭 State: {state}")
        self.decisions_label.setText(f"🎯 Decisions: {decisions}")


class LiveChartWidget(QWidget):
    """Live updating chart with multiple series"""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()

        if PYQTGRAPH_AVAILABLE:
            # Create pyqtgraph plot
            self.plot_widget = pg.PlotWidget()
            self.plot_widget.setBackground("#1e1e1e")
            self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
            self.plot_widget.setLabel("left", "Portfolio Value", units="$")
            self.plot_widget.setLabel("bottom", "Time")

            # Create data series
            self.portfolio_curve = self.plot_widget.plot(
                pen=pg.mkPen(color="#4ec9b0", width=3), name="Portfolio"
            )

            self.data_x = []
            self.data_y = []

            layout.addWidget(self.plot_widget)
        else:
            # Fallback to simple label
            label = QLabel("📈 Live Chart\n(Install pyqtgraph for interactive charts)")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("background-color: #2d2d30; padding: 50px; border-radius: 10px;")
            layout.addWidget(label)

        self.setLayout(layout)

    def update_data(self, value: float):
        """Add new data point"""
        if PYQTGRAPH_AVAILABLE and hasattr(self, "portfolio_curve"):
            self.data_x.append(len(self.data_x))
            self.data_y.append(value)

            # Keep last 100 points
            if len(self.data_x) > 100:
                self.data_x = self.data_x[-100:]
                self.data_y = self.data_y[-100:]

            self.portfolio_curve.setData(self.data_x, self.data_y)


class LokiEnhancedApp(QMainWindow):
    """Enhanced Loki Desktop Application with Modern UI"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Loki AI Trading Platform - Enterprise Edition")
        self.setGeometry(100, 100, 1800, 1000)

        # Apply ultra-modern theme
        self.apply_modern_theme()

        # Initialize UI components
        self.init_ui()

        # Setup system tray
        self.setup_system_tray()

        # Start update timers
        self.start_updates()

        logger.info("🚀 Loki Enhanced App initialized")

    def apply_modern_theme(self):
        """Apply ultra-modern dark theme"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e1e;
            }
            QWidget {
                color: #ffffff;
                font-family: 'Segoe UI', 'Roboto', Arial, sans-serif;
                font-size: 10pt;
            }
            QTabWidget::pane {
                border: 1px solid #3e3e42;
                background-color: #252526;
                border-radius: 8px;
            }
            QTabBar::tab {
                background-color: #2d2d30;
                color: #ffffff;
                padding: 12px 24px;
                border: 1px solid #3e3e42;
                border-bottom: none;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #007acc;
                border-color: #007acc;
            }
            QTabBar::tab:hover {
                background-color: #3e3e42;
            }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border-radius: 6px;
                padding: 10px 20px;
                border: none;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
            QPushButton:pressed {
                background-color: #0d5689;
            }
            QTableWidget {
                background-color: #1e1e1e;
                alternate-background-color: #252526;
                gridline-color: #3e3e42;
                border: 1px solid #3e3e42;
                border-radius: 8px;
            }
            QHeaderView::section {
                background-color: #2d2d30;
                padding: 10px;
                border: none;
                border-bottom: 2px solid #007acc;
                font-weight: bold;
                color: #ffffff;
            }
            QScrollBar:vertical {
                background: #1e1e1e;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background: #3e3e42;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical:hover {
                background: #007acc;
            }
            QLineEdit, QTextEdit {
                background-color: #1e1e1e;
                border: 2px solid #3e3e42;
                border-radius: 6px;
                padding: 8px;
                color: #ffffff;
            }
            QLineEdit:focus, QTextEdit:focus {
                border-color: #007acc;
            }
        """)

    def init_ui(self):
        """Initialize the enhanced UI"""
        # Create central widget
        central_widget = QWidget()
        main_layout = QVBoxLayout()
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Header with logo and quick stats
        header = self.create_header()
        main_layout.addWidget(header)

        # Main content area with tabs
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.North)

        # Tab 1: Dashboard
        dashboard_tab = self.create_dashboard_tab()
        self.tabs.addTab(dashboard_tab, "📊 Dashboard")

        # Tab 2: AI Assistant
        ai_tab = self.create_ai_tab()
        self.tabs.addTab(ai_tab, "🤖 AI Assistant")

        # Tab 3: Trading
        trading_tab = self.create_trading_tab()
        self.tabs.addTab(trading_tab, "💹 Trading")

        # Tab 4: Analytics
        analytics_tab = self.create_analytics_tab()
        self.tabs.addTab(analytics_tab, "📈 Analytics")

        # Tab 5: Settings
        settings_tab = self.create_settings_tab()
        self.tabs.addTab(settings_tab, "⚙️ Settings")

        main_layout.addWidget(self.tabs)

        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        # Create status bar
        self.create_enhanced_status_bar()

        # Create toolbar
        self.create_enhanced_toolbar()

    def create_header(self) -> QWidget:
        """Create modern header"""
        header = QWidget()
        header.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #007acc, stop:1 #005a9e);
                border-radius: 12px;
                padding: 20px;
            }
        """)

        layout = QHBoxLayout()

        # Logo and title
        title_layout = QVBoxLayout()
        title = QLabel("🚀 LOKI")
        title.setFont(QFont("Segoe UI", 32, QFont.Weight.Bold))
        subtitle = QLabel("AI Trading Platform - Enterprise Edition")
        subtitle.setFont(QFont("Segoe UI", 12))
        subtitle.setStyleSheet("color: #d4d4d4;")

        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)
        layout.addLayout(title_layout)

        layout.addStretch()

        # Quick stats
        quick_stats = QHBoxLayout()

        stat1 = QLabel("💰 $105,432")
        stat1.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))

        stat2 = QLabel("📈 +2.1%")
        stat2.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        stat2.setStyleSheet("color: #4ec9b0;")

        stat3 = QLabel("🤖 Active")
        stat3.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        stat3.setStyleSheet("color: #4ec9b0;")

        quick_stats.addWidget(stat1)
        quick_stats.addWidget(stat2)
        quick_stats.addWidget(stat3)

        layout.addLayout(quick_stats)

        header.setLayout(layout)
        header.setMinimumHeight(100)
        return header

    def create_dashboard_tab(self) -> QWidget:
        """Create enhanced dashboard tab"""
        dashboard = QWidget()
        layout = QVBoxLayout()

        # Top row - Key metrics cards
        metrics_layout = QHBoxLayout()

        self.portfolio_card = ModernCard(
            "Portfolio Value", "$105,432.50", "+$2,156.30 (2.1%)", "#4ec9b0"
        )

        self.daily_pnl_card = ModernCard("Daily P&L", "$2,156.30", "+2.09%", "#4ec9b0")

        self.positions_card = ModernCard("Open Positions", "5", "Active", "#569cd6")

        self.winrate_card = ModernCard("Win Rate", "68.5%", "Last 30 days", "#dcdcaa")

        metrics_layout.addWidget(self.portfolio_card)
        metrics_layout.addWidget(self.daily_pnl_card)
        metrics_layout.addWidget(self.positions_card)
        metrics_layout.addWidget(self.winrate_card)

        layout.addLayout(metrics_layout)

        # Middle row - Chart and AI Status
        middle_layout = QHBoxLayout()

        # Live chart
        chart_container = QWidget()
        chart_layout = QVBoxLayout()
        chart_title = QLabel("📈 Portfolio Performance")
        chart_title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self.live_chart = LiveChartWidget()
        chart_layout.addWidget(chart_title)
        chart_layout.addWidget(self.live_chart)
        chart_container.setLayout(chart_layout)

        # AI Status
        self.ai_status = AIStatusWidget()

        middle_layout.addWidget(chart_container, 7)
        middle_layout.addWidget(self.ai_status, 3)

        layout.addLayout(middle_layout)

        dashboard.setLayout(layout)
        return dashboard

    def create_ai_tab(self) -> QWidget:
        """Create AI assistant tab"""
        ai_tab = QWidget()
        layout = QVBoxLayout()

        title = QLabel("🤖 AI Assistant - Chat with Loki")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        layout.addWidget(title)

        # Chat area
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setPlaceholderText("AI messages will appear here...")
        layout.addWidget(self.chat_display)

        # Input area
        input_layout = QHBoxLayout()
        self.chat_input = QTextEdit()
        self.chat_input.setMaximumHeight(60)
        self.chat_input.setPlaceholderText("Ask AI anything... (e.g., 'Should I buy AAPL?')")

        send_btn = QPushButton("Send 🚀")
        send_btn.setMinimumWidth(120)
        send_btn.setMinimumHeight(60)
        send_btn.clicked.connect(self.send_ai_message)

        input_layout.addWidget(self.chat_input)
        input_layout.addWidget(send_btn)

        layout.addLayout(input_layout)

        # Add initial AI message
        self.chat_display.append("""
        <div style='background-color: #2d2d30; padding: 15px; border-radius: 10px; margin: 5px;'>
            <b style='color: #4ec9b0;'>🤖 Loki AI:</b><br>
            <span style='color: #cccccc;'>
            Hello! I'm Loki, your autonomous AI trading assistant. I can:
            <ul>
                <li>Analyze market conditions</li>
                <li>Suggest trading strategies</li>
                <li>Assess risk levels</li>
                <li>Explain my reasoning</li>
                <li>Learn from outcomes</li>
            </ul>
            Ask me anything about trading!
            </span>
        </div>
        """)

        ai_tab.setLayout(layout)
        return ai_tab

    def create_trading_tab(self) -> QWidget:
        """Create trading tab"""
        trading = QWidget()
        layout = QVBoxLayout()

        title = QLabel("💹 Active Trading")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        layout.addWidget(title)

        # Quick trade panel
        trade_panel = QWidget()
        trade_panel.setStyleSheet("""
            QWidget {
                background-color: #2d2d30;
                border-radius: 10px;
                padding: 20px;
            }
        """)
        trade_layout = QHBoxLayout()

        # Symbol input
        symbol_label = QLabel("Symbol:")
        self.symbol_input = QComboBox()
        self.symbol_input.addItems(["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA", "AMZN"])
        self.symbol_input.setEditable(True)

        # Quantity
        qty_label = QLabel("Quantity:")
        self.qty_input = QSpinBox()
        self.qty_input.setRange(1, 10000)
        self.qty_input.setValue(100)

        # Action buttons
        buy_btn = QPushButton("🟢 BUY")
        buy_btn.setStyleSheet("background-color: #4ec9b0;")
        buy_btn.setMinimumWidth(120)

        sell_btn = QPushButton("🔴 SELL")
        sell_btn.setStyleSheet("background-color: #f48771;")
        sell_btn.setMinimumWidth(120)

        trade_layout.addWidget(symbol_label)
        trade_layout.addWidget(self.symbol_input)
        trade_layout.addWidget(qty_label)
        trade_layout.addWidget(self.qty_input)
        trade_layout.addWidget(buy_btn)
        trade_layout.addWidget(sell_btn)
        trade_layout.addStretch()

        trade_panel.setLayout(trade_layout)
        layout.addWidget(trade_panel)

        # Positions table
        positions_label = QLabel("📦 Open Positions")
        positions_label.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        layout.addWidget(positions_label)

        self.positions_table = QTableWidget()
        self.positions_table.setColumnCount(8)
        self.positions_table.setHorizontalHeaderLabels(
            ["Symbol", "Qty", "Entry", "Current", "P&L $", "P&L %", "Duration", "Actions"]
        )
        self.positions_table.setAlternatingRowColors(True)
        self._populate_positions_table()

        layout.addWidget(self.positions_table)

        trading.setLayout(layout)
        return trading

    def create_analytics_tab(self) -> QWidget:
        """Create analytics tab"""
        analytics = QWidget()
        layout = QVBoxLayout()

        title = QLabel("📈 Advanced Analytics")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        layout.addWidget(title)

        # Analytics cards
        analytics_grid = QGridLayout()

        # Risk metrics
        risk_card = ModernCard("Risk Metrics", "VaR (95%)", "$2,450", "#f48771")
        sharpe_card = ModernCard("Sharpe Ratio", "1.85", "Excellent", "#4ec9b0")
        drawdown_card = ModernCard("Max Drawdown", "-8.2%", "Acceptable", "#dcdcaa")

        analytics_grid.addWidget(risk_card, 0, 0)
        analytics_grid.addWidget(sharpe_card, 0, 1)
        analytics_grid.addWidget(drawdown_card, 0, 2)

        layout.addLayout(analytics_grid)

        # Add charts placeholder
        chart_placeholder = QLabel("📊 Advanced analytics charts coming soon...")
        chart_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chart_placeholder.setStyleSheet("""
            padding: 100px;
            background-color: #2d2d30;
            border-radius: 10px;
            font-size: 14pt;
            color: #9e9e9e;
        """)
        layout.addWidget(chart_placeholder)

        analytics.setLayout(layout)
        return analytics

    def create_settings_tab(self) -> QWidget:
        """Create settings tab"""
        settings = QWidget()
        layout = QVBoxLayout()

        title = QLabel("⚙️ Settings & Configuration")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        layout.addWidget(title)

        # Settings form
        form_widget = QWidget()
        form_widget.setStyleSheet("""
            QWidget {
                background-color: #2d2d30;
                border-radius: 10px;
                padding: 20px;
            }
        """)
        form_layout = QVBoxLayout()

        # Auto-start
        autostart_check = QCheckBox("🚀 Start Loki automatically on login")
        autostart_check.setChecked(True)
        form_layout.addWidget(autostart_check)

        # AI enabled
        ai_check = QCheckBox("🤖 Enable autonomous AI trading")
        ai_check.setChecked(True)
        form_layout.addWidget(ai_check)

        # Notifications
        notif_check = QCheckBox("🔔 Enable desktop notifications")
        notif_check.setChecked(True)
        form_layout.addWidget(notif_check)

        # Trading style
        style_layout = QHBoxLayout()
        style_label = QLabel("Trading Style:")
        style_combo = QComboBox()
        style_combo.addItems(["Conservative", "Moderate", "Aggressive"])
        style_layout.addWidget(style_label)
        style_layout.addWidget(style_combo)
        style_layout.addStretch()
        form_layout.addLayout(style_layout)

        # Save button
        save_btn = QPushButton("💾 Save Settings")
        save_btn.setMinimumHeight(40)
        form_layout.addWidget(save_btn)

        form_widget.setLayout(form_layout)
        layout.addWidget(form_widget)
        layout.addStretch()

        settings.setLayout(layout)
        return settings

    def _populate_positions_table(self):
        """Populate positions table with sample data"""
        positions = [
            ("AAPL", 100, 175.50, 178.20, 270.00, 1.54, "2h 15m"),
            ("MSFT", 50, 380.00, 382.50, 125.00, 0.66, "1h 30m"),
            ("GOOGL", 25, 140.00, 142.80, 70.00, 2.00, "45m"),
        ]

        self.positions_table.setRowCount(len(positions))
        for row, pos in enumerate(positions):
            for col, value in enumerate(pos):
                item = QTableWidgetItem(str(value))
                if col == 4:  # P&L $
                    if value > 0:
                        item.setForeground(QColor("#4ec9b0"))
                    else:
                        item.setForeground(QColor("#f48771"))
                self.positions_table.setItem(row, col, item)

            # Close button
            close_btn = QPushButton("✖ Close")
            close_btn.setStyleSheet("background-color: #f48771;")
            self.positions_table.setCellWidget(row, 7, close_btn)

    def create_enhanced_status_bar(self):
        """Create enhanced status bar"""
        statusbar = QStatusBar()
        statusbar.setStyleSheet("""
            QStatusBar {
                background-color: #007acc;
                color: #ffffff;
                border: none;
                padding: 5px;
            }
        """)

        self.status_conn = QLabel("🟢 Connected")
        self.status_market = QLabel("📈 Market: OPEN")
        self.status_time = QLabel()

        statusbar.addWidget(self.status_conn)
        statusbar.addWidget(self.status_market)
        statusbar.addPermanentWidget(self.status_time)

        self.setStatusBar(statusbar)

    def create_enhanced_toolbar(self):
        """Create enhanced toolbar"""
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(32, 32))
        toolbar.setStyleSheet("""
            QToolBar {
                background-color: #2d2d30;
                border: none;
                spacing: 10px;
                padding: 10px;
            }
            QToolButton {
                background-color: transparent;
                border-radius: 6px;
                padding: 8px;
                color: #ffffff;
            }
            QToolButton:hover {
                background-color: #3e3e42;
            }
        """)

        refresh_action = QAction("🔄 Refresh", self)
        start_action = QAction("▶️ Start AI", self)
        stop_action = QAction("⏸️ Stop AI", self)
        settings_action = QAction("⚙️ Settings", self)

        toolbar.addAction(refresh_action)
        toolbar.addAction(start_action)
        toolbar.addAction(stop_action)
        toolbar.addSeparator()
        toolbar.addAction(settings_action)

        self.addToolBar(toolbar)

    def setup_system_tray(self):
        """Setup system tray"""
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setToolTip("Loki AI Trading Platform")

        tray_menu = QMenu()
        show_action = QAction("Show Loki", self)
        show_action.triggered.connect(self.show)
        hide_action = QAction("Hide", self)
        hide_action.triggered.connect(self.hide)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(QApplication.quit)

        tray_menu.addAction(show_action)
        tray_menu.addAction(hide_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

    def start_updates(self):
        """Start update timers"""
        # Time update
        time_timer = QTimer(self)
        time_timer.timeout.connect(self.update_time)
        time_timer.start(1000)

        # Chart update
        chart_timer = QTimer(self)
        chart_timer.timeout.connect(self.update_chart)
        chart_timer.start(2000)

        # AI status update
        ai_timer = QTimer(self)
        ai_timer.timeout.connect(self.update_ai_status)
        ai_timer.start(5000)

    def update_time(self):
        """Update time display"""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.status_time.setText(f"🕒 {current_time}")

    def update_chart(self):
        """Update chart with new data"""
        import random

        value = 105000 + random.randint(-1000, 1000)
        self.live_chart.update_data(value)

    def update_ai_status(self):
        """Update AI status"""
        import random

        thinking_states = ["Analyzing market", "Evaluating risk", "Checking patterns", "Idle"]
        states = ["Confident", "Cautious", "Neutral"]

        self.ai_status.update_status(
            thinking=random.choice(thinking_states),
            confidence=random.uniform(60, 95),
            state=random.choice(states),
            decisions=random.randint(10, 50),
        )

    def send_ai_message(self):
        """Send message to AI"""
        message = self.chat_input.toPlainText().strip()
        if not message:
            return

        # Display user message
        self.chat_display.append(f"""
        <div style='background-color: #007acc; padding: 10px; border-radius: 10px; margin: 5px; text-align: right;'>
            <b style='color: #ffffff;'>You:</b><br>
            <span style='color: #ffffff;'>{message}</span>
        </div>
        """)

        # Simulate AI response
        responses = [
            "Based on current market analysis, I recommend a cautious approach...",
            "Technical indicators suggest a bullish trend. Confidence: 78%",
            "I've detected a potential trade opportunity. Let me analyze the risk...",
            "Market sentiment is neutral. I recommend waiting for clearer signals.",
        ]

        import random

        ai_response = random.choice(responses)

        self.chat_display.append(f"""
        <div style='background-color: #2d2d30; padding: 10px; border-radius: 10px; margin: 5px;'>
            <b style='color: #4ec9b0;'>🤖 Loki AI:</b><br>
            <span style='color: #cccccc;'>{ai_response}</span>
        </div>
        """)

        self.chat_input.clear()

        # Scroll to bottom
        self.chat_display.verticalScrollBar().setValue(
            self.chat_display.verticalScrollBar().maximum()
        )


def main():
    """Launch enhanced Loki app"""
    if not PYQT_AVAILABLE:
        print("ERROR: PyQt6 is required!")
        print("Install with: pip install PyQt6 pyqtgraph")
        input("Press Enter to exit...")
        return

    try:
        app = QApplication(sys.argv)
        app.setApplicationName("Loki AI Trading Platform")
        app.setOrganizationName("Loki Trading Systems")

        window = LokiEnhancedApp()
        window.show()

        sys.exit(app.exec())
    except Exception as e:
        print(f"ERROR: {e}")
        print("\nTroubleshooting:")
        print("1. Make sure PyQt6 is installed: pip install PyQt6")
        print("2. Try running: pip install --upgrade PyQt6 pyqtgraph")
        print("3. Check Python version (need 3.10+)")
        input("\nPress Enter to exit...")


if __name__ == "__main__":
    main()
