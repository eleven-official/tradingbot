"""
Loki Trading Platform - Advanced Risk Management
Enterprise-grade risk analytics: VaR, CVaR, stress testing, and portfolio optimization
"""
import numpy as np
import pandas as pd
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from scipy import stats
from scipy.optimize import minimize
import logging

logger = logging.getLogger(__name__)


@dataclass
class RiskMetrics:
    """Risk metrics container"""
    var_95: float  # Value at Risk (95% confidence)
    var_99: float  # Value at Risk (99% confidence)
    cvar_95: float  # Conditional VaR (Expected Shortfall)
    cvar_99: float  # Conditional VaR (99% confidence)
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    max_drawdown_duration: int  # days
    volatility: float
    beta: Optional[float] = None
    alpha: Optional[float] = None
    tracking_error: Optional[float] = None
    information_ratio: Optional[float] = None


@dataclass
class StressTestResult:
    """Stress test scenario result"""
    scenario_name: str
    portfolio_loss: float
    portfolio_loss_percent: float
    affected_positions: List[Dict]
    timestamp: datetime


@dataclass
class PortfolioOptimization:
    """Portfolio optimization result"""
    optimal_weights: Dict[str, float]
    expected_return: float
    expected_volatility: float
    sharpe_ratio: float
    efficient_frontier: pd.DataFrame


class AdvancedRiskManager:
    """
    Enterprise-grade risk management system
    
    Features:
    - Value at Risk (VaR) - Historical, Parametric, Monte Carlo
    - Conditional Value at Risk (CVaR/ES)
    - Stress Testing
    - Portfolio Optimization (Mean-Variance, Kelly Criterion)
    - Risk Budgeting
    - Correlation Analysis
    """
    
    def __init__(self, confidence_level: float = 0.95):
        self.confidence_level = confidence_level
        self.risk_free_rate = 0.04  # 4% annual risk-free rate
        
    def calculate_var(
        self,
        returns: pd.Series,
        confidence_level: float = 0.95,
        method: str = "historical"
    ) -> float:
        """
        Calculate Value at Risk
        
        Args:
            returns: Historical returns series
            confidence_level: Confidence level (0.95 for 95%)
            method: 'historical', 'parametric', or 'monte_carlo'
        
        Returns:
            VaR value (negative indicates loss)
        """
        if method == "historical":
            return self._historical_var(returns, confidence_level)
        elif method == "parametric":
            return self._parametric_var(returns, confidence_level)
        elif method == "monte_carlo":
            return self._monte_carlo_var(returns, confidence_level)
        else:
            raise ValueError(f"Unknown VaR method: {method}")
    
    def _historical_var(self, returns: pd.Series, confidence_level: float) -> float:
        """Historical VaR calculation"""
        return np.percentile(returns, (1 - confidence_level) * 100)
    
    def _parametric_var(self, returns: pd.Series, confidence_level: float) -> float:
        """Parametric (Variance-Covariance) VaR"""
        mean = returns.mean()
        std = returns.std()
        z_score = stats.norm.ppf(1 - confidence_level)
        return mean + z_score * std
    
    def _monte_carlo_var(
        self,
        returns: pd.Series,
        confidence_level: float,
        num_simulations: int = 10000
    ) -> float:
        """Monte Carlo VaR simulation"""
        mean = returns.mean()
        std = returns.std()
        simulated_returns = np.random.normal(mean, std, num_simulations)
        return np.percentile(simulated_returns, (1 - confidence_level) * 100)
    
    def calculate_cvar(
        self,
        returns: pd.Series,
        confidence_level: float = 0.95
    ) -> float:
        """
        Calculate Conditional Value at Risk (Expected Shortfall)
        Average loss beyond the VaR threshold
        """
        var = self.calculate_var(returns, confidence_level, method="historical")
        # Take average of all returns worse than VaR
        tail_losses = returns[returns <= var]
        if len(tail_losses) > 0:
            return tail_losses.mean()
        return var
    
    def calculate_comprehensive_metrics(
        self,
        returns: pd.Series,
        benchmark_returns: Optional[pd.Series] = None,
        portfolio_value: float = 100000
    ) -> RiskMetrics:
        """
        Calculate comprehensive risk metrics
        
        Args:
            returns: Portfolio returns series
            benchmark_returns: Optional benchmark returns for alpha/beta
            portfolio_value: Current portfolio value
        
        Returns:
            RiskMetrics object with all metrics
        """
        # VaR calculations
        var_95 = abs(self.calculate_var(returns, 0.95)) * portfolio_value
        var_99 = abs(self.calculate_var(returns, 0.99)) * portfolio_value
        
        # CVaR calculations
        cvar_95 = abs(self.calculate_cvar(returns, 0.95)) * portfolio_value
        cvar_99 = abs(self.calculate_cvar(returns, 0.99)) * portfolio_value
        
        # Sharpe Ratio
        excess_returns = returns - (self.risk_free_rate / 252)  # Daily risk-free rate
        sharpe = np.sqrt(252) * excess_returns.mean() / returns.std() if returns.std() > 0 else 0
        
        # Sortino Ratio (only downside deviation)
        downside_returns = returns[returns < 0]
        downside_std = downside_returns.std() if len(downside_returns) > 0 else returns.std()
        sortino = np.sqrt(252) * excess_returns.mean() / downside_std if downside_std > 0 else 0
        
        # Maximum Drawdown
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        max_dd = drawdown.min()
        
        # Max Drawdown Duration
        drawdown_periods = (drawdown < 0).astype(int)
        if drawdown_periods.sum() > 0:
            dd_durations = drawdown_periods.groupby(
                (drawdown_periods != drawdown_periods.shift()).cumsum()
            ).sum()
            max_dd_duration = dd_durations.max()
        else:
            max_dd_duration = 0
        
        # Volatility (annualized)
        volatility = returns.std() * np.sqrt(252)
        
        # Beta and Alpha (if benchmark provided)
        beta = None
        alpha = None
        tracking_error = None
        information_ratio = None
        
        if benchmark_returns is not None:
            # Align indices
            aligned_returns = returns.align(benchmark_returns, join='inner')
            port_ret = aligned_returns[0]
            bench_ret = aligned_returns[1]
            
            if len(port_ret) > 0:
                # Beta
                covariance = np.cov(port_ret, bench_ret)[0][1]
                benchmark_variance = bench_ret.var()
                beta = covariance / benchmark_variance if benchmark_variance > 0 else 1.0
                
                # Alpha (annualized)
                alpha = (port_ret.mean() - beta * bench_ret.mean()) * 252
                
                # Tracking Error
                active_returns = port_ret - bench_ret
                tracking_error = active_returns.std() * np.sqrt(252)
                
                # Information Ratio
                information_ratio = (active_returns.mean() * 252) / tracking_error if tracking_error > 0 else 0
        
        return RiskMetrics(
            var_95=var_95,
            var_99=var_99,
            cvar_95=cvar_95,
            cvar_99=cvar_99,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            max_drawdown=max_dd,
            max_drawdown_duration=max_dd_duration,
            volatility=volatility,
            beta=beta,
            alpha=alpha,
            tracking_error=tracking_error,
            information_ratio=information_ratio
        )
    
    def stress_test(
        self,
        portfolio: Dict[str, Dict],
        scenarios: Optional[List[Dict]] = None
    ) -> List[StressTestResult]:
        """
        Perform stress testing on portfolio
        
        Args:
            portfolio: Dict of {symbol: {'quantity': X, 'price': Y}}
            scenarios: List of stress scenarios
        
        Returns:
            List of StressTestResult objects
        """
        if scenarios is None:
            scenarios = self._default_stress_scenarios()
        
        results = []
        
        for scenario in scenarios:
            scenario_name = scenario['name']
            shocks = scenario['shocks']  # Dict of {symbol: price_change_percent}
            
            total_loss = 0
            affected_positions = []
            
            for symbol, position in portfolio.items():
                quantity = position['quantity']
                current_price = position['price']
                
                # Apply shock
                shock_percent = shocks.get(symbol, shocks.get('market', 0))
                new_price = current_price * (1 + shock_percent)
                position_loss = quantity * (new_price - current_price)
                
                total_loss += position_loss
                
                if position_loss < 0:
                    affected_positions.append({
                        'symbol': symbol,
                        'loss': position_loss,
                        'loss_percent': shock_percent * 100
                    })
            
            # Calculate portfolio value
            portfolio_value = sum(p['quantity'] * p['price'] for p in portfolio.values())
            loss_percent = (total_loss / portfolio_value * 100) if portfolio_value > 0 else 0
            
            results.append(StressTestResult(
                scenario_name=scenario_name,
                portfolio_loss=total_loss,
                portfolio_loss_percent=loss_percent,
                affected_positions=affected_positions,
                timestamp=datetime.now()
            ))
        
        return results
    
    def _default_stress_scenarios(self) -> List[Dict]:
        """Default stress test scenarios"""
        return [
            {
                'name': '2008 Financial Crisis',
                'shocks': {'market': -0.35}  # 35% market crash
            },
            {
                'name': '2020 COVID Crash',
                'shocks': {'market': -0.30}  # 30% crash
            },
            {
                'name': 'Flash Crash',
                'shocks': {'market': -0.20}  # 20% flash crash
            },
            {
                'name': 'Interest Rate Shock',
                'shocks': {'market': -0.15}  # 15% decline
            },
            {
                'name': 'Sector Rotation',
                'shocks': {'market': -0.10}  # 10% decline
            }
        ]
    
    def optimize_portfolio(
        self,
        expected_returns: pd.Series,
        covariance_matrix: pd.DataFrame,
        method: str = "max_sharpe"
    ) -> PortfolioOptimization:
        """
        Portfolio optimization
        
        Args:
            expected_returns: Expected returns for each asset
            covariance_matrix: Covariance matrix of returns
            method: 'max_sharpe', 'min_variance', 'max_return'
        
        Returns:
            PortfolioOptimization object
        """
        n_assets = len(expected_returns)
        
        # Objective functions
        def portfolio_stats(weights):
            portfolio_return = np.dot(weights, expected_returns)
            portfolio_variance = np.dot(weights, np.dot(covariance_matrix, weights))
            portfolio_std = np.sqrt(portfolio_variance)
            sharpe = (portfolio_return - self.risk_free_rate) / portfolio_std
            return portfolio_return, portfolio_std, sharpe
        
        def neg_sharpe(weights):
            return -portfolio_stats(weights)[2]
        
        def portfolio_variance(weights):
            return np.dot(weights, np.dot(covariance_matrix, weights))
        
        # Constraints
        constraints = [
            {'type': 'eq', 'fun': lambda x: np.sum(x) - 1}  # weights sum to 1
        ]
        
        # Bounds (0 to 1 for each weight - no short selling)
        bounds = tuple((0, 1) for _ in range(n_assets))
        
        # Initial guess (equal weights)
        init_guess = np.array([1/n_assets] * n_assets)
        
        # Optimize
        if method == "max_sharpe":
            result = minimize(neg_sharpe, init_guess, method='SLSQP',
                            bounds=bounds, constraints=constraints)
        elif method == "min_variance":
            result = minimize(portfolio_variance, init_guess, method='SLSQP',
                            bounds=bounds, constraints=constraints)
        else:
            raise ValueError(f"Unknown optimization method: {method}")
        
        optimal_weights = dict(zip(expected_returns.index, result.x))
        port_return, port_vol, port_sharpe = portfolio_stats(result.x)
        
        # Generate efficient frontier
        target_returns = np.linspace(expected_returns.min(), expected_returns.max(), 50)
        efficient_frontier = self._calculate_efficient_frontier(
            expected_returns, covariance_matrix, target_returns
        )
        
        return PortfolioOptimization(
            optimal_weights=optimal_weights,
            expected_return=port_return,
            expected_volatility=port_vol,
            sharpe_ratio=port_sharpe,
            efficient_frontier=efficient_frontier
        )
    
    def _calculate_efficient_frontier(
        self,
        expected_returns: pd.Series,
        covariance_matrix: pd.DataFrame,
        target_returns: np.ndarray
    ) -> pd.DataFrame:
        """Calculate efficient frontier points"""
        n_assets = len(expected_returns)
        frontier_volatility = []
        
        for target_return in target_returns:
            constraints = [
                {'type': 'eq', 'fun': lambda x: np.sum(x) - 1},
                {'type': 'eq', 'fun': lambda x: np.dot(x, expected_returns) - target_return}
            ]
            
            bounds = tuple((0, 1) for _ in range(n_assets))
            init_guess = np.array([1/n_assets] * n_assets)
            
            def portfolio_variance(weights):
                return np.dot(weights, np.dot(covariance_matrix, weights))
            
            try:
                result = minimize(portfolio_variance, init_guess, method='SLSQP',
                                bounds=bounds, constraints=constraints)
                frontier_volatility.append(np.sqrt(result.fun))
            except:
                frontier_volatility.append(np.nan)
        
        return pd.DataFrame({
            'return': target_returns,
            'volatility': frontier_volatility
        })
    
    def calculate_position_limits(
        self,
        portfolio_value: float,
        risk_per_trade: float = 0.02,
        volatility: float = 0.20,
        stop_loss_percent: float = 0.05
    ) -> Dict[str, float]:
        """
        Calculate position sizing based on risk parameters
        
        Args:
            portfolio_value: Total portfolio value
            risk_per_trade: Risk per trade as decimal (0.02 = 2%)
            volatility: Asset volatility
            stop_loss_percent: Stop loss percentage
        
        Returns:
            Dict with position limits
        """
        # Kelly Criterion sizing
        win_rate = 0.60  # Assume 60% win rate
        avg_win = 0.03  # 3% average win
        avg_loss = stop_loss_percent
        
        kelly_fraction = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win
        kelly_fraction = max(0, min(kelly_fraction, 0.25))  # Cap at 25%
        
        # Fixed fractional based on stop loss
        risk_amount = portfolio_value * risk_per_trade
        position_size_stop = risk_amount / stop_loss_percent
        
        # Volatility-adjusted sizing
        vol_adjust_factor = 0.20 / max(volatility, 0.05)  # Normalize to 20% vol
        position_size_vol = portfolio_value * risk_per_trade * vol_adjust_factor
        
        return {
            'kelly_position': portfolio_value * kelly_fraction,
            'fixed_risk_position': position_size_stop,
            'volatility_adjusted_position': position_size_vol,
            'recommended_position': min(position_size_stop, position_size_vol),
            'max_position': portfolio_value * 0.25  # Never more than 25% in one position
        }


def demo_risk_analysis():
    """Demo of risk analysis capabilities"""
    # Generate sample returns
    np.random.seed(42)
    returns = pd.Series(np.random.normal(0.001, 0.02, 252))  # Daily returns for 1 year
    
    risk_manager = AdvancedRiskManager()
    
    # Calculate comprehensive metrics
    metrics = risk_manager.calculate_comprehensive_metrics(returns, portfolio_value=100000)
    
    print("=" * 60)
    print("LOKI ADVANCED RISK ANALYSIS")
    print("=" * 60)
    print(f"Value at Risk (95%):       ${metrics.var_95:,.2f}")
    print(f"Value at Risk (99%):       ${metrics.var_99:,.2f}")
    print(f"CVaR (95%):                ${metrics.cvar_95:,.2f}")
    print(f"CVaR (99%):                ${metrics.cvar_99:,.2f}")
    print(f"Sharpe Ratio:              {metrics.sharpe_ratio:.2f}")
    print(f"Sortino Ratio:             {metrics.sortino_ratio:.2f}")
    print(f"Max Drawdown:              {metrics.max_drawdown*100:.2f}%")
    print(f"Volatility (Annual):       {metrics.volatility*100:.2f}%")
    
    # Stress testing
    portfolio = {
        'AAPL': {'quantity': 100, 'price': 175.50},
        'MSFT': {'quantity': 50, 'price': 380.00},
        'GOOGL': {'quantity': 25, 'price': 140.00},
    }
    
    print("\n" + "=" * 60)
    print("STRESS TEST RESULTS")
    print("=" * 60)
    
    stress_results = risk_manager.stress_test(portfolio)
    for result in stress_results:
        print(f"\n{result.scenario_name}:")
        print(f"  Portfolio Loss: ${result.portfolio_loss:,.2f}")
        print(f"  Loss %: {result.portfolio_loss_percent:.2f}%")


if __name__ == "__main__":
    demo_risk_analysis()
