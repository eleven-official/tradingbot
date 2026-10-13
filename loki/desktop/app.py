"""
Loki Desktop Application - Professional Trading Terminal
Enterprise-grade desktop interface with real-time monitoring
"""
import sys
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QSystemTrayIcon, QMenu, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QSplitter, QStatusBar,
    QToolBar, QMessageBox, QDockWidget
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QSize
from PyQt6.QtGui import QIcon, QAction, QFont, QColor, QPalette
from PyQt6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis, QDateTimeAxis
import pyqtgraph as pg

# Configure logging
logger = logging.getLogger(__name__)


class MarketDataThread(QThread):
    """Background thread for market data updates"""
    data_updated = pyqtSignal(dict)
    
    def __init__(self):
        super().__init__()
        self.running = True
    
    def run(self):
        """Fetch market data in background"""
        while self.running:
            try:
                # TODO: Connect to real market data source
                data = {
                    'timestamp': datetime.now(),
                    'portfolio_value': 105432.50,
                    'daily_pnl': 2156.30,
                    'positions': 5,
                    'open_orders': 2
                }
                self.data_updated.emit(data)
                self.msleep(1000)  # Update every second
            except Exception as e:
                logger.error(f"Market data error: {e}")
    
    def stop(self):
        """Stop the thread"""
        self.running = False


class DashboardWidget(QWidget):
    """Main dashboard with key metrics"""
    
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Header
        header = QLabel("📊 Portfolio Overview")
        header.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        layout.addWidget(header)
        
        # Metrics grid
        metrics_layout = QHBoxLayout()
        
        # Portfolio Value
        self.portfolio_card = self._create_metric_card(
            "Portfolio Value", "$105,432.50", "+2.1%", QColor(34, 139, 34)
        )
        metrics_layout.addWidget(self.portfolio_card)
        
        # Daily P&L
        self.pnl_card = self._create_metric_card(
            "Daily P&L", "$2,156.30", "+2.09%", QColor(34, 139, 34)
        )
        metrics_layout.addWidget(self.pnl_card)
        
        # Open Positions
        self.positions_card = self._create_metric_card(
            "Open Positions", "5", "Active", QColor(30, 144, 255)
        )
        metrics_layout.addWidget(self.positions_card)
        
        # Win Rate
        self.winrate_card = self._create_metric_card(
            "Win Rate", "68.5%", "Last 30 days", QColor(255, 140, 0)
        )
        metrics_layout.addWidget(self.winrate_card)
        
        layout.addLayout(metrics_layout)
        
        # Performance chart
        chart_label = QLabel("📈 Performance Chart (30 Days)")
        chart_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        layout.addWidget(chart_label)
        
        self.chart_view = self._create_performance_chart()
        layout.addWidget(self.chart_view)
        
        self.setLayout(layout)
    
    def _create_metric_card(self, title: str, value: str, subtitle: str, color: QColor) -> QWidget:
        """Create a metric card widget"""
        card = QWidget()
        card.setStyleSheet(f"""
            QWidget {{
                background-color: #2b2b2b;
                border-radius: 8px;
                padding: 15px;
                border: 1px solid #3d3d3d;
            }}
        """)
        
        layout = QVBoxLayout()
        
        title_label = QLabel(title)
        title_label.setFont(QFont("Segoe UI", 10))
        title_label.setStyleSheet("color: #aaaaaa;")
        
        value_label = QLabel(value)
        value_label.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        value_label.setStyleSheet(f"color: {color.name()};")
        
        subtitle_label = QLabel(subtitle)
        subtitle_label.setFont(QFont("Segoe UI", 9))
        subtitle_label.setStyleSheet("color: #888888;")
        
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        layout.addWidget(subtitle_label)
        
        card.setLayout(layout)
        return card
    
    def _create_performance_chart(self) -> QChartView:
        """Create performance line chart"""
        chart = QChart()
        chart.setTitle("")
        chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)
        chart.setTheme(QChart.ChartTheme.ChartThemeDark)
        
        series = QLineSeries()
        series.setName("Portfolio Value")
        
        # Sample data - replace with real data
        for i in range(30):
            series.append(i, 100000 + (i * 150) + (i % 5 * 200))
        
        chart.addSeries(series)
        chart.createDefaultAxes()
        
        chart_view = QChartView(chart)
        chart_view.setRenderHint(chart_view.RenderHint.Antialiasing)
        chart_view.setMinimumHeight(300)
        
        return chart_view
    
    def update_metrics(self, data: dict):
        """Update dashboard metrics"""
        # Update portfolio value
        portfolio_value = data.get('portfolio_value', 0)
        daily_pnl = data.get('daily_pnl', 0)
        
        # TODO: Update the metric cards with new data


class PositionsWidget(QWidget):
    """Active positions table"""
    
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        header = QLabel("📦 Active Positions")
        header.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        layout.addWidget(header)
        
        # Positions table
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Symbol", "Quantity", "Entry Price", "Current Price",
            "P&L", "P&L %", "Duration", "Actions"
        ])
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #2b2b2b;
                alternate-background-color: #323232;
                gridline-color: #3d3d3d;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #1e1e1e;
                padding: 8px;
                border: 1px solid #3d3d3d;
                font-weight: bold;
            }
        """)
        
        # Sample data
        self._add_sample_positions()
        
        layout.addWidget(self.table)
        self.setLayout(layout)
    
    def _add_sample_positions(self):
        """Add sample position data"""
        positions = [
            ("AAPL", 100, 175.50, 178.20, 270.00, 1.54, "2h 15m"),
            ("MSFT", 50, 380.00, 382.50, 125.00, 0.66, "1h 30m"),
            ("GOOGL", 25, 140.00, 142.80, 70.00, 2.00, "45m"),
            ("TSLA", 30, 250.00, 248.50, -45.00, -0.60, "3h 10m"),
            ("NVDA", 15, 485.00, 492.00, 105.00, 1.44, "1h 05m"),
        ]
        
        self.table.setRowCount(len(positions))
        for row, pos in enumerate(positions):
            for col, value in enumerate(pos):
                item = QTableWidgetItem(str(value))
                
                # Color code P&L
                if col == 4:  # P&L column
                    if value > 0:
                        item.setForeground(QColor(34, 139, 34))
                    else:
                        item.setForeground(QColor(220, 20, 60))
                
                self.table.setItem(row, col, item)
            
            # Add close button
            close_btn = QPushButton("Close")
            close_btn.setStyleSheet("""
                QPushButton {
                    background-color: #c82333;
                    color: white;
                    border-radius: 4px;
                    padding: 5px 10px;
                }
                QPushButton:hover {
                    background-color: #a71d2a;
                }
            """)
            self.table.setCellWidget(row, 7, close_btn)


class StrategyWidget(QWidget):
    """Strategy management and monitoring"""
    
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        header = QLabel("🧠 Active Strategies")
        header.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        layout.addWidget(header)
        
        # Strategy table
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Strategy", "Status", "Positions", "Today P&L",
            "Total P&L", "Win Rate", "Actions"
        ])
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #2b2b2b;
                alternate-background-color: #323232;
                gridline-color: #3d3d3d;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #1e1e1e;
                padding: 8px;
                border: 1px solid #3d3d3d;
                font-weight: bold;
            }
        """)
        
        # Sample strategies
        self._add_sample_strategies()
        
        layout.addWidget(self.table)
        self.setLayout(layout)
    
    def _add_sample_strategies(self):
        """Add sample strategy data"""
        strategies = [
            ("Quantum Momentum", "🟢 Active", 3, "$1,245.50", "$12,450.00", "72.5%"),
            ("Neural Network", "🟢 Active", 2, "$890.30", "$8,920.00", "68.0%"),
            ("Mean Reversion", "🟡 Paused", 0, "$0.00", "$5,630.00", "65.5%"),
            ("Trend Following", "🟢 Active", 1, "$420.50", "$4,210.00", "58.2%"),
        ]
        
        self.table.setRowCount(len(strategies))
        for row, strat in enumerate(strategies):
            for col, value in enumerate(strat):
                item = QTableWidgetItem(str(value))
                self.table.setItem(row, col, item)
            
            # Add control buttons
            btn_widget = QWidget()
            btn_layout = QHBoxLayout()
            btn_layout.setContentsMargins(0, 0, 0, 0)
            
            toggle_btn = QPushButton("⏸️")
            config_btn = QPushButton("⚙️")
            
            btn_layout.addWidget(toggle_btn)
            btn_layout.addWidget(config_btn)
            btn_widget.setLayout(btn_layout)
            
            self.table.setCellWidget(row, 6, btn_widget)


class LokiDesktopApp(QMainWindow):
    """Main Loki Desktop Application Window"""
    
    def __init__(self):
        super().__init__()
        self.market_thread: Optional[MarketDataThread] = None
        self.init_ui()
        self.setup_system_tray()
        self.start_market_data()
    
    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("Loki Trading Platform - Professional Edition")
        self.setGeometry(100, 100, 1600, 900)
        
        # Apply dark theme
        self.apply_dark_theme()
        
        # Create menu bar
        self.create_menu_bar()
        
        # Create toolbar
        self.create_toolbar()
        
        # Create main widget
        main_widget = QWidget()
        main_layout = QVBoxLayout()
        
        # Create tab widget
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #3d3d3d;
                background-color: #1e1e1e;
            }
            QTabBar::tab {
                background-color: #2b2b2b;
                color: #ffffff;
                padding: 10px 20px;
                border: 1px solid #3d3d3d;
            }
            QTabBar::tab:selected {
                background-color: #007acc;
            }
        """)
        
        # Add tabs
        self.dashboard = DashboardWidget()
        self.positions = PositionsWidget()
        self.strategies = StrategyWidget()
        
        self.tabs.addTab(self.dashboard, "📊 Dashboard")
        self.tabs.addTab(self.positions, "📦 Positions")
        self.tabs.addTab(self.strategies, "🧠 Strategies")
        self.tabs.addTab(QWidget(), "📈 Analytics")
        self.tabs.addTab(QWidget(), "⚙️ Settings")
        
        main_layout.addWidget(self.tabs)
        main_widget.setLayout(main_layout)
        
        self.setCentralWidget(main_widget)
        
        # Create status bar
        self.create_status_bar()
    
    def apply_dark_theme(self):
        """Apply professional dark theme"""
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(30, 30, 30))
        palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(45, 45, 45))
        palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.Button, QColor(45, 45, 45))
        palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
        palette.setColor(QPalette.ColorRole.Link, QColor(0, 122, 204))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(0, 122, 204))
        palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
        
        self.setPalette(palette)
        
        # Set application-wide stylesheet
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e1e;
            }
            QWidget {
                color: #ffffff;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 10pt;
            }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border-radius: 4px;
                padding: 8px 16px;
                border: none;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
            QPushButton:pressed {
                background-color: #0d5689;
            }
        """)
    
    def create_menu_bar(self):
        """Create application menu bar"""
        menubar = self.menuBar()
        menubar.setStyleSheet("""
            QMenuBar {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QMenuBar::item:selected {
                background-color: #007acc;
            }
            QMenu {
                background-color: #2b2b2b;
                color: #ffffff;
                border: 1px solid #3d3d3d;
            }
            QMenu::item:selected {
                background-color: #007acc;
            }
        """)
        
        # File menu
        file_menu = menubar.addMenu("&File")
        file_menu.addAction(QAction("&New Strategy", self))
        file_menu.addAction(QAction("&Open Configuration", self))
        file_menu.addSeparator()
        exit_action = QAction("&Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Trading menu
        trading_menu = menubar.addMenu("&Trading")
        trading_menu.addAction(QAction("&Start All Strategies", self))
        trading_menu.addAction(QAction("&Stop All Strategies", self))
        trading_menu.addAction(QAction("&Close All Positions", self))
        
        # View menu
        view_menu = menubar.addMenu("&View")
        view_menu.addAction(QAction("&Full Screen", self))
        view_menu.addAction(QAction("&Refresh", self))
        
        # Help menu
        help_menu = menubar.addMenu("&Help")
        help_menu.addAction(QAction("&Documentation", self))
        help_menu.addAction(QAction("&About Loki", self))
    
    def create_toolbar(self):
        """Create application toolbar"""
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(24, 24))
        toolbar.setStyleSheet("""
            QToolBar {
                background-color: #2b2b2b;
                border: none;
                spacing: 5px;
                padding: 5px;
            }
            QToolButton {
                background-color: transparent;
                border-radius: 4px;
                padding: 5px;
            }
            QToolButton:hover {
                background-color: #3d3d3d;
            }
        """)
        
        # Add actions
        start_action = QAction("▶️ Start", self)
        stop_action = QAction("⏸️ Stop", self)
        refresh_action = QAction("🔄 Refresh", self)
        settings_action = QAction("⚙️ Settings", self)
        
        toolbar.addAction(start_action)
        toolbar.addAction(stop_action)
        toolbar.addSeparator()
        toolbar.addAction(refresh_action)
        toolbar.addSeparator()
        toolbar.addAction(settings_action)
        
        self.addToolBar(toolbar)
    
    def create_status_bar(self):
        """Create status bar with live updates"""
        statusbar = QStatusBar()
        statusbar.setStyleSheet("""
            QStatusBar {
                background-color: #2b2b2b;
                color: #ffffff;
                border-top: 1px solid #3d3d3d;
            }
        """)
        
        # Connection status
        self.conn_label = QLabel("🟢 Connected")
        self.conn_label.setStyleSheet("color: #4ec9b0;")
        
        # Market status
        self.market_label = QLabel("📈 Market: OPEN")
        
        # Time
        self.time_label = QLabel()
        self.update_time()
        
        statusbar.addWidget(self.conn_label)
        statusbar.addWidget(self.market_label)
        statusbar.addPermanentWidget(self.time_label)
        
        self.setStatusBar(statusbar)
        
        # Update time every second
        timer = QTimer(self)
        timer.timeout.connect(self.update_time)
        timer.start(1000)
    
    def update_time(self):
        """Update status bar time"""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.time_label.setText(f"🕒 {current_time}")
    
    def setup_system_tray(self):
        """Setup system tray icon"""
        self.tray_icon = QSystemTrayIcon(self)
        # self.tray_icon.setIcon(QIcon("loki_icon.png"))  # Add icon file
        
        # Create tray menu
        tray_menu = QMenu()
        show_action = QAction("Show Loki", self)
        show_action.triggered.connect(self.show)
        hide_action = QAction("Hide Loki", self)
        hide_action.triggered.connect(self.hide)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(QApplication.quit)
        
        tray_menu.addAction(show_action)
        tray_menu.addAction(hide_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()
    
    def start_market_data(self):
        """Start background market data updates"""
        self.market_thread = MarketDataThread()
        self.market_thread.data_updated.connect(self.on_market_data_update)
        self.market_thread.start()
    
    def on_market_data_update(self, data: dict):
        """Handle market data updates"""
        self.dashboard.update_metrics(data)
    
    def closeEvent(self, event):
        """Handle window close event"""
        reply = QMessageBox.question(
            self, 'Confirm Exit',
            'Are you sure you want to exit Loki Trading Platform?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            if self.market_thread:
                self.market_thread.stop()
                self.market_thread.wait()
            event.accept()
        else:
            event.ignore()


def main():
    """Main entry point for desktop application"""
    app = QApplication(sys.argv)
    app.setApplicationName("Loki Trading Platform")
    app.setOrganizationName("Loki Trading Systems")
    
    window = LokiDesktopApp()
    window.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
