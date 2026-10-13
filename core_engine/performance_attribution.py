"""
Advanced Performance Attribution and Strategy Comparison
Implements detailed performance analysis, factor attribution, and strategy comparison
"""
import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict


class AttributionFactor(Enum):
    """Performance attribution factors."""
    SELECTION = "selection"  # Security selection effect
    TIMING = "timing"  # Market timing effect
    INTERACTION = "interaction"  # Selection-timing interaction
    ALLOCATION = "allocation"  # Asset allocation effect
    RESIDUAL = "residual"  # Unexplained residual


class TimePeriod(Enum):
    """Time periods for analysis."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


@dataclass
class AttributionReport:
    """Performance attribution report."""
    strategy_name: str
    period_start: datetime
    period_end: datetime
    total_return: float
    benchmark_return: float
    active_return: float
    attribution: Dict[str, float]
    factor_exposures: Dict[str, float]
    contributions: Dict[str, float]
    timestamp: datetime


@dataclass
class StrategyComparison:
    """Strategy comparison result."""
    strategies: List[str]
    comparison_period: Tuple[datetime, datetime]
    metrics: Dict[str, Dict[str, float]]
    rankings: Dict[str, List[str]]
    statistical_tests: Dict[str, Dict[str, any]]
    recommendations: List[str]


@dataclass
class FactorAnalysis:
    """Factor analysis results."""
    strategy_name: str
    factor_returns: Dict[str, float]
    factor_t_stats: Dict[str, float]
    factor_p_values: Dict[str, float]
    r_squared: float
    adjusted_r_squared: float
    residuals: pd.Series


class PerformanceAttributor:
    """
    Advanced performance attribution analysis.
    Decomposes returns into selection, timing, and allocation effects.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def calculate_attribution(self, strategy_returns: pd.Series,
                             benchmark_returns: pd.Series,
                             sector_weights: Optional[Dict[str, float]] = None,
                             benchmark_weights: Optional[Dict[str, float]] = None) -> AttributionReport:
        """
        Calculate performance attribution using Brinson model.
        """
        # Calculate returns
        total_return = (1 + strategy_returns).prod() - 1
        benchmark_return = (1 + benchmark_returns).prod() - 1
        active_return = total_return - benchmark_return
        
        # Attribution components
        attribution = {}
        
        if sector_weights and benchmark_weights:
            # Allocation effect
            allocation = sum(
                (sector_weights[sector] - benchmark_weights.get(sector, 0)) * 
                benchmark_returns.mean()
                for sector in sector_weights
            )
            attribution['allocation'] = allocation
            
            # Selection effect
            selection = sum(
                sector_weights[sector] * (strategy_returns.mean() - benchmark_returns.mean())
                for sector in sector_weights
            )
            attribution['selection'] = selection
            
            # Interaction effect
            interaction = sum(
                (sector_weights[sector] - benchmark_weights.get(sector, 0)) *
                (strategy_returns.mean() - benchmark_returns.mean())
                for sector in sector_weights
            )
            attribution['interaction'] = interaction
        else:
            # Simple decomposition
            attribution['selection'] = active_return * 0.6
            attribution['timing'] = active_return * 0.3
            attribution['residual'] = active_return * 0.1
        
        # Factor exposures (simplified)
        factor_exposures = self._calculate_factor_exposures(strategy_returns, benchmark_returns)
        
        # Contributions
        contributions = {
            'market_risk': factor_exposures.get('beta', 0) * benchmark_return,
            'alpha': active_return - attribution.get('selection', 0) - attribution.get('timing', 0)
        }
        
        return AttributionReport(
            strategy_name="Strategy",
            period_start=strategy_returns.index[0],
            period_end=strategy_returns.index[-1],
            total_return=total_return,
            benchmark_return=benchmark_return,
            active_return=active_return,
            attribution=attribution,
            factor_exposures=factor_exposures,
            contributions=contributions,
            timestamp=datetime.now()
        )
    
    def _calculate_factor_exposures(self, strategy_returns: pd.Series,
                                   benchmark_returns: pd.Series) -> Dict[str, float]:
        """Calculate factor exposures."""
        exposures = {}
        
        # Market beta
        if len(strategy_returns) > 1 and len(benchmark_returns) > 1:
            covariance = np.cov(strategy_returns, benchmark_returns)[0, 1]
            benchmark_variance = benchmark_returns.var()
            exposures['beta'] = covariance / benchmark_variance if benchmark_variance > 0 else 1.0
        
        # Alpha (Jensen's alpha)
        exposures['alpha'] = strategy_returns.mean() - exposures.get('beta', 1.0) * benchmark_returns.mean()
        
        # Volatility exposure
        exposures['volatility'] = strategy_returns.std() / benchmark_returns.std() if benchmark_returns.std() > 0 else 1.0
        
        return exposures
    
    def calculate_rolling_attribution(self, strategy_returns: pd.Series,
                                    benchmark_returns: pd.Series,
                                    window: int = 20) -> pd.DataFrame:
        """Calculate rolling attribution over time."""
        results = []
        
        for i in range(window, len(strategy_returns)):
            window_returns = strategy_returns.iloc[i-window:i]
            window_benchmark = benchmark_returns.iloc[i-window:i]
            
            attribution = self.calculate_attribution(window_returns, window_benchmark)
            
            results.append({
                'date': strategy_returns.index[i],
                'total_return': attribution.total_return,
                'active_return': attribution.active_return,
                'selection': attribution.attribution.get('selection', 0),
                'timing': attribution.attribution.get('timing', 0),
                'allocation': attribution.attribution.get('allocation', 0)
            })
        
        return pd.DataFrame(results).set_index('date')


class FactorAnalyzer:
    """
    Factor analysis using Fama-French and other factor models.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def analyze_factor_exposure(self, strategy_returns: pd.Series,
                              factor_returns: pd.DataFrame) -> FactorAnalysis:
        """
        Analyze factor exposures using multiple regression.
        """
        # Ensure alignment
        aligned_data = pd.concat([strategy_returns, factor_returns], axis=1).dropna()
        
        if len(aligned_data) < 30:
            self.logger.warning("Insufficient data for factor analysis")
            return None
        
        y = aligned_data.iloc[:, 0]
        X = aligned_data.iloc[:, 1:]
        
        # Add constant
        X = np.column_stack([np.ones(len(X)), X])
        
        # Regression
        try:
            from scipy import stats
            results = stats.linregress(X, y)
            
            # Calculate R-squared
            y_pred = results.intercept + np.sum(X[:, 1:] * results.slope, axis=1)
            ss_res = np.sum((y - y_pred) ** 2)
            ss_tot = np.sum((y - y.mean()) ** 2)
            r_squared = 1 - (ss_res / ss_tot)
            adjusted_r_squared = 1 - (1 - r_squared) * (len(y) - 1) / (len(y) - X.shape[1] - 1)
            
            # Factor returns (simplified)
            factor_returns_dict = {
                'market': results.slope[0] if len(results.slope) > 0 else 0,
                'size': results.slope[1] if len(results.slope) > 1 else 0,
                'value': results.slope[2] if len(results.slope) > 2 else 0,
                'momentum': results.slope[3] if len(results.slope) > 3 else 0
            }
            
            return FactorAnalysis(
                strategy_name="Strategy",
                factor_returns=factor_returns_dict,
                factor_t_stats={},
                factor_p_values={},
                r_squared=r_squared,
                adjusted_r_squared=adjusted_r_squared,
                residuals=y - y_pred
            )
            
        except Exception as e:
            self.logger.error(f"Factor analysis failed: {e}")
            return None


class StrategyComparator:
    """
    Comprehensive strategy comparison framework.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def compare_strategies(self, returns_dict: Dict[str, pd.Series],
                          benchmark_returns: Optional[pd.Series] = None,
                          period: Optional[Tuple[datetime, datetime]] = None) -> StrategyComparison:
        """
        Compare multiple strategies across multiple dimensions.
        """
        strategy_names = list(returns_dict.keys())
        
        # Filter by period if specified
        if period:
            start, end = period
            returns_dict = {
                name: returns[(returns.index >= start) & (returns.index <= end)]
                for name, returns in returns_dict.items()
            }
        
        # Calculate metrics for each strategy
        metrics = {}
        for name, returns in returns_dict.items():
            metrics[name] = self._calculate_comprehensive_metrics(returns, benchmark_returns)
        
        # Calculate rankings
        rankings = self._calculate_rankings(metrics)
        
        # Statistical tests
        statistical_tests = self._run_statistical_tests(returns_dict)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(metrics, rankings)
        
        return StrategyComparison(
            strategies=strategy_names,
            comparison_period=period or (returns_dict[strategy_names[0]].index[0],
                                        returns_dict[strategy_names[0]].index[-1]),
            metrics=metrics,
            rankings=rankings,
            statistical_tests=statistical_tests,
            recommendations=recommendations
        )
    
    def _calculate_comprehensive_metrics(self, returns: pd.Series,
                                        benchmark_returns: Optional[pd.Series] = None) -> Dict[str, float]:
        """Calculate comprehensive performance metrics."""
        metrics = {}
        
        # Return metrics
        metrics['total_return'] = (1 + returns).prod() - 1
        metrics['annualized_return'] = returns.mean() * 252
        metrics['volatility'] = returns.std() * np.sqrt(252)
        
        # Risk-adjusted metrics
        excess_returns = returns - 0.02/252  # Assuming 2% risk-free rate
        metrics['sharpe_ratio'] = excess_returns.mean() / excess_returns.std() * np.sqrt(252) if excess_returns.std() > 0 else 0
        
        downside_returns = returns[returns < 0]
        metrics['sortino_ratio'] = returns.mean() / downside_returns.std() * np.sqrt(252) if len(downside_returns) > 0 else 0
        
        # Drawdown metrics
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        metrics['max_drawdown'] = drawdown.min()
        metrics['avg_drawdown'] = drawdown.mean()
        metrics['drawdown_duration'] = self._calculate_max_drawdown_duration(drawdown)
        
        # Trade metrics
        metrics['win_rate'] = (returns > 0).sum() / len(returns)
        metrics['avg_win'] = returns[returns > 0].mean() if len(returns[returns > 0]) > 0 else 0
        metrics['avg_loss'] = returns[returns < 0].mean() if len(returns[returns < 0]) > 0 else 0
        metrics['profit_factor'] = abs(returns[returns > 0].sum() / returns[returns < 0].sum()) if len(returns[returns < 0]) > 0 else 0
        
        # Distribution metrics
        metrics['skewness'] = returns.skew()
        metrics['kurtosis'] = returns.kurtosis()
        metrics['var_95'] = returns.quantile(0.05)
        metrics['cvar_95'] = returns[returns <= returns.quantile(0.05)].mean()
        
        # Benchmark-relative metrics
        if benchmark_returns is not None:
            aligned_returns = pd.concat([returns, benchmark_returns], axis=1).dropna()
            if len(aligned_returns) > 0:
                metrics['alpha'] = (aligned_returns.iloc[:, 0].mean() - aligned_returns.iloc[:, 1].mean()) * 252
                metrics['beta'] = np.cov(aligned_returns.iloc[:, 0], aligned_returns.iloc[:, 1])[0, 1] / aligned_returns.iloc[:, 1].var()
                metrics['information_ratio'] = (aligned_returns.iloc[:, 0] - aligned_returns.iloc[:, 1]).mean() / (aligned_returns.iloc[:, 0] - aligned_returns.iloc[:, 1]).std() * np.sqrt(252)
                metrics['tracking_error'] = (aligned_returns.iloc[:, 0] - aligned_returns.iloc[:, 1]).std() * np.sqrt(252)
        
        return metrics
    
    def _calculate_max_drawdown_duration(self, drawdown: pd.Series) -> int:
        """Calculate maximum drawdown duration in days."""
        is_drawdown = drawdown < 0
        drawdown_periods = []
        current_period = 0
        
        for dd in is_drawdown:
            if dd:
                current_period += 1
            else:
                if current_period > 0:
                    drawdown_periods.append(current_period)
                current_period = 0
        
        if current_period > 0:
            drawdown_periods.append(current_period)
        
        return max(drawdown_periods) if drawdown_periods else 0
    
    def _calculate_rankings(self, metrics: Dict[str, Dict[str, float]]) -> Dict[str, List[str]]:
        """Calculate rankings for each metric."""
        rankings = {}
        
        # Metrics where higher is better
        higher_better = ['total_return', 'annualized_return', 'sharpe_ratio', 
                        'sortino_ratio', 'win_rate', 'avg_win', 'profit_factor',
                        'alpha', 'information_ratio']
        
        # Metrics where lower is better
        lower_better = ['volatility', 'max_drawdown', 'avg_drawdown', 
                       'drawdown_duration', 'avg_loss', 'tracking_error',
                       'var_95', 'cvar_95']
        
        for metric in higher_better:
            if metric in metrics[list(metrics.keys())[0]]:
                sorted_strategies = sorted(metrics.keys(), 
                                          key=lambda x: metrics[x].get(metric, 0), 
                                          reverse=True)
                rankings[metric] = sorted_strategies
        
        for metric in lower_better:
            if metric in metrics[list(metrics.keys())[0]]:
                sorted_strategies = sorted(metrics.keys(), 
                                          key=lambda x: metrics[x].get(metric, float('inf')))
                rankings[metric] = sorted_strategies
        
        return rankings
    
    def _run_statistical_tests(self, returns_dict: Dict[str, pd.Series]) -> Dict[str, Dict[str, any]]:
        """Run statistical tests to compare strategies."""
        tests = {}
        
        strategy_names = list(returns_dict.keys())
        
        # Pairwise comparisons
        for i in range(len(strategy_names)):
            for j in range(i + 1, len(strategy_names)):
                name1, name2 = strategy_names[i], strategy_names[j]
                
                # Align returns
                aligned = pd.concat([returns_dict[name1], returns_dict[name2]], axis=1).dropna()
                
                if len(aligned) > 30:
                    try:
                        from scipy.stats import ttest_ind, mannwhitneyu
                        
                        # T-test
                        t_stat, t_p = ttest_ind(aligned.iloc[:, 0], aligned.iloc[:, 1])
                        
                        # Mann-Whitney U test
                        u_stat, u_p = mannwhitneyu(aligned.iloc[:, 0], aligned.iloc[:, 1])
                        
                        comparison_key = f"{name1}_vs_{name2}"
                        tests[comparison_key] = {
                            't_test': {'statistic': t_stat, 'p_value': t_p},
                            'mann_whitney': {'statistic': u_stat, 'p_value': u_p},
                            'mean_diff': aligned.iloc[:, 0].mean() - aligned.iloc[:, 1].mean()
                        }
                    except Exception as e:
                        self.logger.error(f"Statistical test failed: {e}")
        
        return tests
    
    def _generate_recommendations(self, metrics: Dict[str, Dict[str, float]],
                                rankings: Dict[str, List[str]]) -> List[str]:
        """Generate recommendations based on comparison."""
        recommendations = []
        
        # Find best overall strategy
        best_sharpe = rankings.get('sharpe_ratio', [])
        if best_sharpe:
            recommendations.append(f"Best risk-adjusted return: {best_sharpe[0]} (Sharpe: {metrics[best_sharpe[0]]['sharpe_ratio']:.2f})")
        
        # Find lowest risk
        lowest_vol = rankings.get('volatility', [])
        if lowest_vol:
            recommendations.append(f"Lowest volatility: {lowest_vol[0]} (Vol: {metrics[lowest_vol[0]]['volatility']:.2%})")
        
        # Find best risk/reward
        best_dd = rankings.get('max_drawdown', [])
        if best_dd:
            recommendations.append(f"Best drawdown control: {best_dd[0]} (Max DD: {metrics[best_dd[0]]['max_drawdown']:.2%})")
        
        # Check for statistical significance
        if any(test.get('t_test', {}).get('p_value', 1) < 0.05 for test in rankings.values() if isinstance(test, dict)):
            recommendations.append("Some strategies show statistically significant differences")
        
        return recommendations


class PerformanceVisualizer:
    """
    Performance visualization and reporting.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def generate_performance_report(self, returns_dict: Dict[str, pd.Series],
                                   benchmark_returns: Optional[pd.Series] = None) -> str:
        """Generate a comprehensive performance report."""
        comparator = StrategyComparator()
        comparison = comparator.compare_strategies(returns_dict, benchmark_returns)
        
        report = []
        report.append("=" * 80)
        report.append("STRATEGY PERFORMANCE COMPARISON REPORT")
        report.append("=" * 80)
        report.append(f"Period: {comparison.comparison_period[0]} to {comparison.comparison_period[1]}")
        report.append(f"Strategies: {', '.join(comparison.strategies)}")
        report.append("")
        
        # Performance metrics table
        report.append("PERFORMANCE METRICS")
        report.append("-" * 80)
        
        headers = ["Strategy", "Return", "Volatility", "Sharpe", "Max DD", "Win Rate"]
        report.append(f"{headers[0]:<20} {headers[1]:<12} {headers[2]:<12} {headers[3]:<10} {headers[4]:<12} {headers[5]:<10}")
        
        for strategy in comparison.strategies:
            metrics = comparison.metrics[strategy]
            report.append(
                f"{strategy:<20} "
                f"{metrics['total_return']:>10.2%} "
                f"{metrics['volatility']:>10.2%} "
                f"{metrics['sharpe_ratio']:>8.2f} "
                f"{metrics['max_drawdown']:>10.2%} "
                f"{metrics['win_rate']:>8.2%}"
            )
        
        report.append("")
        
        # Rankings
        report.append("RANKINGS")
        report.append("-" * 80)
        for metric, ranking in comparison.rankings.items():
            report.append(f"{metric}: {', '.join(ranking[:3])}")
        
        report.append("")
        
        # Recommendations
        report.append("RECOMMENDATIONS")
        report.append("-" * 80)
        for rec in comparison.recommendations:
            report.append(f"• {rec}")
        
        report.append("")
        report.append("=" * 80)
        
        return "\n".join(report)