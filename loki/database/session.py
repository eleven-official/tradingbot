"""
Database session management and connection pooling
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool
import os

# Database URL from environment or default to SQLite for development
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://loki:loki_password@localhost:5432/loki_trading"
)

# For SQLite fallback in development
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL, connect_args={"check_same_thread": False}, poolclass=NullPool
    )
else:
    # PostgreSQL/TimescaleDB production configuration
    engine = create_engine(
        DATABASE_URL,
        pool_size=20,
        max_overflow=40,
        pool_pre_ping=True,
        pool_recycle=3600,
        echo=False,  # Set to True for SQL debugging
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    """
    Dependency for getting database session
    Usage with FastAPI: db: Session = Depends(get_db)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
