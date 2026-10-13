"""
Custom exceptions for the trading bot.
Provides structured error handling for different failure scenarios.
"""
from typing import Optional, Dict, Any


class TradingBotError(Exception):
    """Base exception for all trading bot errors."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}
    
    def __str__(self):
        if self.details:
            return f"{self.message} | Details: {self.details}"
        return self.message


class AuthenticationError(TradingBotError):
    """Authentication and token management failures."""
    pass


class ConfigurationError(TradingBotError):
    """Configuration validation and loading errors."""
    pass


class DataFetchError(TradingBotError):
    """Market data fetching failures."""
    pass


class OrderExecutionError(TradingBotError):
    """Order placement, modification, or cancellation failures."""
    pass


class PositionManagementError(TradingBotError):
    """Position tracking and management errors."""
    pass


class RiskLimitError(TradingBotError):
    """Risk limit violations (daily loss, consecutive losses, etc.)."""
    pass


class StrategyError(TradingBotError):
    """Strategy signal generation and execution errors."""
    pass


class MarketConditionError(TradingBotError):
    """Market condition analysis errors."""
    pass


class NetworkError(TradingBotError):
    """Network connectivity and API timeout errors."""
    pass


class ValidationError(TradingBotError):
    """Input validation errors."""
    pass


class StateError(TradingBotError):
    """State persistence and recovery errors."""
    pass


class InstrumentError(TradingBotError):
    """Instrument lookup and validation errors."""
    pass


class LiquidityError(TradingBotError):
    """Insufficient liquidity for order execution."""
    pass


class TimingError(TradingBotError):
    """Market timing and session errors."""
    pass


def create_error_context(error: Exception, context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a standardized error context for logging and reporting.
    
    Args:
        error: The exception that occurred
        context: Additional context information
    
    Returns:
        Dictionary with error details and context
    """
    error_context = {
        'error_type': type(error).__name__,
        'error_message': str(error),
        'context': context
    }
    
    if isinstance(error, TradingBotError):
        error_context['details'] = error.details
    
    return error_context


def handle_error_with_fallback(error: Exception, fallback_value: Any, 
                               logger=None, context: Dict[str, Any] = None) -> Any:
    """
    Handle an error by logging it and returning a fallback value.
    
    Args:
        error: The exception that occurred
        fallback_value: Value to return on error
        logger: Optional logger instance
        context: Additional context information
    
    Returns:
        The fallback value
    """
    error_context = create_error_context(error, context or {})
    
    if logger:
        logger.error(f"Error occurred: {error_context}")
    
    return fallback_value