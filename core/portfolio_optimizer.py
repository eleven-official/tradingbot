"""
Portfolio Optimization Module
Integrated from Vibe-Trading project
Provides advanced portfolio optimization strategies
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional
from scipy.optimize import minimize


class PortfolioOptimizer:
    """Advanced portfolio optimization strategies."""
    
    def __init__(self):
        self.optimizers = {
            'equal_weight': self.equal_weight,
            'inverse_volatility': self.inverse_volatility,
            'risk_parity': self.risk_parity,
            'mean_variance': self.mean_variance,
            'max_diversification': self.max_diversification,
        }
    
    def equal_weight(self, n_assets: int) -> np.ndarray:
        """Equal weight allocation."""
        if isinstance(n_assets, pd.DataFrame):
            n_assets = len(n_assets.columns)
        n_assets = int(n_assets) if not isinstance(n_assets, int) else n_assets
        return np.ones(n_assets) / n_assets
    
    def inverse_volatility(self, returns: pd.DataFrame) -> np.ndarray:
        """Inverse volatility weighting."""
        vols = returns.std(ddof=1)
        inv_vol = 1.0 / vols
        weights = inv_vol / inv_vol.sum()
        return np.array(weights.values)
    
    def risk_parity(self, returns: pd.DataFrame) -> np.ndarray:
        """Equal risk contribution (risk parity) optimization."""
        cov = returns.cov().values
        n = int(cov.shape[0])
        
        if n == 0:
            return np.array([])
        
        vols = np.sqrt(np.diag(cov))
        if not np.isfinite(cov).all() or np.any(vols < 1e-12):
            return np.ones(n) / n
        
        inv_vol = 1.0 / vols
        seed = inv_vol / inv_vol.sum()
        
        def contribution_error(w: np.ndarray) -> float:
            variance = float(w @ cov @ w)
            if not np.isfinite(variance) or variance <= 1e-18:
                return 1e12
            contributions = w * (cov @ w)
            target = variance / n
            return float(np.sum((contributions - target) ** 2) / variance**2)
        
        result = minimize(
            contribution_error,
            seed,
            method="SLSQP",
            bounds=[(0.0, 1.0)] * n,
            constraints={"type": "eq", "fun": lambda w: w.sum() - 1.0},
            options={"maxiter": 200, "ftol": 1e-12},
        )
        
        if result.success and np.isfinite(result.x).all():
            return result.x / result.x.sum()
        return seed
    
    def mean_variance(self, returns: pd.DataFrame, risk_aversion: float = 1.0) -> np.ndarray:
        """Mean-variance optimization (Markowitz)."""
        n = int(len(returns.columns))
        
        mu = returns.mean().values
        cov = returns.cov().values
        
        if not np.isfinite(cov).all() or not np.isfinite(mu).all():
            return np.ones(n) / n
        
        def objective(w: np.ndarray) -> float:
            return risk_aversion * (w @ cov @ w) - w @ mu
        
        result = minimize(
            objective,
            np.ones(n) / n,
            method="SLSQP",
            bounds=[(0.0, 1.0)] * n,
            constraints={"type": "eq", "fun": lambda w: w.sum() - 1.0},
            options={"maxiter": 200, "ftol": 1e-12},
        )
        
        if result.success and np.isfinite(result.x).all():
            return result.x / result.x.sum()
        return self.equal_weight(n)
    
    def max_diversification(self, returns: pd.DataFrame) -> np.ndarray:
        """Maximum diversification ratio optimization."""
        cov = returns.cov().values
        n = int(cov.shape[0])
        
        if n == 0:
            return np.array([])
        
        vols = np.sqrt(np.diag(cov))
        if not np.isfinite(cov).all() or np.any(vols < 1e-12):
            return np.ones(n) / n
        
        def diversification_ratio(w: np.ndarray) -> float:
            """Maximize diversification ratio."""
            portfolio_vol = np.sqrt(w @ cov @ w)
            weighted_avg_vol = w @ vols
            if portfolio_vol <= 1e-12:
                return -1e12
            return -weighted_avg_vol / portfolio_vol
        
        result = minimize(
            diversification_ratio,
            np.ones(n) / n,
            method="SLSQP",
            bounds=[(0.0, 1.0)] * n,
            constraints={"type": "eq", "fun": lambda w: w.sum() - 1.0},
            options={"maxiter": 200, "ftol": 1e-12},
        )
        
        if result.success and np.isfinite(result.x).all():
            return result.x / result.x.sum()
        return self.equal_weight(n)
    
    def optimize(
        self,
        returns: pd.DataFrame,
        method: str = 'risk_parity',
        **kwargs
    ) -> np.ndarray:
        """
        Optimize portfolio weights using specified method.
        
        Args:
            returns: DataFrame of asset returns
            method: Optimization method ('equal_weight', 'inverse_volatility', 
                    'risk_parity', 'mean_variance', 'max_diversification')
            **kwargs: Additional parameters for specific methods
        
        Returns:
            Array of optimal weights
        """
        if method not in self.optimizers:
            raise ValueError(f"Unknown optimization method: {method}")
        
        if returns.empty or len(returns.columns) == 0:
            return np.array([])
        
        optimizer = self.optimizers[method]
        
        if method == 'mean_variance':
            return optimizer(returns, **kwargs)
        else:
            return optimizer(returns)
    
    def optimize_with_constraints(
        self,
        returns: pd.DataFrame,
        method: str = 'risk_parity',
        min_weight: float = 0.0,
        max_weight: float = 1.0,
        max_turnover: Optional[float] = None,
        current_weights: Optional[np.ndarray] = None,
        **kwargs
    ) -> np.ndarray:
        """
        Optimize with additional constraints.
        
        Args:
            returns: DataFrame of asset returns
            method: Optimization method
            min_weight: Minimum weight per asset
            max_weight: Maximum weight per asset
            max_turnover: Maximum turnover (change in weights)
            current_weights: Current weights for turnover constraint
            **kwargs: Additional parameters
        
        Returns:
            Array of optimal weights
        """
        n = int(len(returns.columns))
        
        if method == 'risk_parity':
            cov = returns.cov().values
            vols = np.sqrt(np.diag(cov))
            inv_vol = 1.0 / vols
            seed = inv_vol / inv_vol.sum()
        else:
            seed = np.ones(n) / n
        
        bounds = [(min_weight, max_weight)] * n
        
        constraints = [{"type": "eq", "fun": lambda w: w.sum() - 1.0}]
        
        if max_turnover is not None and current_weights is not None:
            constraints.append({
                "type": "ineq",
                "fun": lambda w: max_turnover - np.sum(np.abs(w - current_weights))
            })
        
        if method == 'risk_parity':
            cov = returns.cov().values
            
            def contribution_error(w: np.ndarray) -> float:
                variance = float(w @ cov @ w)
                if not np.isfinite(variance) or variance <= 1e-18:
                    return 1e12
                contributions = w * (cov @ w)
                target = variance / n
                return float(np.sum((contributions - target) ** 2) / variance**2)
            
            objective = contribution_error
        elif method == 'mean_variance':
            mu = returns.mean().values
            cov = returns.cov().values
            risk_aversion = kwargs.get('risk_aversion', 1.0)
            
            def objective(w: np.ndarray) -> float:
                return risk_aversion * (w @ cov @ w) - w @ mu
        else:
            def objective(w: np.ndarray) -> float:
                return 0.0  # Simple equal weight or inverse vol
        
        result = minimize(
            objective,
            seed,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"maxiter": 200, "ftol": 1e-12},
        )
        
        if result.success and np.isfinite(result.x).all():
            return result.x / result.x.sum()
        return seed
