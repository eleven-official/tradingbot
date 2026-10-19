"""
LOKI v7.0 - Portfolio Optimization Engine
Modern Portfolio Theory, risk-adjusted returns, and optimal position sizing
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


@dataclass
class Asset:
    """Asset in the portfolio"""

    symbol: str
    current_price: float
    quantity: float
    value: float

    @property
    def weight(self) -> float:
        """Weight in portfolio (calculated by optimizer)"""
        return 0.0


@dataclass
class PortfolioMetrics:
    """Portfolio performance metrics"""

    total_value: float
    total_return: float
    annualized_return: float
    volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    var_95: float  # Value at Risk (95%)
    cvar_95: float  # Conditional VaR (95%)


@dataclass
class OptimalAllocation:
    """Optimal portfolio allocation"""

    timestamp: datetime
    allocations: Dict[str, float]  # symbol -> weight (0-1)
    expected_return: float
    expected_risk: float
    sharpe_ratio: float
    diversification_score: float  # 0-100%
    rebalance_required: bool
    rebalance_trades: Dict[str, float]  # symbol -> quantity to trade


@dataclass
class PositionSize:
    """Optimal position sizing for a trade"""

    symbol: str
    entry_price: float
    optimal_quantity: float
    position_value: float
    portfolio_weight: float  # % of portfolio
    risk_amount: float  # $ at risk
    stop_loss: float
    take_profit: float
    risk_reward_ratio: float


@dataclass
class CorrelationAnalysis:
    """Correlation analysis between assets"""

    timestamp: datetime
    correlation_matrix: pd.DataFrame
    highly_correlated_pairs: List[Tuple[str, str, float]]  # (symbol1, symbol2, correlation)
    diversification_opportunities: List[str]  # Symbols with low correlation
    cluster_analysis: Dict[str, List[str]]  # cluster_name -> [symbols]


class PortfolioOptimizer:
    """
    Advanced portfolio optimization using Modern Portfolio Theory

    Features:
    - Mean-variance optimization
    - Risk-adjusted position sizing
    - Correlation analysis
    - Kelly Criterion for sizing
    - Dynamic rebalancing
    """

    def __init__(self, risk_free_rate: float = 0.02):
        """
        Initialize portfolio optimizer

        Args:
            risk_free_rate: Annual risk-free rate (default 2%)
        """
        self.risk_free_rate = risk_free_rate
        self.portfolio_history: List[PortfolioMetrics] = []
        self.allocation_history: List[OptimalAllocation] = []

        logger.info(f"Portfolio Optimizer initialized (risk-free rate: {risk_free_rate:.2%})")

    def calculate_portfolio_metrics(
        self, returns: pd.Series, portfolio_value: float
    ) -> PortfolioMetrics:
        """
        Calculate comprehensive portfolio metrics

        Args:
            returns: Series of portfolio returns
            portfolio_value: Current portfolio value

        Returns:
            PortfolioMetrics with all statistics
        """
        try:
            if len(returns) < 2:
                logger.warning("Insufficient returns data")
                return self._fallback_metrics(portfolio_value)

            # Basic returns
            total_return = float(returns.sum())
            annualized_return = float((1 + returns.mean()) ** 252 - 1)  # Assuming daily returns

            # Risk metrics
            volatility = float(returns.std() * np.sqrt(252))

            # Sharpe Ratio
            excess_returns = returns.mean() - (self.risk_free_rate / 252)
            sharpe_ratio = (
                float(excess_returns / returns.std() * np.sqrt(252)) if returns.std() > 0 else 0.0
            )

            # Sortino Ratio (only downside deviation)
            downside_returns = returns[returns < 0]
            downside_std = downside_returns.std() if len(downside_returns) > 0 else returns.std()
            sortino_ratio = (
                float(excess_returns / downside_std * np.sqrt(252)) if downside_std > 0 else 0.0
            )

            # Maximum Drawdown
            cumulative = (1 + returns).cumprod()
            running_max = cumulative.expanding().max()
            drawdown = (cumulative - running_max) / running_max
            max_drawdown = float(drawdown.min())

            # Win Rate
            winning_days = (returns > 0).sum()
            win_rate = float(winning_days / len(returns)) if len(returns) > 0 else 0.0

            # Profit Factor
            gross_profit = returns[returns > 0].sum()
            gross_loss = abs(returns[returns < 0].sum())
            profit_factor = float(gross_profit / gross_loss) if gross_loss > 0 else float("inf")

            # Value at Risk (95%)
            var_95 = float(np.percentile(returns, 5) * portfolio_value)

            # Conditional VaR (95%) - average of worst 5%
            worst_returns = returns[returns <= np.percentile(returns, 5)]
            cvar_95 = (
                float(worst_returns.mean() * portfolio_value) if len(worst_returns) > 0 else var_95
            )

            metrics = PortfolioMetrics(
                total_value=portfolio_value,
                total_return=total_return,
                annualized_return=annualized_return,
                volatility=volatility,
                sharpe_ratio=sharpe_ratio,
                sortino_ratio=sortino_ratio,
                max_drawdown=max_drawdown,
                win_rate=win_rate,
                profit_factor=profit_factor,
                var_95=var_95,
                cvar_95=cvar_95,
            )

            self.portfolio_history.append(metrics)

            logger.info(
                f"Portfolio metrics: Return={annualized_return:.2%}, Sharpe={sharpe_ratio:.2f}, MaxDD={max_drawdown:.2%}"
            )

            return metrics

        except Exception as e:
            logger.error(f"Portfolio metrics calculation failed: {e}")
            return self._fallback_metrics(portfolio_value)

    def optimize_allocation(
        self,
        asset_returns: Dict[str, pd.Series],
        target_return: Optional[float] = None,
        max_weights: Optional[Dict[str, float]] = None,
    ) -> OptimalAllocation:
        """
        Find optimal asset allocation using mean-variance optimization

        Args:
            asset_returns: Dict mapping symbol to returns series
            target_return: Target return (if None, maximize Sharpe ratio)
            max_weights: Maximum weight per asset

        Returns:
            OptimalAllocation with weights and metrics
        """
        try:
            if not asset_returns:
                logger.warning("No asset returns provided")
                return self._fallback_allocation()

            # Convert to DataFrame
            returns_df = pd.DataFrame(asset_returns)

            # Calculate expected returns and covariance
            expected_returns = returns_df.mean() * 252  # Annualized
            cov_matrix = returns_df.cov() * 252  # Annualized

            # Number of assets
            n_assets = len(asset_returns)

            # Find optimal weights
            if target_return is None:
                # Maximize Sharpe ratio
                weights = self._maximize_sharpe_ratio(expected_returns, cov_matrix, max_weights)
            else:
                # Target specific return
                weights = self._target_return_optimization(
                    expected_returns, cov_matrix, target_return, max_weights
                )

            # Calculate portfolio metrics
            portfolio_return = float(np.dot(weights, expected_returns))
            portfolio_risk = float(np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights))))
            sharpe_ratio = (
                (portfolio_return - self.risk_free_rate) / portfolio_risk
                if portfolio_risk > 0
                else 0.0
            )

            # Diversification score (based on weight distribution)
            diversification_score = self._calculate_diversification_score(weights)

            # Create allocation dictionary
            allocations = {
                symbol: float(weight) for symbol, weight in zip(asset_returns.keys(), weights)
            }

            # Check if rebalancing needed (stub - would compare to current portfolio)
            rebalance_required = True
            rebalance_trades = {}  # Would calculate specific trades

            allocation = OptimalAllocation(
                timestamp=datetime.now(),
                allocations=allocations,
                expected_return=portfolio_return,
                expected_risk=portfolio_risk,
                sharpe_ratio=sharpe_ratio,
                diversification_score=diversification_score,
                rebalance_required=rebalance_required,
                rebalance_trades=rebalance_trades,
            )

            self.allocation_history.append(allocation)

            logger.info(
                f"Optimal allocation: Return={portfolio_return:.2%}, Risk={portfolio_risk:.2%}, Sharpe={sharpe_ratio:.2f}"
            )

            return allocation

        except Exception as e:
            logger.error(f"Portfolio optimization failed: {e}")
            return self._fallback_allocation()

    def calculate_position_size(
        self,
        symbol: str,
        entry_price: float,
        stop_loss: float,
        portfolio_value: float,
        win_rate: float = 0.5,
        avg_win: float = 0.02,
        avg_loss: float = 0.01,
        max_risk_per_trade: float = 0.02,
    ) -> PositionSize:
        """
        Calculate optimal position size using Kelly Criterion and risk management

        Args:
            symbol: Asset symbol
            entry_price: Entry price
            stop_loss: Stop loss price
            portfolio_value: Total portfolio value
            win_rate: Historical win rate
            avg_win: Average win (as decimal)
            avg_loss: Average loss (as decimal)
            max_risk_per_trade: Maximum risk per trade (as decimal)

        Returns:
            PositionSize with optimal sizing
        """
        try:
            # Calculate risk per share
            risk_per_share = abs(entry_price - stop_loss)

            if risk_per_share == 0:
                logger.warning("Invalid stop loss - same as entry price")
                return self._fallback_position_size(symbol, entry_price, portfolio_value)

            # Kelly Criterion
            # Kelly % = (Win% * AvgWin - Loss% * AvgLoss) / AvgLoss
            loss_rate = 1 - win_rate
            kelly_fraction = (win_rate * avg_win - loss_rate * avg_loss) / avg_loss
            kelly_fraction = max(0, min(kelly_fraction, 0.25))  # Cap at 25%

            # Conservative Kelly (half Kelly for safety)
            conservative_kelly = kelly_fraction * 0.5

            # Risk-based sizing
            max_risk_dollars = portfolio_value * max_risk_per_trade
            risk_based_shares = max_risk_dollars / risk_per_share

            # Use more conservative of the two methods
            kelly_shares = (portfolio_value * conservative_kelly) / entry_price
            optimal_shares = min(risk_based_shares, kelly_shares)

            # Round to reasonable quantity
            optimal_quantity = round(optimal_shares, 2)
            position_value = optimal_quantity * entry_price
            portfolio_weight = position_value / portfolio_value
            risk_amount = optimal_quantity * risk_per_share

            # Calculate take profit (2:1 risk/reward)
            risk_reward_ratio = 2.0
            take_profit = entry_price + (
                risk_per_share * risk_reward_ratio * (1 if entry_price > stop_loss else -1)
            )

            position = PositionSize(
                symbol=symbol,
                entry_price=entry_price,
                optimal_quantity=optimal_quantity,
                position_value=position_value,
                portfolio_weight=portfolio_weight,
                risk_amount=risk_amount,
                stop_loss=stop_loss,
                take_profit=take_profit,
                risk_reward_ratio=risk_reward_ratio,
            )

            logger.info(
                f"Position size for {symbol}: {optimal_quantity:.2f} shares "
                f"(${position_value:.2f}, {portfolio_weight:.1%} of portfolio)"
            )

            return position

        except Exception as e:
            logger.error(f"Position sizing failed: {e}")
            return self._fallback_position_size(symbol, entry_price, portfolio_value)

    def analyze_correlations(
        self, asset_returns: Dict[str, pd.Series], threshold: float = 0.7
    ) -> CorrelationAnalysis:
        """
        Analyze correlations between assets

        Args:
            asset_returns: Dict mapping symbol to returns series
            threshold: Correlation threshold for "high" correlation

        Returns:
            CorrelationAnalysis with correlation matrix and insights
        """
        try:
            if len(asset_returns) < 2:
                logger.warning("Need at least 2 assets for correlation analysis")
                return self._fallback_correlation()

            # Create returns DataFrame
            returns_df = pd.DataFrame(asset_returns)

            # Calculate correlation matrix
            corr_matrix = returns_df.corr()

            # Find highly correlated pairs
            highly_correlated = []
            symbols = list(asset_returns.keys())

            for i, sym1 in enumerate(symbols):
                for j, sym2 in enumerate(symbols):
                    if i < j:  # Avoid duplicates
                        corr = corr_matrix.loc[sym1, sym2]
                        if abs(corr) >= threshold:
                            highly_correlated.append((sym1, sym2, float(corr)))

            # Sort by absolute correlation
            highly_correlated.sort(key=lambda x: abs(x[2]), reverse=True)

            # Find diversification opportunities (low correlation)
            diversification_opps = []
            for sym in symbols:
                avg_corr = corr_matrix[sym].drop(sym).abs().mean()
                if avg_corr < 0.3:  # Low average correlation
                    diversification_opps.append(sym)

            # Simple clustering (by correlation similarity)
            clusters = self._cluster_by_correlation(corr_matrix)

            analysis = CorrelationAnalysis(
                timestamp=datetime.now(),
                correlation_matrix=corr_matrix,
                highly_correlated_pairs=highly_correlated,
                diversification_opportunities=diversification_opps,
                cluster_analysis=clusters,
            )

            logger.info(
                f"Correlation analysis: {len(highly_correlated)} high correlations, "
                f"{len(diversification_opps)} diversification opportunities"
            )

            return analysis

        except Exception as e:
            logger.error(f"Correlation analysis failed: {e}")
            return self._fallback_correlation()

    # Private helper methods

    def _maximize_sharpe_ratio(
        self,
        expected_returns: pd.Series,
        cov_matrix: pd.DataFrame,
        max_weights: Optional[Dict[str, float]],
    ) -> np.ndarray:
        """Maximize Sharpe ratio using scipy optimization"""
        from scipy.optimize import minimize

        n_assets = len(expected_returns)

        # Objective function (negative Sharpe to minimize)
        def neg_sharpe(weights):
            portfolio_return = np.dot(weights, expected_returns)
            portfolio_risk = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
            sharpe = (portfolio_return - self.risk_free_rate) / portfolio_risk
            return -sharpe

        # Constraints
        constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]  # Weights sum to 1

        # Bounds (0 to max_weight for each asset)
        bounds = []
        symbols = expected_returns.index.tolist()
        for sym in symbols:
            max_w = max_weights.get(sym, 1.0) if max_weights else 1.0
            bounds.append((0, max_w))

        # Initial guess (equal weight)
        initial_weights = np.array([1 / n_assets] * n_assets)

        # Optimize
        result = minimize(
            neg_sharpe, initial_weights, method="SLSQP", bounds=bounds, constraints=constraints
        )

        return result.x if result.success else initial_weights

    def _target_return_optimization(
        self,
        expected_returns: pd.Series,
        cov_matrix: pd.DataFrame,
        target_return: float,
        max_weights: Optional[Dict[str, float]],
    ) -> np.ndarray:
        """Minimize risk for target return"""
        from scipy.optimize import minimize

        n_assets = len(expected_returns)

        # Objective function (portfolio variance)
        def portfolio_variance(weights):
            return np.dot(weights.T, np.dot(cov_matrix, weights))

        # Constraints
        constraints = [
            {"type": "eq", "fun": lambda w: np.sum(w) - 1},  # Weights sum to 1
            {
                "type": "eq",
                "fun": lambda w: np.dot(w, expected_returns) - target_return,
            },  # Target return
        ]

        # Bounds
        bounds = []
        symbols = expected_returns.index.tolist()
        for sym in symbols:
            max_w = max_weights.get(sym, 1.0) if max_weights else 1.0
            bounds.append((0, max_w))

        # Initial guess
        initial_weights = np.array([1 / n_assets] * n_assets)

        # Optimize
        result = minimize(
            portfolio_variance,
            initial_weights,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
        )

        return result.x if result.success else initial_weights

    def _calculate_diversification_score(self, weights: np.ndarray) -> float:
        """Calculate diversification score (0-100%)"""
        # Based on entropy of weights
        # Maximum entropy = all equal weights
        # Minimum entropy = one asset has all weight

        n_assets = len(weights)

        if n_assets == 1:
            return 0.0

        # Normalized entropy
        entropy = -np.sum(weights * np.log(weights + 1e-10))
        max_entropy = np.log(n_assets)

        diversification = (entropy / max_entropy) * 100 if max_entropy > 0 else 0.0

        return float(diversification)

    def _cluster_by_correlation(self, corr_matrix: pd.DataFrame) -> Dict[str, List[str]]:
        """Simple clustering based on correlation"""
        symbols = corr_matrix.columns.tolist()
        clusters = {}
        assigned = set()

        cluster_id = 0

        for sym in symbols:
            if sym in assigned:
                continue

            # Find highly correlated symbols
            correlations = corr_matrix[sym].drop(sym)
            cluster_members = [sym]
            assigned.add(sym)

            for other_sym, corr in correlations.items():
                if other_sym not in assigned and abs(corr) > 0.6:
                    cluster_members.append(other_sym)
                    assigned.add(other_sym)

            clusters[f"Cluster_{cluster_id}"] = cluster_members
            cluster_id += 1

        return clusters

    def _fallback_metrics(self, portfolio_value: float) -> PortfolioMetrics:
        """Fallback metrics when calculation fails"""
        return PortfolioMetrics(
            total_value=portfolio_value,
            total_return=0.0,
            annualized_return=0.0,
            volatility=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            max_drawdown=0.0,
            win_rate=0.0,
            profit_factor=1.0,
            var_95=0.0,
            cvar_95=0.0,
        )

    def _fallback_allocation(self) -> OptimalAllocation:
        """Fallback allocation when optimization fails"""
        return OptimalAllocation(
            timestamp=datetime.now(),
            allocations={},
            expected_return=0.0,
            expected_risk=0.0,
            sharpe_ratio=0.0,
            diversification_score=0.0,
            rebalance_required=False,
            rebalance_trades={},
        )

    def _fallback_position_size(
        self, symbol: str, entry_price: float, portfolio_value: float
    ) -> PositionSize:
        """Fallback position sizing"""
        # Conservative 1% of portfolio
        position_value = portfolio_value * 0.01
        quantity = position_value / entry_price

        return PositionSize(
            symbol=symbol,
            entry_price=entry_price,
            optimal_quantity=quantity,
            position_value=position_value,
            portfolio_weight=0.01,
            risk_amount=position_value * 0.02,
            stop_loss=entry_price * 0.98,
            take_profit=entry_price * 1.04,
            risk_reward_ratio=2.0,
        )

    def _fallback_correlation(self) -> CorrelationAnalysis:
        """Fallback correlation analysis"""
        return CorrelationAnalysis(
            timestamp=datetime.now(),
            correlation_matrix=pd.DataFrame(),
            highly_correlated_pairs=[],
            diversification_opportunities=[],
            cluster_analysis={},
        )


def demo_portfolio_optimization():
    """Demonstration of portfolio optimization"""
    # Generate sample returns for multiple assets
    np.random.seed(42)
    dates = pd.date_range(end=datetime.now(), periods=252, freq="D")

    returns = {
        "AAPL": pd.Series(np.random.randn(252) * 0.02 + 0.001, index=dates),
        "GOOGL": pd.Series(np.random.randn(252) * 0.025 + 0.0012, index=dates),
        "MSFT": pd.Series(np.random.randn(252) * 0.018 + 0.0015, index=dates),
        "AMZN": pd.Series(np.random.randn(252) * 0.03 + 0.0008, index=dates),
        "TSLA": pd.Series(np.random.randn(252) * 0.04 + 0.0005, index=dates),
    }

    optimizer = PortfolioOptimizer(risk_free_rate=0.02)

    # Portfolio metrics
    portfolio_returns = returns["AAPL"] * 0.3 + returns["GOOGL"] * 0.3 + returns["MSFT"] * 0.4
    metrics = optimizer.calculate_portfolio_metrics(portfolio_returns, 100000)

    print(f"\n{'='*70}")
    print("PORTFOLIO METRICS")
    print(f"{'='*70}")
    print(f"Total Value: ${metrics.total_value:,.2f}")
    print(f"Annualized Return: {metrics.annualized_return:.2%}")
    print(f"Volatility: {metrics.volatility:.2%}")
    print(f"Sharpe Ratio: {metrics.sharpe_ratio:.2f}")
    print(f"Sortino Ratio: {metrics.sortino_ratio:.2f}")
    print(f"Max Drawdown: {metrics.max_drawdown:.2%}")
    print(f"Win Rate: {metrics.win_rate:.2%}")
    print(f"Profit Factor: {metrics.profit_factor:.2f}")

    # Optimal allocation
    allocation = optimizer.optimize_allocation(returns)

    print(f"\n{'='*70}")
    print("OPTIMAL ALLOCATION")
    print(f"{'='*70}")
    print(f"Expected Return: {allocation.expected_return:.2%}")
    print(f"Expected Risk: {allocation.expected_risk:.2%}")
    print(f"Sharpe Ratio: {allocation.sharpe_ratio:.2f}")
    print(f"Diversification Score: {allocation.diversification_score:.1f}%")
    print("\nAllocations:")
    for symbol, weight in allocation.allocations.items():
        print(f"  {symbol}: {weight:.1%}")

    # Position sizing
    position = optimizer.calculate_position_size(
        symbol="AAPL",
        entry_price=150.0,
        stop_loss=145.0,
        portfolio_value=100000,
        win_rate=0.6,
        avg_win=0.03,
        avg_loss=0.015,
    )

    print(f"\n{'='*70}")
    print("POSITION SIZING (AAPL)")
    print(f"{'='*70}")
    print(f"Entry Price: ${position.entry_price:.2f}")
    print(f"Optimal Quantity: {position.optimal_quantity:.2f} shares")
    print(f"Position Value: ${position.position_value:,.2f}")
    print(f"Portfolio Weight: {position.portfolio_weight:.1%}")
    print(f"Risk Amount: ${position.risk_amount:.2f}")
    print(f"Stop Loss: ${position.stop_loss:.2f}")
    print(f"Take Profit: ${position.take_profit:.2f}")
    print(f"Risk/Reward: {position.risk_reward_ratio:.1f}:1")

    # Correlation analysis
    corr_analysis = optimizer.analyze_correlations(returns)

    print(f"\n{'='*70}")
    print("CORRELATION ANALYSIS")
    print(f"{'='*70}")
    print("\nCorrelation Matrix:")
    print(corr_analysis.correlation_matrix.round(2))
    print(f"\nHighly Correlated Pairs:")
    for sym1, sym2, corr in corr_analysis.highly_correlated_pairs[:3]:
        print(f"  {sym1} - {sym2}: {corr:.2f}")
    print(f"\nDiversification Opportunities: {corr_analysis.diversification_opportunities}")


if __name__ == "__main__":
    demo_portfolio_optimization()
