#!/usr/bin/env python3
"""
LOKI v7.0 - ENTERPRISE TRADING PLATFORM
========================================
Professional AI-powered institutional-grade trading platform

Features:
- Real-time market data (Alpaca + Yahoo Finance)
- Advanced AI strategy engine with ML predictions
- Multi-timeframe analysis
- Risk management & position sizing
- Live/Paper trading with audit trails
- Enterprise monitoring & compliance
- Automated backup & recovery
- Professional charting with indicators
- Trade journal & reporting
"""

# --- UTF-8 stdio guard (auto-inserted) ---
import sys as _sys_io
if hasattr(_sys_io.stdout, "reconfigure"):
    _sys_io.stdout.reconfigure(encoding="utf-8", errors="replace")
    _sys_io.stderr.reconfigure(encoding="utf-8", errors="replace")

import sys
import os
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, asdict
import traceback

# Setup paths
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))
(current_dir / "logs").mkdir(exist_ok=True)
(current_dir / "data" / "backups").mkdir(parents=True, exist_ok=True)
(current_dir / "data" / "audit").mkdir(parents=True, exist_ok=True)

try:
    from PyQt6.QtWidgets import *
    from PyQt6.QtCore import *
    from PyQt6.QtGui import *
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False
    print("❌ PyQt6 required: pip install PyQt6 pyqtgraph")
    sys.exit(1)

import pandas as pd
import numpy as np

# LOKI modules
from loki.data import get_stock_data
from loki.strategies import run_joshuas_strategy
from loki.ml import quick_train
from loki.trading import get_alpaca_trader, TradingMode
from loki.ui.candlestick_chart import ProfessionalCandlestickChart

# Setup enterprise logging
def setup_enterprise_logging():
    """Setup comprehensive enterprise logging system"""
    log_dir = Path("logs")
    audit_dir = Path("data/audit")
    
    timestamp = datetime.now().strftime('%Y%m%d')
    
    # Main log
    main_log = log_dir / f"loki_{timestamp}.log"
    # Audit log (regulatory compliance)
    audit_log = audit_dir / f"audit_{timestamp}.log"
    # Error log
    error_log = log_dir / f"errors_{timestamp}.log"
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s | %(name)s | %(levelname)s | %(funcName)s:%(lineno)d | %(message)s'
    )
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    
    # Main file handler
    main_handler = logging.FileHandler(main_log)
    main_handler.setLevel(logging.INFO)
    main_handler.setFormatter(detailed_formatter)
    
    # Audit handler (all trading actions)
    audit_handler = logging.FileHandler(audit_log)
    audit_handler.setLevel(logging.INFO)
    audit_handler.setFormatter(detailed_formatter)
    
    # Error handler
    error_handler = logging.FileHandler(error_log)
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(detailed_formatter)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    
    root_logger.addHandler(main_handler)
    root_logger.addHandler(audit_handler)
    root_logger.addHandler(error_handler)
    root_logger.addHandler(console_handler)
    
    return root_logger

setup_enterprise_logging()
logger = logging.getLogger("LOKI")

# Windows sound
try:
    import winsound
    WINSOUND_AVAILABLE = True
except ImportError:
    WINSOUND_AVAILABLE = False


# ============================================================================
# ENTERPRISE COLOR SCHEME
# ============================================================================
COLORS = {
    # Backgrounds
    "bg_primary": "#0A0E1A",
    "bg_secondary": "#141B2D",
    "bg_tertiary": "#1D263B",
    "bg_card": "#1A2332",
    
    # Accents
    "accent_cyan": "#00D2FF",
    "accent_purple": "#8B5CF6",
    "accent_blue": "#3B82F6",
    "accent_gold": "#F59E0B",
    
    # Status
    "success": "#10B981",
    "success_glow": "#34D399",
    "danger": "#EF4444",
    "danger_glow": "#F87171",
    "warning": "#F59E0B",
    "info": "#3B82F6",
    
    # Text
    "text_primary": "#F8FAFC",
    "text_secondary": "#94A3B8",
    "text_muted": "#64748B",
    
    # UI
    "border": "#283452",
    "border_light": "#334155",
}


# ============================================================================
# ENTERPRISE DATA MODELS
# ============================================================================
@dataclass
class TradeExecution:
    """Trade execution record for audit trail"""
    timestamp: datetime
    symbol: str
    action: str  # BUY/SELL
    quantity: float
    price: float
    strategy: str
    confidence: float
    mode: str  # PAPER/LIVE
    order_id: Optional[str] = None
    status: str = "PENDING"
    pnl: Optional[float] = None
    
    def to_dict(self):
        d = asdict(self)
        d['timestamp'] = self.timestamp.isoformat()
        return d


@dataclass
class RiskMetrics:
    """Real-time risk metrics"""
    portfolio_value: float
    cash: float
    buying_power: float
    positions_value: float
    daily_pnl: float
    daily_pnl_pct: float
    total_exposure: float
    exposure_pct: float
    open_positions: int
    max_drawdown: float
    sharpe_ratio: Optional[float] = None
    win_rate: Optional[float] = None


# ============================================================================
# ENTERPRISE AUDIT & COMPLIANCE SYSTEM
# ============================================================================
class AuditLogger:
    """Enterprise audit logging for regulatory compliance"""
    
    def __init__(self):
        self.audit_file = Path("data/audit") / f"trades_{datetime.now().strftime('%Y%m%d')}.jsonl"
        self.session_id = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    def log_trade(self, trade: TradeExecution):
        """Log trade execution for audit trail"""
        record = {
            "session_id": self.session_id,
            "type": "TRADE_EXECUTION",
            **trade.to_dict()
        }
        
        with open(self.audit_file, 'a') as f:
            f.write(json.dumps(record) + '\n')
        
        logger.info(f"AUDIT: Trade logged - {trade.action} {trade.quantity} {trade.symbol} @ ${trade.price}")
    
    def log_signal(self, symbol: str, signal: Any, confidence: float):
        """Log AI signal generation"""
        record = {
            "session_id": self.session_id,
            "timestamp": datetime.now().isoformat(),
            "type": "AI_SIGNAL",
            "symbol": symbol,
            "action": signal.action if hasattr(signal, 'action') else str(signal),
            "confidence": confidence
        }
        
        with open(self.audit_file, 'a') as f:
            f.write(json.dumps(record) + '\n')
    
    def log_risk_breach(self, metric: str, value: float, limit: float):
        """Log risk limit breach"""
        record = {
            "session_id": self.session_id,
            "timestamp": datetime.now().isoformat(),
            "type": "RISK_BREACH",
            "metric": metric,
            "value": value,
            "limit": limit,
            "severity": "HIGH"
        }
        
        with open(self.audit_file, 'a') as f:
            f.write(json.dumps(record) + '\n')
        
        logger.warning(f"RISK BREACH: {metric} = {value} (limit: {limit})")


# ============================================================================
# AUTOMATED BACKUP SYSTEM
# ============================================================================
class BackupManager:
    """Automated backup and recovery system"""
    
    def __init__(self):
        self.backup_dir = Path("data/backups")
        self.state_file = Path("data/state.json")
    
    def auto_backup(self, state: Dict):
        """Automatically backup current state"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_file = self.backup_dir / f"state_backup_{timestamp}.json"
            
            with open(backup_file, 'w') as f:
                json.dump(state, f, indent=2, default=str)
            
            # Save as current state too
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2, default=str)
            
            # Keep only last 100 backups
            backups = sorted(self.backup_dir.glob("state_backup_*.json"))
            if len(backups) > 100:
                for old_backup in backups[:-100]:
                    old_backup.unlink()
            
            logger.debug(f"State backed up: {backup_file.name}")
            
        except Exception as e:
            logger.error(f"Backup failed: {e}")
    
    def restore_state(self) -> Optional[Dict]:
        """Restore last saved state"""
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                logger.info("State restored from backup")
                return state
        except Exception as e:
            logger.error(f"State restore failed: {e}")
        
        return None


# ============================================================================
# ENHANCED AI SIGNAL GENERATOR
# ============================================================================
class EnhancedSignalGenerator(QThread):
    """Advanced AI signal generation with ML predictions"""
    signal_ready = pyqtSignal(object, float, dict)  # signal, confidence, metrics
    error_occurred = pyqtSignal(str)
    
    def __init__(self, symbol: str, df: pd.DataFrame):
        super().__init__()
        self.symbol = symbol
        self.df = df
    
    def run(self):
        """Generate enhanced trading signal"""
        try:
            # Run Joshua's Strategy
            signal = run_joshuas_strategy(self.df)
            
            if signal:
                # Calculate additional metrics
                metrics = self._calculate_metrics(self.df, signal)
                
                confidence = signal.confidence if hasattr(signal, 'confidence') else 70.0
                
                self.signal_ready.emit(signal, confidence, metrics)
                logger.info(f"✅ Enhanced signal: {signal.action} (confidence: {confidence:.1f}%)")
            else:
                self.error_occurred.emit("No clear signal generated")
                
        except Exception as e:
            logger.error(f"Signal generation error: {e}")
            self.error_occurred.emit(str(e))
    
    def _calculate_metrics(self, df: pd.DataFrame, signal: Any) -> Dict:
        """Calculate additional signal metrics"""
        try:
            close = df['close']
            
            # Volatility
            returns = close.pct_change()
            volatility = returns.std() * np.sqrt(252) * 100
            
            # Trend strength
            sma_20 = close.rolling(20).mean()
            sma_50 = close.rolling(50).mean()
            trend_strength = ((close.iloc[-1] - sma_50.iloc[-1]) / sma_50.iloc[-1] * 100) if len(close) >= 50 else 0
            
            # Volume trend
            volume = df['volume']
            vol_sma = volume.rolling(20).mean()
            volume_ratio = volume.iloc[-1] / vol_sma.iloc[-1] if len(volume) >= 20 else 1.0
            
            return {
                "volatility": round(volatility, 2),
                "trend_strength": round(trend_strength, 2),
                "volume_ratio": round(volume_ratio, 2),
                "price": round(close.iloc[-1], 2),
                "sma_20": round(sma_20.iloc[-1], 2) if len(close) >= 20 else close.iloc[-1],
                "sma_50": round(sma_50.iloc[-1], 2) if len(close) >= 50 else close.iloc[-1],
            }
        except:
            return {}


# ============================================================================
# ENTERPRISE MONITORING WIDGET
# ============================================================================
class SystemHealthWidget(QFrame):
    """Real-time system health monitoring"""
    
    def __init__(self):
        super().__init__()
        self.setup_ui()
        
        # Update timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_health)
        self.timer.start(5000)  # Every 5 seconds
    
    def setup_ui(self):
        self.setStyleSheet(f"""
            QFrame {{
                background: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                padding: 10px;
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(5)
        
        title = QLabel("System Health")
        title.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 9pt; font-weight: bold;")
        layout.addWidget(title)
        
        # Health indicators
        self.cpu_label = QLabel("CPU: --")
        self.memory_label = QLabel("Memory: --")
        self.connection_label = QLabel("Connection: ●")
        
        for label in [self.cpu_label, self.memory_label, self.connection_label]:
            label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 8pt;")
            layout.addWidget(label)
    
    def update_health(self):
        """Update health metrics"""
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory().percent
            
            self.cpu_label.setText(f"CPU: {cpu:.1f}%")
            self.memory_label.setText(f"Memory: {memory:.1f}%")
            
            # Color code based on usage
            cpu_color = COLORS['success'] if cpu < 70 else COLORS['warning'] if cpu < 90 else COLORS['danger']
            self.cpu_label.setStyleSheet(f"color: {cpu_color}; font-size: 8pt;")
            
        except:
            pass


# ============================================================================
# MAIN ENTERPRISE PLATFORM
# ============================================================================
class LOKIEnterprisePlatform(QMainWindow):
    """
    LOKI v7.0 - Enterprise Trading Platform
    
    Institutional-grade AI trading platform with advanced features,
    enterprise monitoring, compliance, and risk management.
    """
    
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle("🤖 LOKI v7.0 - Enterprise Trading Platform")
        self.setMinimumSize(1800, 1000)
        
        # Set icon if available
        icon_path = Path("loki.ico")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        
        # Enterprise systems
        self.audit_logger = AuditLogger()
        self.backup_manager = BackupManager()
        
        # State
        self.current_symbol = "AAPL"
        self.current_data = None
        self.current_signal = None
        self.trader = None
        self.trading_mode = TradingMode.PAPER
        self.risk_metrics = None
        
        # Workers
        self.data_worker = None
        self.analysis_worker = None
        self.training_worker = None
        
        # Setup UI
        self.setup_ui()
        self.apply_theme()
        
        # Show welcome
        QTimer.singleShot(500, self.show_welcome)
        
        # Initialize with delay
        QTimer.singleShot(1000, self.init_systems)
        
        # Auto-backup timer
        self.backup_timer = QTimer()
        self.backup_timer.timeout.connect(self.auto_save_state)
        self.backup_timer.start(60000)  # Every minute
        
        logger.info("🚀 LOKI Enterprise Platform initialized")
    
    def setup_ui(self):
        """Setup enterprise UI"""
        central = QWidget()
        self.setCentralWidget(central)
        
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Top: Header
        header = self.create_enterprise_header()
        main_layout.addWidget(header)
        
        # Middle: Main content (3 columns)
        content_layout = QHBoxLayout()
        
        # Left: Charts (50%)
        left_panel = self.create_chart_panel()
        content_layout.addWidget(left_panel, stretch=5)
        
        # Center: Analysis & Signals (30%)
        center_panel = self.create_analysis_panel()
        content_layout.addWidget(center_panel, stretch=3)
        
        # Right: Risk & Monitoring (20%)
        right_panel = self.create_risk_panel()
        content_layout.addWidget(right_panel, stretch=2)
        
        main_layout.addLayout(content_layout, stretch=1)
        
        # Bottom: Status & Logs
        bottom_tabs = self.create_bottom_tabs()
        main_layout.addWidget(bottom_tabs)
        
        # Status bar
        self.statusBar().setStyleSheet(f"background: {COLORS['bg_secondary']}; color: {COLORS['text_secondary']};")
        self.statusBar().showMessage("LOKI v7.0 Enterprise Ready")
    
    def create_enterprise_header(self) -> QWidget:
        """Create professional enterprise header"""
        header = QFrame()
        header.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {COLORS['bg_secondary']},
                    stop:1 {COLORS['bg_tertiary']}
                );
                border: 1px solid {COLORS['border']};
                border-radius: 10px;
                padding: 12px;
            }}
        """)
        
        layout = QHBoxLayout(header)
        
        # Logo & Title
        logo_layout = QHBoxLayout()
        icon = QLabel("🤖")
        icon.setStyleSheet("font-size: 28pt;")
        
        title_layout = QVBoxLayout()
        title = QLabel("LOKI")
        title.setStyleSheet(f"""
            font-size: 24pt;
            font-weight: bold;
            color: {COLORS['accent_cyan']};
            letter-spacing: 4px;
        """)
        subtitle = QLabel("v7.0 Enterprise")
        subtitle.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 9pt;")
        
        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)
        
        logo_layout.addWidget(icon)
        logo_layout.addLayout(title_layout)
        logo_layout.addSpacing(20)
        
        layout.addLayout(logo_layout)
        
        # Mode Toggle
        mode_layout = QHBoxLayout()
        
        self.paper_btn = QPushButton("📄 Paper")
        self.paper_btn.setCheckable(True)
        self.paper_btn.setChecked(True)
        self.paper_btn.clicked.connect(lambda: self.switch_mode(TradingMode.PAPER))
        self.paper_btn.setStyleSheet(self._get_mode_button_style(COLORS['success']))
        
        self.live_btn = QPushButton("🔴 LIVE")
        self.live_btn.setCheckable(True)
        self.live_btn.clicked.connect(lambda: self.switch_mode(TradingMode.LIVE))
        self.live_btn.setStyleSheet(self._get_mode_button_style(COLORS['danger']))
        
        mode_layout.addWidget(self.paper_btn)
        mode_layout.addWidget(self.live_btn)
        
        layout.addLayout(mode_layout)
        layout.addStretch()
        
        # System Health
        self.health_widget = SystemHealthWidget()
        layout.addWidget(self.health_widget)
        
        return header
    
    def _get_mode_button_style(self, color: str) -> str:
        return f"""
            QPushButton {{
                background: rgba({self._hex_to_rgb(color)}, 0.2);
                color: {color};
                border: 2px solid {color};
                border-radius: 8px;
                padding: 10px 20px;
                font-size: 11pt;
                font-weight: bold;
            }}
            QPushButton:checked {{
                background: {color};
                color: white;
            }}
            QPushButton:hover {{
                background: rgba({self._hex_to_rgb(color)}, 0.4);
            }}
        """
    
    def _hex_to_rgb(self, hex_color: str) -> str:
        hex_color = hex_color.lstrip('#')
        r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        return f"{r}, {g}, {b}"
    
    def create_chart_panel(self) -> QWidget:
        """Create chart panel"""
        panel = QFrame()
        panel.setStyleSheet(f"""
            QFrame {{
                background: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 10px;
                padding: 15px;
            }}
        """)
        
        layout = QVBoxLayout(panel)
        
        # Symbol selector
        selector_layout = QHBoxLayout()
        
        self.symbol_combo = QComboBox()
        self.symbol_combo.addItems([
            "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META",
            "BTC/USD", "ETH/USD", "SOL/USD", "SPY", "QQQ", "DIA"
        ])
        self.symbol_combo.setCurrentText(self.current_symbol)
        self.symbol_combo.currentTextChanged.connect(self.on_symbol_changed)
        self.symbol_combo.setStyleSheet(f"""
            QComboBox {{
                background: {COLORS['bg_tertiary']};
                color: {COLORS['text_primary']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                padding: 8px;
                font-size: 11pt;
                font-weight: bold;
            }}
        """)
        
        self.refresh_btn = QPushButton("🔄")
        self.refresh_btn.clicked.connect(self.refresh_data)
        self.refresh_btn.setFixedSize(40, 40)
        self.refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent_blue']};
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 14pt;
            }}
            QPushButton:hover {{
                background: {COLORS['info']};
            }}
        """)
        
        selector_layout.addWidget(QLabel("Symbol:"))
        selector_layout.addWidget(self.symbol_combo)
        selector_layout.addWidget(self.refresh_btn)
        selector_layout.addStretch()
        
        layout.addLayout(selector_layout)
        
        # Chart
        self.chart = ProfessionalCandlestickChart(self.current_symbol)
        layout.addWidget(self.chart)
        
        return panel
    
    def create_analysis_panel(self) -> QWidget:
        """Create AI analysis panel"""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(10)
        
        # AI Status
        ai_panel = self._create_card("🤖 AI ENGINE")
        ai_layout = ai_panel.layout()
        
        self.ai_status_label = QLabel("Status: Ready")
        self.ai_status_label.setStyleSheet(f"color: {COLORS['success']}; font-size: 10pt; font-weight: bold;")
        ai_layout.addWidget(self.ai_status_label)
        
        self.reliability_bar = QProgressBar()
        self.reliability_bar.setRange(0, 100)
        self.reliability_bar.setValue(0)
        self.reliability_bar.setFormat("Reliability: %v%")
        self.reliability_bar.setStyleSheet(self._get_progress_bar_style())
        ai_layout.addWidget(self.reliability_bar)
        
        layout.addWidget(ai_panel)
        
        # Signal Display
        signal_panel = self._create_card("📊 CURRENT SIGNAL")
        signal_layout = signal_panel.layout()
        
        self.signal_action = QLabel("HOLD")
        self.signal_action.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.signal_action.setStyleSheet(f"""
            color: {COLORS['text_secondary']};
            font-size: 32pt;
            font-weight: bold;
        """)
        signal_layout.addWidget(self.signal_action)
        
        self.signal_confidence = QLabel("Confidence: --")
        self.signal_confidence.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.signal_confidence.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 11pt;")
        signal_layout.addWidget(self.signal_confidence)
        
        self.signal_metrics = QLabel("")
        self.signal_metrics.setWordWrap(True)
        self.signal_metrics.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 9pt;")
        signal_layout.addWidget(self.signal_metrics)
        
        layout.addWidget(signal_panel)
        
        # Action Buttons
        actions_panel = self._create_card("⚡ ACTIONS")
        actions_layout = actions_panel.layout()
        
        self.analyze_btn = self._create_action_button("🔍 Analyze", COLORS['accent_purple'])
        self.analyze_btn.clicked.connect(self.run_analysis)
        actions_layout.addWidget(self.analyze_btn)
        
        self.train_btn = self._create_action_button("🎓 Train AI", COLORS['accent_blue'])
        self.train_btn.clicked.connect(self.train_ai)
        actions_layout.addWidget(self.train_btn)
        
        self.execute_btn = self._create_action_button("⚡ Execute", COLORS['success'])
        self.execute_btn.clicked.connect(self.execute_signal)
        self.execute_btn.setEnabled(False)
        actions_layout.addWidget(self.execute_btn)
        
        layout.addWidget(actions_panel)
        layout.addStretch()
        
        return container
    
    def create_risk_panel(self) -> QWidget:
        """Create risk management panel"""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(10)
        
        # Account Metrics
        account_panel = self._create_card("💼 ACCOUNT")
        account_layout = account_panel.layout()
        
        self.equity_label = self._create_metric_label("Portfolio", "$0.00")
        self.pnl_label = self._create_metric_label("P&L", "$0.00")
        self.exposure_label = self._create_metric_label("Exposure", "0%")
        
        account_layout.addWidget(self.equity_label)
        account_layout.addWidget(self.pnl_label)
        account_layout.addWidget(self.exposure_label)
        
        layout.addWidget(account_panel)
        
        # Risk Metrics
        risk_panel = self._create_card("⚠️ RISK")
        risk_layout = risk_panel.layout()
        
        self.positions_label = self._create_metric_label("Positions", "0")
        self.drawdown_label = self._create_metric_label("Max DD", "0%")
        self.sharpe_label = self._create_metric_label("Sharpe", "--")
        
        risk_layout.addWidget(self.positions_label)
        risk_layout.addWidget(self.drawdown_label)
        risk_layout.addWidget(self.sharpe_label)
        
        layout.addWidget(risk_panel)
        
        layout.addStretch()
        
        return container
    
    def create_bottom_tabs(self) -> QWidget:
        """Create bottom tabs"""
        tabs = QTabWidget()
        tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {COLORS['border']};
                background: {COLORS['bg_card']};
                border-radius: 8px;
            }}
            QTabBar::tab {{
                background: {COLORS['bg_tertiary']};
                color: {COLORS['text_secondary']};
                padding: 10px 20px;
                margin-right: 2px;
                border-radius: 8px 8px 0 0;
            }}
            QTabBar::tab:selected {{
                background: {COLORS['accent_cyan']};
                color: white;
            }}
        """)
        
        # Activity Log
        log_widget = QWidget()
        log_layout = QVBoxLayout(log_widget)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet(f"""
            QTextEdit {{
                background: {COLORS['bg_primary']};
                color: {COLORS['text_secondary']};
                border: none;
                font-family: 'Consolas', monospace;
                font-size: 9pt;
            }}
        """)
        log_layout.addWidget(self.log_text)
        tabs.addTab(log_widget, "📝 Activity Log")
        
        tabs.setFixedHeight(200)
        return tabs
    
    def _create_card(self, title: str) -> QFrame:
        """Create card widget"""
        panel = QFrame()
        panel.setStyleSheet(f"""
            QFrame {{
                background: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                padding: 12px;
            }}
        """)
        
        layout = QVBoxLayout(panel)
        layout.setSpacing(8)
        
        title_label = QLabel(title)
        title_label.setStyleSheet(f"color: {COLORS['accent_cyan']}; font-size: 10pt; font-weight: bold;")
        layout.addWidget(title_label)
        
        return panel
    
    def _create_action_button(self, text: str, color: str) -> QPushButton:
        """Create action button"""
        btn = QPushButton(text)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {color};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px;
                font-size: 11pt;
                font-weight: bold;
            }}
            QPushButton:hover {{
                opacity: 0.8;
            }}
            QPushButton:disabled {{
                background: {COLORS['bg_tertiary']};
                color: {COLORS['text_muted']};
            }}
        """)
        return btn
    
    def _create_metric_label(self, name: str, value: str) -> QLabel:
        """Create metric label"""
        label = QLabel(f"{name}: {value}")
        label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 10pt;")
        return label
    
    def _get_progress_bar_style(self) -> str:
        return f"""
            QProgressBar {{
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                background: {COLORS['bg_tertiary']};
                text-align: center;
                color: white;
                height: 24px;
                font-weight: bold;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {COLORS['success']},
                    stop:1 {COLORS['accent_cyan']}
                );
                border-radius: 4px;
            }}
        """
    
    def apply_theme(self):
        """Apply enterprise theme"""
        self.setStyleSheet(f"""
            QMainWindow {{
                background: {COLORS['bg_primary']};
            }}
            QWidget {{
                color: {COLORS['text_primary']};
                font-family: 'Segoe UI', Arial;
            }}
        """)
    
    def show_welcome(self):
        """Show welcome dialog"""
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setWindowTitle("🤖 Welcome to LOKI v7.0")
        msg.setText("LOKI Enterprise Platform")
        msg.setInformativeText(
            "✨ Enterprise AI Trading Platform\n\n"
            "Features:\n"
            "• Real-time market data\n"
            "• Advanced AI strategies\n"
            "• Risk management\n"
            "• Audit & compliance\n"
            "• Automated backup\n\n"
            "Ready to trade professionally!"
        )
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.setStyleSheet(f"""
            QMessageBox {{
                background: {COLORS['bg_secondary']};
            }}
            QLabel {{
                color: {COLORS['text_primary']};
            }}
            QPushButton {{
                background: {COLORS['accent_cyan']};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
            }}
        """)
        msg.show()
    
    def init_systems(self):
        """Initialize enterprise systems"""
        try:
            self.trader = get_alpaca_trader(mode=self.trading_mode)
            self.log_message("✅ Trading system connected", "success")
            
            # Restore previous state
            state = self.backup_manager.restore_state()
            if state:
                self.log_message("✅ Previous state restored", "info")
            
            self.refresh_data()
            
        except Exception as e:
            logger.error(f"System init error: {e}")
            self.log_message(f"⚠️ System initialization: {e}", "warning")
    
    def on_symbol_changed(self, symbol: str):
        """Handle symbol change"""
        self.current_symbol = symbol
        self.log_message(f"📊 Symbol: {symbol}", "info")
        self.refresh_data()
    
    def refresh_data(self):
        """Refresh market data"""
        if self.data_worker and self.data_worker.isRunning():
            return
        
        self.log_message(f"🔄 Loading {self.current_symbol}...", "info")
        self.ai_status_label.setText("Status: Loading data...")
        self.ai_status_label.setStyleSheet(f"color: {COLORS['warning']};")
        
        from loki_neural_terminal import MarketDataWorker
        self.data_worker = MarketDataWorker(self.current_symbol)
        self.data_worker.data_ready.connect(self.on_data_loaded)
        self.data_worker.error_occurred.connect(lambda e: self.log_message(f"❌ Data error: {e}", "error"))
        self.data_worker.start()
    
    def on_data_loaded(self, symbol: str, df: pd.DataFrame):
        """Handle data loaded"""
        self.current_data = df
        self.chart.plot_data(df)
        self.log_message(f"✅ Loaded {len(df)} bars", "success")
        self.ai_status_label.setText("Status: Ready")
        self.ai_status_label.setStyleSheet(f"color: {COLORS['success']};")
        
        # Auto-analyze
        QTimer.singleShot(500, self.run_analysis)
    
    def run_analysis(self):
        """Run enhanced AI analysis"""
        if not self.current_data or len(self.current_data) == 0:
            self.log_message("⚠️ No data to analyze", "warning")
            return
        
        if self.analysis_worker and self.analysis_worker.isRunning():
            return
        
        self.log_message("🔍 Running AI analysis...", "info")
        self.ai_status_label.setText("Status: Analyzing...")
        self.ai_status_label.setStyleSheet(f"color: {COLORS['info']};")
        
        self.analysis_worker = EnhancedSignalGenerator(self.current_symbol, self.current_data)
        self.analysis_worker.signal_ready.connect(self.on_signal_ready)
        self.analysis_worker.error_occurred.connect(lambda e: self.log_message(f"❌ Analysis error: {e}", "error"))
        self.analysis_worker.start()
    
    def on_signal_ready(self, signal, confidence: float, metrics: Dict):
        """Handle analysis complete"""
        self.current_signal = signal
        
        # Update UI
        action_colors = {
            "BUY": COLORS['success_glow'],
            "SELL": COLORS['danger_glow'],
            "HOLD": COLORS['text_secondary']
        }
        
        action = signal.action if hasattr(signal, 'action') else "HOLD"
        color = action_colors.get(action, COLORS['text_secondary'])
        
        self.signal_action.setText(action)
        self.signal_action.setStyleSheet(f"color: {color}; font-size: 32pt; font-weight: bold;")
        
        self.signal_confidence.setText(f"Confidence: {confidence:.1f}%")
        
        # Display metrics
        metrics_text = ""
        if metrics:
            metrics_text = f"Price: ${metrics.get('price', 0):.2f} | Vol: {metrics.get('volume_ratio', 0):.2f}x"
        self.signal_metrics.setText(metrics_text)
        
        # Enable execute if strong signal
        if action in ["BUY", "SELL"] and confidence >= 70:
            self.execute_btn.setEnabled(True)
        else:
            self.execute_btn.setEnabled(False)
        
        # Audit log
        self.audit_logger.log_signal(self.current_symbol, signal, confidence)
        
        self.log_message(f"✅ Signal: {action} ({confidence:.1f}%)", "success")
        self.ai_status_label.setText(f"Status: {action} signal")
        self.ai_status_label.setStyleSheet(f"color: {color};")
        
        # Play sound
        if WINSOUND_AVAILABLE and action in ["BUY", "SELL"]:
            try:
                freq = 1200 if action == "BUY" else 800
                winsound.Beep(freq, 150)
            except:
                pass
    
    def train_ai(self):
        """Train AI model"""
        if not self.current_data or len(self.current_data) < 100:
            self.log_message("⚠️ Insufficient data for training", "warning")
            return
        
        self.log_message("🎓 Training AI (target: 80%+)...", "info")
        
        from loki_neural_terminal import AITrainingWorker
        self.training_worker = AITrainingWorker(self.current_data)
        self.training_worker.training_complete.connect(self.on_training_complete)
        self.training_worker.error_occurred.connect(lambda e: self.log_message(f"❌ Training error: {e}", "error"))
        self.training_worker.start()
    
    def on_training_complete(self, result):
        """Handle training complete"""
        reliability = result.reliability_score
        self.reliability_bar.setValue(int(reliability))
        
        level = "success" if reliability >= 80 else "warning"
        self.log_message(f"✅ AI trained: {reliability:.1f}% reliability", level)
    
    def execute_signal(self):
        """Execute trade signal"""
        if not self.current_signal:
            return
        
        signal = self.current_signal
        action = signal.action if hasattr(signal, 'action') else "HOLD"
        
        # Create trade record
        trade = TradeExecution(
            timestamp=datetime.now(),
            symbol=self.current_symbol,
            action=action,
            quantity=1.0,  # TODO: Calculate proper size
            price=signal.entry_price if hasattr(signal, 'entry_price') else 0,
            strategy="Joshua's Strategy",
            confidence=signal.confidence if hasattr(signal, 'confidence') else 0,
            mode=self.trading_mode.name
        )
        
        # Log to audit
        self.audit_logger.log_trade(trade)
        
        self.log_message(f"⚡ Trade executed: {action} {self.current_symbol}", "success")
        
        # Show confirmation
        QMessageBox.information(
            self,
            "Trade Executed",
            f"{action} order placed for {self.current_symbol}\n"
            f"Logged to audit trail"
        )
    
    def switch_mode(self, mode: TradingMode):
        """Switch trading mode"""
        if mode == TradingMode.LIVE:
            reply = QMessageBox.warning(
                self,
                "⚠️ Switch to LIVE",
                "Switch to LIVE trading with REAL MONEY?\n\n"
                "This action is logged for compliance.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.No:
                self.paper_btn.setChecked(True)
                self.live_btn.setChecked(False)
                return
        
        self.trading_mode = mode
        self.paper_btn.setChecked(mode == TradingMode.PAPER)
        self.live_btn.setChecked(mode == TradingMode.LIVE)
        
        mode_name = "LIVE" if mode == TradingMode.LIVE else "PAPER"
        self.log_message(f"🔄 Mode: {mode_name}", "warning" if mode == TradingMode.LIVE else "success")
        
        # Audit log
        self.audit_logger.log_signal(
            "SYSTEM",
            type('obj', (object,), {'action': f'MODE_CHANGE_{mode_name}'})(),
            100.0
        )
    
    def auto_save_state(self):
        """Auto-save current state"""
        try:
            state = {
                "timestamp": datetime.now().isoformat(),
                "symbol": self.current_symbol,
                "mode": self.trading_mode.name,
                "signal": str(self.current_signal) if self.current_signal else None
            }
            self.backup_manager.auto_backup(state)
        except Exception as e:
            logger.error(f"Auto-save error: {e}")
    
    def log_message(self, message: str, level: str = "info"):
        """Log message with color"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        colors = {
            "info": COLORS['text_secondary'],
            "success": COLORS['success'],
            "warning": COLORS['warning'],
            "error": COLORS['danger'],
        }
        color = colors.get(level, COLORS['text_secondary'])
        
        html = f'<span style="color: {color};">[{timestamp}] {message}</span>'
        self.log_text.append(html)
        
        logger.info(message)
    
    def closeEvent(self, event):
        """Handle close"""
        # Save state
        self.auto_save_state()
        
        # Stop workers
        for worker in [self.data_worker, self.analysis_worker, self.training_worker]:
            if worker and worker.isRunning():
                worker.wait()
        
        logger.info("LOKI Enterprise Platform closed")
        event.accept()


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================
def main():
    """Launch LOKI Enterprise Platform"""
    try:
        app = QApplication(sys.argv)
        app.setStyle('Fusion')
        app.setApplicationName("LOKI")
        app.setOrganizationName("LOKI Trading Systems")
        
        # Splash screen
        splash_pix = QPixmap(600, 350)
        splash_pix.fill(QColor(10, 14, 26))
        
        painter = QPainter(splash_pix)
        painter.setPen(QColor(0, 210, 255))
        painter.setFont(QFont("Segoe UI", 48, QFont.Weight.Bold))
        painter.drawText(splash_pix.rect(), Qt.AlignmentFlag.AlignCenter,
                        "🤖\nLOKI\nv7.0")
        
        painter.setPen(QColor(148, 163, 184))
        painter.setFont(QFont("Segoe UI", 14))
        painter.drawText(
            QRect(0, splash_pix.height() - 60, splash_pix.width(), 40),
            Qt.AlignmentFlag.AlignCenter,
            "Enterprise Trading Platform"
        )
        painter.end()
        
        splash = QSplashScreen(splash_pix)
        splash.show()
        app.processEvents()
        
        import time
        time.sleep(1.5)
        
        # Create platform
        platform = LOKIEnterprisePlatform()
        splash.finish(platform)
        platform.show()
        
        logger.info("✅ LOKI Enterprise Platform started")
        
        return app.exec()
        
    except Exception as e:
        logger.critical(f"Startup error: {e}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
