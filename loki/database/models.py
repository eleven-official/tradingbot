"""
Loki Trading Platform - Database Models
Production-grade SQLAlchemy models with TimescaleDB support for time-series data
"""
from datetime import datetime
from typing import Optional
from decimal import Decimal

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime,
    ForeignKey, Index, Enum as SQLEnum, Text, DECIMAL, JSON
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum

Base = declarative_base()

# Enums
class OrderSide(enum.Enum):
    BUY = "buy"
    SELL = "sell"

class OrderType(enum.Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"

class OrderStatus(enum.Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"

class StrategyStatus(enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"

# User Management
class User(Base):
    """User account model"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255))
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = Column(DateTime)
    
    # Relationships
    portfolios = relationship("Portfolio", back_populates="user")
    api_keys = relationship("APIKey", back_populates="user")
    audit_logs = relationship("AuditLog", back_populates="user")

class APIKey(Base):
    """API key management"""
    __tablename__ = "api_keys"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    key_name = Column(String(100), nullable=False)
    key_hash = Column(String(255), nullable=False, unique=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used = Column(DateTime)
    expires_at = Column(DateTime)
    permissions = Column(JSON)  # Store permissions as JSON
    
    # Relationships
    user = relationship("User", back_populates="api_keys")

# Portfolio & Account
class Portfolio(Base):
    """User portfolio"""
    __tablename__ = "portfolios"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(100), nullable=False)
    initial_capital = Column(DECIMAL(20, 2), nullable=False)
    current_cash = Column(DECIMAL(20, 2), nullable=False)
    total_value = Column(DECIMAL(20, 2), nullable=False)
    is_live = Column(Boolean, default=False)  # Live vs Paper trading
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="portfolios")
    positions = relationship("Position", back_populates="portfolio")
    orders = relationship("Order", back_populates="portfolio")
    strategies = relationship("Strategy", back_populates="portfolio")

class Position(Base):
    """Open trading position"""
    __tablename__ = "positions"
    
    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id"), nullable=False)
    strategy_id = Column(Integer, ForeignKey("strategies.id"))
    symbol = Column(String(20), nullable=False, index=True)
    quantity = Column(DECIMAL(20, 8), nullable=False)
    entry_price = Column(DECIMAL(20, 8), nullable=False)
    current_price = Column(DECIMAL(20, 8), nullable=False)
    unrealized_pnl = Column(DECIMAL(20, 2), nullable=False)
    stop_loss = Column(DECIMAL(20, 8))
    take_profit = Column(DECIMAL(20, 8))
    opened_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    portfolio = relationship("Portfolio", back_populates="positions")
    strategy = relationship("Strategy", back_populates="positions")
    
    __table_args__ = (
        Index('idx_portfolio_symbol', 'portfolio_id', 'symbol'),
    )

class Order(Base):
    """Trading order (historical and pending)"""
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id"), nullable=False)
    strategy_id = Column(Integer, ForeignKey("strategies.id"))
    order_id_broker = Column(String(100), unique=True, index=True)  # Broker's order ID
    symbol = Column(String(20), nullable=False, index=True)
    side = Column(SQLEnum(OrderSide), nullable=False)
    order_type = Column(SQLEnum(OrderType), nullable=False)
    status = Column(SQLEnum(OrderStatus), nullable=False, index=True)
    quantity = Column(DECIMAL(20, 8), nullable=False)
    filled_quantity = Column(DECIMAL(20, 8), default=0)
    price = Column(DECIMAL(20, 8))  # Limit price
    filled_price = Column(DECIMAL(20, 8))  # Average fill price
    commission = Column(DECIMAL(20, 2), default=0)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    submitted_at = Column(DateTime)
    filled_at = Column(DateTime)
    metadata = Column(JSON)  # Additional order metadata
    
    # Relationships
    portfolio = relationship("Portfolio", back_populates="orders")
    strategy = relationship("Strategy", back_populates="orders")
    
    __table_args__ = (
        Index('idx_portfolio_status', 'portfolio_id', 'status'),
        Index('idx_created_at', 'created_at'),
    )

# Strategy Management
class Strategy(Base):
    """Trading strategy configuration"""
    __tablename__ = "strategies"
    
    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id"), nullable=False)
    name = Column(String(100), nullable=False)
    strategy_type = Column(String(50), nullable=False)  # QuantumMomentum, NeuralNetwork, etc.
    status = Column(SQLEnum(StrategyStatus), default=StrategyStatus.STOPPED)
    risk_per_trade = Column(Float, default=0.01)
    max_positions = Column(Integer, default=5)
    symbols = Column(JSON)  # List of trading symbols
    parameters = Column(JSON)  # Strategy-specific parameters
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at = Column(DateTime)
    stopped_at = Column(DateTime)
    
    # Performance metrics (cached)
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    total_pnl = Column(DECIMAL(20, 2), default=0)
    
    # Relationships
    portfolio = relationship("Portfolio", back_populates="strategies")
    positions = relationship("Position", back_populates="strategy")
    orders = relationship("Order", back_populates="strategy")
    performance = relationship("StrategyPerformance", back_populates="strategy")

# Time-series data (use TimescaleDB hypertables)
class MarketData(Base):
    """Market data time-series (TimescaleDB hypertable)"""
    __tablename__ = "market_data"
    
    time = Column(DateTime, primary_key=True, index=True)
    symbol = Column(String(20), primary_key=True, index=True)
    open = Column(DECIMAL(20, 8), nullable=False)
    high = Column(DECIMAL(20, 8), nullable=False)
    low = Column(DECIMAL(20, 8), nullable=False)
    close = Column(DECIMAL(20, 8), nullable=False)
    volume = Column(DECIMAL(30, 8), nullable=False)
    
    __table_args__ = (
        Index('idx_symbol_time', 'symbol', 'time'),
    )

class PortfolioSnapshot(Base):
    """Portfolio value snapshots (TimescaleDB hypertable)"""
    __tablename__ = "portfolio_snapshots"
    
    time = Column(DateTime, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id"), primary_key=True, index=True)
    total_value = Column(DECIMAL(20, 2), nullable=False)
    cash_balance = Column(DECIMAL(20, 2), nullable=False)
    positions_value = Column(DECIMAL(20, 2), nullable=False)
    daily_pnl = Column(DECIMAL(20, 2))
    total_pnl = Column(DECIMAL(20, 2))
    positions_count = Column(Integer)
    
    __table_args__ = (
        Index('idx_portfolio_time', 'portfolio_id', 'time'),
    )

class StrategyPerformance(Base):
    """Strategy performance metrics (TimescaleDB hypertable)"""
    __tablename__ = "strategy_performance"
    
    time = Column(DateTime, primary_key=True, index=True)
    strategy_id = Column(Integer, ForeignKey("strategies.id"), primary_key=True, index=True)
    pnl = Column(DECIMAL(20, 2), nullable=False)
    win_rate = Column(Float)
    sharpe_ratio = Column(Float)
    max_drawdown = Column(Float)
    trades_count = Column(Integer)
    
    # Relationships
    strategy = relationship("Strategy", back_populates="performance")
    
    __table_args__ = (
        Index('idx_strategy_time', 'strategy_id', 'time'),
    )

# Audit & Compliance
class AuditLog(Base):
    """Audit trail for compliance"""
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    action = Column(String(100), nullable=False, index=True)
    resource_type = Column(String(50))  # order, strategy, portfolio, etc.
    resource_id = Column(Integer)
    details = Column(JSON)
    ip_address = Column(String(45))
    user_agent = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Relationships
    user = relationship("User", back_populates="audit_logs")
    
    __table_args__ = (
        Index('idx_user_action', 'user_id', 'action'),
        Index('idx_created_at', 'created_at'),
    )

class SystemMetric(Base):
    """System performance metrics (TimescaleDB hypertable)"""
    __tablename__ = "system_metrics"
    
    time = Column(DateTime, primary_key=True, index=True)
    metric_name = Column(String(100), primary_key=True, index=True)
    metric_value = Column(Float, nullable=False)
    labels = Column(JSON)  # Additional metric labels
    
    __table_args__ = (
        Index('idx_metric_time', 'metric_name', 'time'),
    )

# Broker Credentials (encrypted)
class BrokerCredential(Base):
    """Encrypted broker API credentials"""
    __tablename__ = "broker_credentials"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    broker_name = Column(String(50), nullable=False)  # alpaca, ib, td_ameritrade, etc.
    encrypted_api_key = Column(Text, nullable=False)
    encrypted_api_secret = Column(Text, nullable=False)
    encrypted_additional_data = Column(Text)  # Account number, etc.
    is_active = Column(Boolean, default=True)
    is_paper = Column(Boolean, default=True)  # Paper vs Live
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_user_broker', 'user_id', 'broker_name'),
    )
