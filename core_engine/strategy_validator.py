"""
Strategy Validation Framework with Statistical Significance Testing
Implements rigorous statistical tests to validate strategy performance
"""
import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

try:
    from scipy import stats
    from scipy.stats import ttest_1samp, ttest_ind, mannwhitneyu, shapiro, normaltest
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    stats = None

__all__ = ['SCIPY_AVAILABLE']


class ValidationMetric(Enum):
    """Validation metrics."""
    SHARPE_RATIO = "sharpe_ratio"
    SORTINO_RATIO = "sortino_ratio"
    CALMAR_RATIO = "calmar_ratio"
    MAX_DRAWDOWN = "max_drawdown"
    WIN_RATE = "win_rate"
    PROFIT_FACTOR = "profit_factor"
    EXPECTED_VALUE = "expected_value"
    STANDARD_DEVIATION = "standard_deviation"
    INFORMATION_RATIO = "information_ratio"
    BETA = "beta"
    ALPHA = "alpha"


class StatisticalTest(Enum):
    """Statistical tests."""
    T_TEST = "t_test"
    WILCOXON = "wilcoxon"
    MANN_WHITNEY = "mann_whitney"
    SHAPIRO_WILK = "shapiro_wilk"
    JARQUE_BERA = "jarque_bera"
    BOOTSTRAP = "bootstrap"
    MONTE_CARLO = "monte_carlo"


@dataclass
class ValidationReport:
    """Strategy validation report."""
    strategy_name: str
    is_valid: bool
    confidence_level: float
    metrics: Dict[str, float]
    statistical_tests: Dict[str, Dict[str, any]]
    recommendations: List[str]
    timestamp: datetime
    sample_size: int
    out_of_sample_performance: Optional[Dict[str, float]] = None


@dataclass
class PerformanceStats:
    """Performance statistics."""
    returns: pd.Series
    benchmark_returns: Optional[pd.Series] = None
    
    def calculate_metrics(self) -> Dict[str, float]:
        """Calculate all performance metrics."""
        metrics = {}
        
        # Basic statistics
        metrics['total_return'] = (1 + self.returns).prod() - 1
        periods = len(self.returns)
        metrics['annualized_return'] = ((1 + self.returns).prod() ** (252 / periods) - 1) if periods else 0.0
        metrics['volatility'] = self.returns.std() * np.sqrt(252)
        
        # Risk-adjusted metrics
        metrics['sharpe_ratio'] = self._calculate_sharpe()
        metrics['sortino_ratio'] = self._calculate_sortino()
        metrics['calmar_ratio'] = self._calculate_calmar()
        
        # Drawdown metrics
        metrics['max_drawdown'] = self._calculate_max_drawdown()
        metrics['avg_drawdown'] = self._calculate_avg_drawdown()
        
        # Trade metrics
        metrics['win_rate'] = self._calculate_win_rate()
        metrics['profit_factor'] = self._calculate_profit_factor()
        metrics['expected_value'] = self.returns.mean()
        
        # Benchmark-relative metrics
        if self.benchmark_returns is not None:
            metrics['alpha'] = self._calculate_alpha()
            metrics['beta'] = self._calculate_beta()
            metrics['information_ratio'] = self._calculate_information_ratio()
            metrics['tracking_error'] = self._calculate_tracking_error()
        
        return metrics
    
    def _calculate_sharpe(self, risk_free_rate: float = 0.02) -> float:
        """Calculate Sharpe ratio."""
        excess_returns = self.returns - risk_free_rate / 252
        return excess_returns.mean() / excess_returns.std() * np.sqrt(252) if excess_returns.std() > 0 else 0
    
    def _calculate_sortino(self, risk_free_rate: float = 0.02) -> float:
        """Calculate Sortino ratio (downside deviation)."""
        excess_returns = self.returns - risk_free_rate / 252
        downside_returns = excess_returns[excess_returns < 0]
        downside_deviation = downside_returns.std() if len(downside_returns) > 0 else 0
        return (excess_returns.mean() / downside_deviation) * np.sqrt(252) if downside_deviation > 0 else 0
    
    def _calculate_calmar(self) -> float:
        """Calculate Calmar ratio (return / max drawdown)."""
        periods = len(self.returns)
        annualized_return = ((1 + self.returns).prod() ** (252 / periods) - 1) if periods else 0.0
        max_drawdown = self._calculate_max_drawdown()
        return annualized_return / abs(max_drawdown) if max_drawdown != 0 else 0
    
    def _calculate_max_drawdown(self) -> float:
        """Calculate maximum drawdown."""
        cumulative = (1 + self.returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        return drawdown.min()
    
    def _calculate_avg_drawdown(self) -> float:
        """Calculate average drawdown."""
        cumulative = (1 + self.returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        return drawdown.mean()
    
    def _calculate_win_rate(self) -> float:
        """Calculate win rate."""
        winning_trades = (self.returns > 0).sum()
        total_trades = len(self.returns)
        return winning_trades / total_trades if total_trades > 0 else 0
    
    def _calculate_profit_factor(self) -> float:
        """Calculate profit factor (gross profit / gross loss)."""
        gross_profit = self.returns[self.returns > 0].sum()
        gross_loss = abs(self.returns[self.returns < 0].sum())
        return gross_profit / gross_loss if gross_loss > 0 else 0
    
    def _calculate_alpha(self) -> float:
        """Calculate alpha (excess return over benchmark)."""
        if self.benchmark_returns is None:
            return 0
        return (self.returns.mean() - self.benchmark_returns.mean()) * 252
    
    def _calculate_beta(self) -> float:
        """Calculate beta (sensitivity to benchmark)."""
        if self.benchmark_returns is None:
            return 0
        covariance = np.cov(self.returns, self.benchmark_returns)[0, 1]
        benchmark_variance = self.benchmark_returns.var()
        return covariance / benchmark_variance if benchmark_variance > 0 else 0
    
    def _calculate_information_ratio(self) -> float:
        """Calculate information ratio (active return / tracking error)."""
        if self.benchmark_returns is None:
            return 0
        active_returns = self.returns - self.benchmark_returns
        return active_returns.mean() / active_returns.std() * np.sqrt(252) if active_returns.std() > 0 else 0
    
    def _calculate_tracking_error(self) -> float:
        """Calculate tracking error."""
        if self.benchmark_returns is None:
            return 0
        active_returns = self.returns - self.benchmark_returns
        return active_returns.std() * np.sqrt(252)


class StatisticalValidator:
    """
    Statistical significance testing for strategy validation.
    """
    
    def __init__(self, confidence_level: float = 0.95):
        self.confidence_level = confidence_level
        self.logger = logging.getLogger(__name__)
    
    def test_normality(self, returns: pd.Series) -> Dict[str, any]:
        """Test if returns are normally distributed."""
        results = {}
        
        if not SCIPY_AVAILABLE:
            self.logger.warning("scipy not available - skipping normality tests")
            return results
        
        # Shapiro-Wilk test
        try:
            shapiro_stat, shapiro_p = shapiro(returns)
            results['shapiro_wilk'] = {
                'statistic': shapiro_stat,
                'p_value': shapiro_p,
                'is_normal': shapiro_p > 0.05
            }
        except Exception as e:
            self.logger.error(f"Shapiro-Wilk test failed: {e}")
        
        # Jarque-Bera test
        try:
            jb_stat, jb_p = normaltest(returns)
            results['jarque_bera'] = {
                'statistic': jb_stat,
                'p_value': jb_p,
                'is_normal': jb_p > 0.05
            }
        except Exception as e:
            self.logger.error(f"Jarque-Bera test failed: {e}")
        
        return results
    
    def test_mean_returns(self, returns: pd.Series,
                         null_hypothesis: float = 0.0) -> Dict[str, any]:
        """Test if mean returns are significantly different from zero."""
        results = {}
        
        if not SCIPY_AVAILABLE:
            self.logger.warning("scipy not available - skipping t-test")
            return results
        
        # One-sample t-test
        try:
            t_stat, t_p = ttest_1samp(returns, null_hypothesis)
            results['t_test'] = {
                'statistic': t_stat,
                'p_value': t_p,
                'is_significant': t_p < (1 - self.confidence_level),
                'mean': returns.mean(),
                'std_error': returns.std() / np.sqrt(len(returns))
            }
        except Exception as e:
            self.logger.error(f"T-test failed: {e}")
        
        return results
    
    def test_outperformance(self, strategy_returns: pd.Series,
                          benchmark_returns: pd.Series) -> Dict[str, any]:
        """Test if strategy significantly outperforms benchmark."""
        results = {}
        
        if not SCIPY_AVAILABLE:
            self.logger.warning("scipy not available - skipping outperformance tests")
            return results
        
        # Paired t-test
        try:
            aligned = pd.concat([strategy_returns, benchmark_returns], axis=1).dropna()
            if len(aligned) < 2:
                return results
            t_stat, t_p = stats.ttest_rel(aligned.iloc[:, 0], aligned.iloc[:, 1])
            results['t_test'] = {
                'statistic': t_stat,
                'p_value': t_p,
                'is_significant': t_p < (1 - self.confidence_level),
                'strategy_mean': strategy_returns.mean(),
                'benchmark_mean': benchmark_returns.mean()
            }
        except Exception as e:
            self.logger.error(f"T-test failed: {e}")
        
        # Mann-Whitney U test (non-parametric)
        try:
            u_stat, u_p = mannwhitneyu(strategy_returns, benchmark_returns)
            results['mann_whitney'] = {
                'statistic': u_stat,
                'p_value': u_p,
                'is_significant': u_p < (1 - self.confidence_level)
            }
        except Exception as e:
            self.logger.error(f"Mann-Whitney test failed: {e}")
        
        return results
    
    def bootstrap_test(self, returns: pd.Series, 
                      n_iterations: int = 10000) -> Dict[str, any]:
        """Bootstrap test for robustness."""
        try:
            # Bootstrap mean returns
            bootstrap_means = []
            for _ in range(n_iterations):
                sample = returns.sample(n=len(returns), replace=True)
                bootstrap_means.append(sample.mean())
            
            bootstrap_means = np.array(bootstrap_means)
            
            # Calculate confidence interval
            lower_bound = np.percentile(bootstrap_means, (1 - self.confidence_level) / 2 * 100)
            upper_bound = np.percentile(bootstrap_means, (1 + self.confidence_level) / 2 * 100)
            
            return {
                'bootstrap_mean': np.mean(bootstrap_means),
                'confidence_interval': (lower_bound, upper_bound),
                'std_error': np.std(bootstrap_means),
                'is_significant': lower_bound > 0
            }
        except Exception as e:
            self.logger.error(f"Bootstrap test failed: {e}")
            return {}
    
    def monte_carlo_simulation(self, returns: pd.Series,
                              n_simulations: int = 1000,
                              n_periods: int = 252) -> Dict[str, any]:
        """Monte Carlo simulation for forward-looking performance."""
        try:
            simulations = []
            
            for _ in range(n_simulations):
                # Generate random returns based on historical distribution
                simulated_returns = np.random.choice(returns, size=n_periods, replace=True)
                cumulative_return = (1 + simulated_returns).prod() - 1
                simulations.append(cumulative_return)
            
            simulations = np.array(simulations)
            
            # Calculate statistics
            percentiles = np.percentile(simulations, [5, 25, 50, 75, 95])
            
            return {
                'mean': np.mean(simulations),
                'std': np.std(simulations),
                'min': np.min(simulations),
                'max': np.max(simulations),
                'percentiles': {
                    '5th': percentiles[0],
                    '25th': percentiles[1],
                    '50th': percentiles[2],
                    '75th': percentiles[3],
                    '95th': percentiles[4]
                },
                'probability_positive': (simulations > 0).mean()
            }
        except Exception as e:
            self.logger.error(f"Monte Carlo simulation failed: {e}")
            return {}


class StrategyValidator:
    """
    Comprehensive strategy validation framework.
    """
    
    def __init__(self, confidence_level: float = 0.95,
                 min_sample_size: int = 100):
        self.confidence_level = confidence_level
        self.min_sample_size = min_sample_size
        self.statistical_validator = StatisticalValidator(confidence_level)
        self.logger = logging.getLogger(__name__)
    
    def validate_strategy(self, strategy_name: str,
                         in_sample_returns: pd.Series,
                         out_of_sample_returns: Optional[pd.Series] = None,
                         benchmark_returns: Optional[pd.Series] = None) -> ValidationReport:
        """
        Validate a strategy with comprehensive statistical tests.
        """
        self.logger.info(f"Validating strategy: {strategy_name}")
        
        # Check sample size
        if len(in_sample_returns) < self.min_sample_size:
            self.logger.warning(f"Insufficient sample size: {len(in_sample_returns)} < {self.min_sample_size}")
        
        # Calculate in-sample metrics
        in_sample_stats = PerformanceStats(in_sample_returns, benchmark_returns)
        in_sample_metrics = in_sample_stats.calculate_metrics()
        
        # Run statistical tests
        statistical_tests = {}
        
        # Normality tests
        statistical_tests['normality'] = self.statistical_validator.test_normality(in_sample_returns)
        
        # Mean returns test
        statistical_tests['mean_returns'] = self.statistical_validator.test_mean_returns(in_sample_returns)
        
        # Bootstrap test
        statistical_tests['bootstrap'] = self.statistical_validator.bootstrap_test(in_sample_returns)
        
        # Monte Carlo simulation
        statistical_tests['monte_carlo'] = self.statistical_validator.monte_carlo_simulation(in_sample_returns)
        
        # Out-of-sample validation
        out_of_sample_metrics = None
        if out_of_sample_returns is not None and len(out_of_sample_returns) > 0:
            out_sample_stats = PerformanceStats(out_of_sample_returns, benchmark_returns)
            out_of_sample_metrics = out_sample_stats.calculate_metrics()
            
            # Test outperformance vs in-sample
            statistical_tests['out_of_sample_vs_in_sample'] = self.statistical_validator.test_outperformance(
                out_of_sample_returns, in_sample_returns
            )
        
        # Benchmark comparison
        if benchmark_returns is not None:
            statistical_tests['vs_benchmark'] = self.statistical_validator.test_outperformance(
                in_sample_returns, benchmark_returns
            )
        
        # Determine validity
        is_valid = self._determine_validity(in_sample_metrics, statistical_tests, out_of_sample_metrics)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(in_sample_metrics, statistical_tests, out_of_sample_metrics)
        
        return ValidationReport(
            strategy_name=strategy_name,
            is_valid=is_valid,
            confidence_level=self.confidence_level,
            metrics=in_sample_metrics,
            statistical_tests=statistical_tests,
            recommendations=recommendations,
            timestamp=datetime.now(),
            sample_size=len(in_sample_returns),
            out_of_sample_performance=out_of_sample_metrics
        )
    
    def _determine_validity(self, metrics: Dict[str, float],
                           tests: Dict[str, Dict[str, any]],
                           out_of_sample_metrics: Optional[Dict[str, float]]) -> bool:
        """Determine if strategy is valid based on tests."""
        valid_criteria = 0
        total_criteria = 0
        
        # Sharpe ratio > 0.5
        total_criteria += 1
        if metrics.get('sharpe_ratio', 0) > 0.5:
            valid_criteria += 1
        
        # Positive mean returns
        total_criteria += 1
        if metrics.get('expected_value', 0) > 0:
            valid_criteria += 1
        
        # Statistically significant mean returns
        total_criteria += 1
        if tests.get('mean_returns', {}).get('t_test', {}).get('is_significant', False):
            valid_criteria += 1
        
        # Win rate > 50%
        total_criteria += 1
        if metrics.get('win_rate', 0) > 0.5:
            valid_criteria += 1
        
        # Max drawdown < 20%
        total_criteria += 1
        if abs(metrics.get('max_drawdown', 1)) < 0.2:
            valid_criteria += 1
        
        # Out-of-sample consistency
        if out_of_sample_metrics:
            total_criteria += 1
            in_sample_sharpe = metrics.get('sharpe_ratio', 0)
            out_sample_sharpe = out_of_sample_metrics.get('sharpe_ratio', 0)
            if out_sample_sharpe > 0 and out_sample_sharpe >= in_sample_sharpe * 0.5:
                valid_criteria += 1
        
        # Valid if 70% of criteria met
        return valid_criteria / total_criteria >= 0.7
    
    def _generate_recommendations(self, metrics: Dict[str, float],
                                 tests: Dict[str, Dict[str, any]],
                                 out_of_sample_metrics: Optional[Dict[str, float]]) -> List[str]:
        """Generate recommendations based on validation results."""
        recommendations = []
        
        # Sharpe ratio
        sharpe = metrics.get('sharpe_ratio', 0)
        if sharpe < 0.5:
            recommendations.append("Low Sharpe ratio - consider risk-adjusted improvements")
        elif sharpe > 1.5:
            recommendations.append("Excellent Sharpe ratio - strategy shows strong risk-adjusted returns")
        
        # Drawdown
        max_dd = abs(metrics.get('max_drawdown', 0))
        if max_dd > 0.3:
            recommendations.append("High maximum drawdown - consider adding position sizing limits")
        
        # Win rate
        win_rate = metrics.get('win_rate', 0)
        if win_rate < 0.4:
            recommendations.append("Low win rate - review entry/exit criteria")
        
        # Statistical significance
        if not tests.get('mean_returns', {}).get('t_test', {}).get('is_significant', False):
            recommendations.append("Returns not statistically significant - need more data")
        
        # Out-of-sample performance
        if out_of_sample_metrics:
            in_sample_sharpe = metrics.get('sharpe_ratio', 0)
            out_sample_sharpe = out_of_sample_metrics.get('sharpe_ratio', 0)
            
            if out_sample_sharpe < in_sample_sharpe * 0.5:
                recommendations.append("Significant out-of-sample degradation - possible overfitting")
            elif out_sample_sharpe > in_sample_sharpe:
                recommendations.append("Out-of-sample performance exceeds in-sample - excellent robustness")
        
        # Normality
        if tests.get('normality', {}).get('shapiro_wilk', {}).get('is_normal', False):
            recommendations.append("Returns are normally distributed - statistical tests are reliable")
        else:
            recommendations.append("Returns are not normal - consider non-parametric methods")
        
        if not recommendations:
            recommendations.append("Strategy passes validation criteria")
        
        return recommendations
    
    def compare_strategies(self, returns_dict: Dict[str, pd.Series],
                          benchmark_returns: Optional[pd.Series] = None) -> Dict[str, ValidationReport]:
        """Compare multiple strategies."""
        reports = {}
        
        for strategy_name, returns in returns_dict.items():
            report = self.validate_strategy(
                strategy_name=strategy_name,
                in_sample_returns=returns,
                benchmark_returns=benchmark_returns
            )
            reports[strategy_name] = report
        
        return reports
