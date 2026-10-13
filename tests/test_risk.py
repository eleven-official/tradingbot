"""
Tests for risk management module
Validates VaR, CVaR, stress testing, and portfolio optimization
"""
import pytest
import numpy as np
import pandas as pd
from loki.risk.advanced_risk import AdvancedRiskManager, RiskMetrics


@pytest.fixture
def sample_returns():
    """Generate sample returns data"""
    np.random.seed(42)
    return pd.Series(np.random.normal(0.001, 0.02, 252))


@pytest.fixture
def risk_manager():
    """Create risk manager instance"""
    return AdvancedRiskManager(confidence_level=0.95)


class TestVaRCalculations:
    """Test Value at Risk calculations"""
    
    def test_historical_var(self, risk_manager, sample_returns):
        """Test historical VaR calculation"""
        var = risk_manager.calculate_var(sample_returns, 0.95, method="historical")
        assert var < 0  # VaR should be negative (loss)
        assert isinstance(var, float)
    
    def test_parametric_var(self, risk_manager, sample_returns):
        """Test parametric VaR calculation"""
        var = risk_manager.calculate_var(sample_returns, 0.95, method="parametric")
        assert var < 0
        assert isinstance(var, float)
    
    def test_monte_carlo_var(self, risk_manager, sample_returns):
        """Test Monte Carlo VaR calculation"""
        var = risk_manager.calculate_var(sample_returns, 0.95, method="monte_carlo")
        assert var < 0
        assert isinstance(var, float)
    
    def test_var_confidence_levels(self, risk_manager, sample_returns):
        """Test VaR at different confidence levels"""
        var_95 = abs(risk_manager.calculate_var(sample_returns, 0.95))
        var_99 = abs(risk_manager.calculate_var(sample_returns, 0.99))
        assert var_99 > var_95  # Higher confidence = larger VaR


class TestCVaR:
    """Test Conditional Value at Risk (Expected Shortfall)"""
    
    def test_cvar_calculation(self, risk_manager, sample_returns):
        """Test CVaR calculation"""
        cvar = risk_manager.calculate_cvar(sample_returns, 0.95)
        var = risk_manager.calculate_var(sample_returns, 0.95, method="historical")
        assert cvar <= var  # CVaR should be worse than VaR
    
    def test_cvar_exceeds_var(self, risk_manager, sample_returns):
        """Test that CVaR captures tail risk"""
        cvar_95 = abs(risk_manager.calculate_cvar(sample_returns, 0.95))
        cvar_99 = abs(risk_manager.calculate_cvar(sample_returns, 0.99))
        assert cvar_99 >= cvar_95


class TestComprehensiveMetrics:
    """Test comprehensive risk metrics calculation"""
    
    def test_metrics_structure(self, risk_manager, sample_returns):
        """Test risk metrics structure"""
        metrics = risk_manager.calculate_comprehensive_metrics(
            sample_returns,
            portfolio_value=100000
        )
        assert isinstance(metrics, RiskMetrics)
        assert metrics.var_95 > 0
        assert metrics.cvar_95 > 0
        assert isinstance(metrics.sharpe_ratio, float)
        assert metrics.max_drawdown < 0
    
    def test_sharpe_ratio(self, risk_manager, sample_returns):
        """Test Sharpe ratio calculation"""
        metrics = risk_manager.calculate_comprehensive_metrics(sample_returns)
        assert -5 < metrics.sharpe_ratio < 5  # Reasonable range
    
    def test_sortino_ratio(self, risk_manager, sample_returns):
        """Test Sortino ratio calculation"""
        metrics = risk_manager.calculate_comprehensive_metrics(sample_returns)
        # Sortino should be >= Sharpe (only downside volatility)
        assert metrics.sortino_ratio >= metrics.sharpe_ratio * 0.5
    
    def test_with_benchmark(self, risk_manager, sample_returns):
        """Test metrics with benchmark returns"""
        np.random.seed(43)
        # Benchmark correlated with the strategy returns so beta is meaningfully positive.
        benchmark_returns = 0.8 * sample_returns + pd.Series(np.random.normal(0, 0.008, 252))
        metrics = risk_manager.calculate_comprehensive_metrics(
            sample_returns,
            benchmark_returns=benchmark_returns
        )
        assert metrics.beta is not None
        assert metrics.alpha is not None
        assert 0 < metrics.beta < 3  # Reasonable beta range


class TestStressTesting:
    """Test portfolio stress testing"""
    
    @pytest.fixture
    def sample_portfolio(self):
        """Create sample portfolio"""
        return {
            'AAPL': {'quantity': 100, 'price': 175.50},
            'MSFT': {'quantity': 50, 'price': 380.00},
            'GOOGL': {'quantity': 25, 'price': 140.00},
        }
    
    def test_stress_test(self, risk_manager, sample_portfolio):
        """Test stress testing"""
        results = risk_manager.stress_test(sample_portfolio)
        assert len(results) > 0
        assert all(r.portfolio_loss < 0 for r in results)  # All scenarios show losses
    
    def test_custom_scenario(self, risk_manager, sample_portfolio):
        """Test custom stress scenario"""
        scenarios = [{
            'name': 'Custom Crash',
            'shocks': {'market': -0.50}  # 50% crash
        }]
        results = risk_manager.stress_test(sample_portfolio, scenarios=scenarios)
        assert len(results) == 1
        assert results[0].scenario_name == 'Custom Crash'
        assert results[0].portfolio_loss_percent < -40  # Should be close to -50%


class TestPortfolioOptimization:
    """Test portfolio optimization"""
    
    @pytest.fixture
    def sample_data(self):
        """Generate sample asset returns"""
        np.random.seed(42)
        returns = pd.DataFrame({
            'AAPL': np.random.normal(0.001, 0.02, 252),
            'MSFT': np.random.normal(0.0008, 0.018, 252),
            'GOOGL': np.random.normal(0.0012, 0.022, 252),
        })
        expected_returns = returns.mean() * 252
        cov_matrix = returns.cov() * 252
        return expected_returns, cov_matrix
    
    def test_max_sharpe_optimization(self, risk_manager, sample_data):
        """Test maximum Sharpe ratio optimization"""
        expected_returns, cov_matrix = sample_data
        result = risk_manager.optimize_portfolio(
            expected_returns,
            cov_matrix,
            method="max_sharpe"
        )
        assert result.sharpe_ratio > 0
        assert abs(sum(result.optimal_weights.values()) - 1.0) < 0.01  # Weights sum to 1
    
    def test_min_variance_optimization(self, risk_manager, sample_data):
        """Test minimum variance optimization"""
        expected_returns, cov_matrix = sample_data
        result = risk_manager.optimize_portfolio(
            expected_returns,
            cov_matrix,
            method="min_variance"
        )
        assert result.expected_volatility > 0
        assert result.expected_volatility < 0.5  # Reasonable volatility


class TestPositionSizing:
    """Test position sizing calculations"""
    
    def test_position_limits(self, risk_manager):
        """Test position limit calculations"""
        limits = risk_manager.calculate_position_limits(
            portfolio_value=100000,
            risk_per_trade=0.02,
            volatility=0.20,
            stop_loss_percent=0.05
        )
        assert 'kelly_position' in limits
        assert 'recommended_position' in limits
        assert 'max_position' in limits
        assert limits['max_position'] == 25000  # 25% of portfolio
        assert limits['recommended_position'] <= limits['max_position']


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=loki.risk", "--cov-report=html"])
