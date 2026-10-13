"""
Value at Risk (VaR) Surface Modeling
Real-time portfolio-wide VaR and Expected Shortfall calculations
"""
import asyncio
import logging
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import deque

try:
    from scipy import stats
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    logging.warning("scipy not available - VaR calculations will use normal distribution approximation")


@dataclass
class VaRResult:
    """VaR calculation result."""
    var_95: float  # 95% confidence VaR
    var_99: float  # 99% confidence VaR
    expected_shortfall: float  # Expected shortfall (ES)
    portfolio_value: float
    timestamp: datetime = field(default_factory=datetime.now)


class VaRModel:
    """
    Value at Risk model for portfolio risk assessment.
    Calculates VaR and Expected Shortfall in real-time.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.var_config = config.get('risk_topology', {})
        
        # Configuration
        self.enabled = self.var_config.get('var_enabled', True)
        self.confidence_levels = [0.95, 0.99]
        self.lookback_days = self.var_config.get('var_lookback_days', 30)
        self.update_interval_minutes = self.var_config.get('var_update_interval', 5)
        
        # Historical returns data
        self.returns_history: Dict[str, deque] = {}
        self.last_prices: Dict[str, float] = {}
        self.portfolio_returns: deque = deque(maxlen=1000)
        
        # Current VaR results
        self.current_var: Optional[VaRResult] = None
        
        # Correlation matrix
        self.correlation_matrix: Optional[np.ndarray] = None
        
        self.logger = logging.getLogger(__name__)
        self.logger.info("VaR Model initialized")
    
    async def initialize(self):
        """Initialize the VaR model."""
        self.logger = logging.getLogger(__name__)
        self.logger.info("VaR Model initialized")
    
    async def update_returns(self, symbol: str, price: float):
        """Update returns history for a symbol."""
        if not np.isfinite(price) or price <= 0:
            raise ValueError("price must be a finite positive number")
        if symbol not in self.returns_history:
            self.returns_history[symbol] = deque(maxlen=1000)
        previous_price = self.last_prices.get(symbol)
        if previous_price is not None:
            self.returns_history[symbol].append((price - previous_price) / previous_price)
        self.last_prices[symbol] = float(price)
    
    async def calculate_var(self, portfolio_weights: Dict[str, float],
                          portfolio_value: float) -> VaRResult:
        """
        Calculate VaR using historical simulation method.
        """
        if not self.enabled:
            return self._get_empty_var(portfolio_value)
        
        # Get returns for all symbols in portfolio
        returns_data = {}
        for symbol in portfolio_weights.keys():
            if symbol in self.returns_history and len(self.returns_history[symbol]) > 1:
                returns_data[symbol] = np.asarray(self.returns_history[symbol], dtype=float)
        
        if not returns_data:
            return self._get_empty_var(portfolio_value)
        
        # Create returns DataFrame
        df = pd.DataFrame(returns_data)
        
        # Fill missing values
        df = df.fillna(0)
        
        # Calculate portfolio returns
        portfolio_returns = df.dot(pd.Series(portfolio_weights))
        
        # Store portfolio returns
        for ret in portfolio_returns:
            self.portfolio_returns.append(ret)
        
        # Calculate VaR using historical simulation
        if len(self.portfolio_returns) < 100:
            return self._get_empty_var(portfolio_value)
        
        returns_array = np.array(list(self.portfolio_returns))
        
        # Sort returns
        sorted_returns = np.sort(returns_array)
        
        # Calculate VaR at different confidence levels
        var_95 = np.percentile(sorted_returns, 5) * portfolio_value
        var_99 = np.percentile(sorted_returns, 1) * portfolio_value
        
        # Calculate Expected Shortfall (average of worst losses)
        var_99_index = int(len(sorted_returns) * 0.01)
        worst_returns = sorted_returns[:var_99_index]
        expected_shortfall = np.mean(worst_returns) * portfolio_value if len(worst_returns) > 0 else 0
        
        # Update correlation matrix
        self.correlation_matrix = df.corr().values
        
        result = VaRResult(
            var_95=abs(var_95),
            var_99=abs(var_99),
            expected_shortfall=abs(expected_shortfall),
            portfolio_value=portfolio_value
        )
        
        self.current_var = result
        
        return result
    
    def _get_empty_var(self, portfolio_value: float) -> VaRResult:
        """Get empty VaR result when insufficient data."""
        return VaRResult(
            var_95=0.0,
            var_99=0.0,
            expected_shortfall=0.0,
            portfolio_value=portfolio_value
        )
    
    async def calculate_parametric_var(self, portfolio_weights: Dict[str, float],
                                     portfolio_value: float) -> VaRResult:
        """
        Calculate VaR using parametric method (variance-covariance).
        """
        if not self.enabled or self.correlation_matrix is None:
            return self._get_empty_var(portfolio_value)
        
        # Get standard deviations
        std_devs = []
        for symbol in portfolio_weights.keys():
            if symbol in self.returns_history and len(self.returns_history[symbol]) > 1:
                returns = np.asarray(self.returns_history[symbol], dtype=float)
                std_devs.append(np.std(returns))
            else:
                std_devs.append(0.0)
        
        # Calculate portfolio variance
        weights_array = np.array(list(portfolio_weights.values()))
        std_dev_array = np.array(std_devs)
        
        portfolio_variance = np.dot(
            weights_array.T,
            np.dot(self.correlation_matrix * np.outer(std_dev_array, std_dev_array), weights_array)
        )
        
        portfolio_std = np.sqrt(portfolio_variance)
        
        # Calculate VaR using normal distribution
        if SCIPY_AVAILABLE:
            var_95 = portfolio_value * stats.norm.ppf(0.05) * portfolio_std
            var_99 = portfolio_value * stats.norm.ppf(0.01) * portfolio_std
            
            # Expected Shortfall for normal distribution
            expected_shortfall = portfolio_value * portfolio_std * stats.norm.pdf(stats.norm.ppf(0.01)) / 0.01
        else:
            # Use simple approximation without scipy
            # For normal distribution, 95% VaR ≈ 1.645 * std, 99% VaR ≈ 2.326 * std
            var_95 = portfolio_value * 1.645 * portfolio_std
            var_99 = portfolio_value * 2.326 * portfolio_std
            # ES approximation for 99% confidence
            expected_shortfall = portfolio_value * 2.665 * portfolio_std
        
        return VaRResult(
            var_95=abs(var_95),
            var_99=abs(var_99),
            expected_shortfall=abs(expected_shortfall),
            portfolio_value=portfolio_value
        )
    
    async def get_risk_budget(self) -> Dict[str, Any]:
        """Get current risk budget."""
        if not self.current_var:
            return {
                'var_95': 0.0,
                'var_99': 0.0,
                'expected_shortfall': 0.0,
                'var_percent': 0.0
            }
        
        var_percent = self.current_var.var_99 / self.current_var.portfolio_value if self.current_var.portfolio_value > 0 else 0
        
        return {
            'var_95': self.current_var.var_95,
            'var_99': self.current_var.var_99,
            'expected_shortfall': self.current_var.expected_shortfall,
            'var_percent': var_percent
        }
    
    async def shutdown(self):
        """Shutdown the VaR model."""
        self.logger.info("VaR Model shutdown complete")
