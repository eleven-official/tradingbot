"""
Reinforcement Learning for Strategy Optimization
Implements Q-learning and other RL techniques for strategy improvement.
"""
import logging
import numpy as np
from typing import Dict, Any, List, Tuple, Optional
from collections import defaultdict
import random


class QLearningAgent:
    """Q-Learning agent for strategy optimization."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.learning_rate = config.get('rl', {}).get('learning_rate', 0.1)
        self.discount_factor = config.get('rl', {}).get('discount_factor', 0.95)
        self.epsilon = config.get('rl', {}).get('epsilon', 0.1)  # Exploration rate
        self.epsilon_decay = config.get('rl', {}).get('epsilon_decay', 0.995)
        self.min_epsilon = config.get('rl', {}).get('min_epsilon', 0.01)
        
        # Q-table: state -> action -> value
        self.q_table: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        
        # Possible actions
        self.actions = ['BUY', 'SELL', 'HOLD', 'REDUCE_POSITION', 'INCREASE_POSITION']
        
        # State space components
        self.state_components = ['market_regime', 'volatility_level', 'trend_direction', 'time_of_day']
    
    def get_state(self, market_conditions: Dict[str, Any]) -> str:
        """Convert market conditions to state representation."""
        regime = market_conditions.get('regime', 'UNKNOWN')
        volatility = self._get_volatility_level(market_conditions)
        trend = self._get_trend_direction(market_conditions)
        timeOfDay = self._get_time_of_day()
        
        return f"{regime}_{volatility}_{trend}_{timeOfDay}"
    
    def _get_volatility_level(self, conditions: Dict[str, Any]) -> str:
        """Categorize volatility level."""
        vix = conditions.get('vix', 15)
        if vix < 15:
            return 'LOW'
        elif vix < 25:
            return 'MEDIUM'
        else:
            return 'HIGH'
    
    def _get_trend_direction(self, conditions: Dict[str, Any]) -> str:
        """Get trend direction."""
        trend = conditions.get('daily_trend', 'NEUTRAL')
        if trend in ['BULLISH', 'UP']:
            return 'UP'
        elif trend in ['BEARISH', 'DOWN']:
            return 'DOWN'
        else:
            return 'NEUTRAL'
    
    def _get_time_of_day(self) -> str:
        """Get time of day for state."""
        from datetime import datetime
        hour = datetime.now().hour
        
        if 9 <= hour < 11:
            return 'MORNING'
        elif 11 <= hour < 14:
            return 'MIDDAY'
        elif 14 <= hour < 15:
            return 'AFTERNOON'
        else:
            return 'CLOSE'
    
    def choose_action(self, state: str, training: bool = True) -> str:
        """Choose action using epsilon-greedy policy."""
        if training and random.random() < self.epsilon:
            # Explore: random action
            return random.choice(self.actions)
        else:
            # Exploit: best action from Q-table
            q_values = self.q_table[state]
            if not q_values:
                return random.choice(self.actions)
            
            return max(q_values, key=q_values.get)
    
    def update_q_value(self, state: str, action: str, reward: float, 
                       next_state: str):
        """Update Q-value using Q-learning update rule."""
        current_q = self.q_table[state][action]
        
        # Maximum Q-value for next state
        next_q_values = self.q_table[next_state]
        max_next_q = max(next_q_values.values()) if next_q_values else 0
        
        # Q-learning update
        new_q = current_q + self.learning_rate * (
            reward + self.discount_factor * max_next_q - current_q
        )
        
        self.q_table[state][action] = new_q
        
        # Decay epsilon
        self.epsilon = max(self.min_epsilon, self.epsilon * self.epsilon_decay)
    
    def get_best_action(self, state: str) -> str:
        """Get best action for a state (exploitation only)."""
        q_values = self.q_table[state]
        if not q_values:
            return 'HOLD'  # Default safe action
        
        return max(q_values, key=q_values.get)


class StrategyOptimizer:
    """Optimizes strategy parameters using Bayesian optimization concepts."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.parameter_history: Dict[str, List[Dict[str, Any]]] = {}
        self.best_parameters: Dict[str, Dict[str, float]] = {}
        self.optimization_iterations = 0
    
    def suggest_parameters(self, strategy_name: str, 
                         current_performance: float) -> Dict[str, float]:
        """Suggest new parameters based on performance."""
        # Get current best parameters
        current_params = self.best_parameters.get(strategy_name, {})
        
        if not current_params:
            # Initialize with default parameters
            current_params = self._get_default_parameters(strategy_name)
        
        # Generate new parameter suggestions
        new_params = current_params.copy()
        
        # Adjust parameters based on performance
        if current_performance < 50:  # Poor performance
            # More aggressive adjustments
            adjustment_factor = 0.2
        elif current_performance < 70:  # Moderate performance
            adjustment_factor = 0.1
        else:  # Good performance
            # Fine-tuning
            adjustment_factor = 0.05
        
        # Apply adjustments
        for param in new_params:
            if param in ['risk_multiplier', 'position_size_multiplier']:
                # Risk parameters: reduce if performance is poor
                if current_performance < 50:
                    new_params[param] *= (1 - adjustment_factor)
                else:
                    new_params[param] *= (1 + adjustment_factor * 0.5)
            
            elif param in ['stop_loss_multiplier', 'entry_threshold']:
                # Conservative parameters: increase if performance is poor
                if current_performance < 50:
                    new_params[param] *= (1 + adjustment_factor)
                else:
                    new_params[param] *= (1 - adjustment_factor * 0.5)
        
        # Ensure parameters stay within reasonable bounds
        new_params = self._clamp_parameters(new_params)
        
        # Store suggestion
        self.parameter_history.setdefault(strategy_name, []).append({
            'iteration': self.optimization_iterations,
            'params': new_params,
            'performance': current_performance,
            'timestamp': self._get_timestamp()
        })
        
        self.optimization_iterations += 1
        
        return new_params
    
    def _get_default_parameters(self, strategy_name: str) -> Dict[str, float]:
        """Get default parameters for a strategy."""
        return {
            'risk_multiplier': 1.0,
            'position_size_multiplier': 1.0,
            'stop_loss_multiplier': 1.0,
            'entry_threshold': 65.0,
            'exit_threshold': 70.0
        }
    
    def _clamp_parameters(self, params: Dict[str, float]) -> Dict[str, float]:
        """Ensure parameters stay within reasonable bounds."""
        clamped = params.copy()
        
        clamped['risk_multiplier'] = max(0.1, min(clamped.get('risk_multiplier', 1.0), 2.0))
        clamped['position_size_multiplier'] = max(0.1, min(clamped.get('position_size_multiplier', 1.0), 2.0))
        clamped['stop_loss_multiplier'] = max(0.5, min(clamped.get('stop_loss_multiplier', 1.0), 3.0))
        clamped['entry_threshold'] = max(50.0, min(clamped.get('entry_threshold', 65.0), 90.0))
        clamped['exit_threshold'] = max(50.0, min(clamped.get('exit_threshold', 70.0), 95.0))
        
        return clamped
    
    def update_best_parameters(self, strategy_name: str, params: Dict[str, float],
                             performance: float):
        """Update best parameters if performance improved."""
        current_best_perf = self.best_parameters.get(strategy_name, {}).get('performance', 0)
        
        if performance > current_best_perf:
            self.best_parameters[strategy_name] = {
                **params,
                'performance': performance,
                'timestamp': self._get_timestamp()
            }
            logging.info(f"[Optimizer] New best parameters for {strategy_name}: {performance:.1f} score")
    
    def _get_timestamp(self) -> str:
        """Get current timestamp."""
        from datetime import datetime
        return datetime.now().isoformat()


class MarketRegimeLearner:
    """Learns and adapts to different market regimes."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.regime_history: List[Dict[str, Any]] = []
        self.regime_performance: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self.current_regime = "UNKNOWN"
        self.regime_confidence = 0.0
    
    def detect_regime(self, market_data: Dict[str, Any]) -> str:
        """Detect current market regime using learned patterns."""
        # Extract features
        vix = market_data.get('vix', 15)
        trend = market_data.get('daily_trend', 'NEUTRAL')
        volatility = market_data.get('volatility', 0.02)
        volume_ratio = market_data.get('volume_ratio', 1.0)
        
        # Simple regime detection logic
        if vix > 25:
            if trend == 'BULLISH':
                regime = 'VOLATILE_BULL'
            else:
                regime = 'VOLATILE_BEAR'
        elif vix < 15:
            regime = 'LOW_VOLATILITY'
        else:
            if trend == 'NEUTRAL':
                regime = 'RANGING'
            else:
                regime = f'TRENDING_{trend}'
        
        # Update confidence based on consistency
        if self.regime_history and self.regime_history[-1]['regime'] == regime:
            self.regime_confidence = min(1.0, self.regime_confidence + 0.1)
        else:
            self.regime_confidence = max(0.3, self.regime_confidence - 0.2)
        
        self.current_regime = regime
        
        # Record regime
        self.regime_history.append({
            'regime': regime,
            'confidence': self.regime_confidence,
            'timestamp': self._get_timestamp(),
            'features': market_data
        })
        
        # Keep only recent history
        if len(self.regime_history) > 100:
            self.regime_history = self.regime_history[-100:]
        
        return regime
    
    def record_regime_performance(self, regime: str, strategy: str, pnl: float):
        """Record performance of strategies in different regimes."""
        self.regime_performance[regime][strategy] += pnl
    
    def get_best_strategy_for_regime(self, regime: str) -> Optional[str]:
        """Get best performing strategy for a regime."""
        if regime not in self.regime_performance:
            return None
        
        regime_perf = self.regime_performance[regime]
        if not regime_perf:
            return None
        
        return max(regime_perf, key=regime_perf.get)
    
    def get_regime_statistics(self) -> Dict[str, Any]:
        """Get statistics about detected regimes."""
        if not self.regime_history:
            return {}
        
        regime_counts = defaultdict(int)
        for entry in self.regime_history:
            regime_counts[entry['regime']] += 1
        
        total = len(self.regime_history)
        return {
            'current_regime': self.current_regime,
            'confidence': self.regime_confidence,
            'regime_distribution': {k: v/total for k, v in regime_counts.items()},
            'total_regimes_detected': len(regime_counts)
        }
    
    def _get_timestamp(self) -> str:
        """Get current timestamp."""
        from datetime import datetime
        return datetime.now().isoformat()


class AdvancedPortfolioOptimizer:
    """Advanced portfolio optimization using modern portfolio theory concepts."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.strategy_returns: Dict[str, List[float]] = defaultdict(list)
        self.correlation_matrix: Dict[str, Dict[str, float]] = {}
        self.optimal_weights: Dict[str, float] = {}
    
    def update_returns(self, strategy_name: str, return_value: float):
        """Update returns history for a strategy."""
        self.strategy_returns[strategy_name].append(return_value)
        
        # Keep only recent returns
        if len(self.strategy_returns[strategy_name]) > 50:
            self.strategy_returns[strategy_name] = self.strategy_returns[strategy_name][-50:]
    
    def calculate_correlations(self):
        """Calculate correlation matrix between strategies."""
        strategies = list(self.strategy_returns.keys())
        
        for i, strat1 in enumerate(strategies):
            for strat2 in strategies[i:]:
                if len(self.strategy_returns[strat1]) > 10 and len(self.strategy_returns[strat2]) > 10:
                    # Calculate correlation
                    corr = self._calculate_correlation(
                        self.strategy_returns[strat1],
                        self.strategy_returns[strat2]
                    )
                    self.correlation_matrix[strat1][strat2] = corr
                    self.correlation_matrix[strat2][strat1] = corr
    
    def _calculate_correlation(self, returns1: List[float], returns2: List[float]) -> float:
        """Calculate correlation between two return series."""
        min_len = min(len(returns1), len(returns2))
        returns1 = returns1[-min_len:]
        returns2 = returns2[-min_len:]
        
        if min_len < 2:
            return 0.0
        
        mean1 = sum(returns1) / len(returns1)
        mean2 = sum(returns2) / len(returns2)
        
        covariance = sum((x - mean1) * (y - mean2) for x, y in zip(returns1, returns2)) / len(returns1)
        
        std1 = (sum((x - mean1) ** 2 for x in returns1) / len(returns1)) ** 0.5
        std2 = (sum((y - mean2) ** 2 for y in returns2) / len(returns2)) ** 0.5
        
        if std1 == 0 or std2 == 0:
            return 0.0
        
        return covariance / (std1 * std2)
    
    def optimize_portfolio(self) -> Dict[str, float]:
        """Optimize portfolio weights using equal risk contribution."""
        strategies = list(self.strategy_returns.keys())
        
        if not strategies:
            return {}
        
        # Calculate recent volatility for each strategy
        volatilities = {}
        for strategy in strategies:
            returns = self.strategy_returns[strategy]
            if len(returns) > 10:
                mean = sum(returns) / len(returns)
                variance = sum((r - mean) ** 2 for r in returns) / len(returns)
                volatilities[strategy] = variance ** 0.5
            else:
                volatilities[strategy] = 1.0  # Default
        
        # Equal risk contribution: weight ∝ 1/volatility
        inv_vol_sum = sum(1.0 / vol for vol in volatilities.values())
        
        for strategy in strategies:
            self.optimal_weights[strategy] = (1.0 / volatilities[strategy]) / inv_vol_sum
        
        return self.optimal_weights
    
    def get_portfolio_stats(self) -> Dict[str, Any]:
        """Get portfolio statistics."""
        if not self.optimal_weights:
            return {}
        
        return {
            'num_strategies': len(self.optimal_weights),
            'weights': self.optimal_weights,
            'correlation_matrix': self.correlation_matrix,
            'avg_correlation': self._get_average_correlation()
        }
    
    def _get_average_correlation(self) -> float:
        """Calculate average correlation between strategies."""
        if not self.correlation_matrix:
            return 0.0
        
        correlations = []
        for strat1, correlations_dict in self.correlation_matrix.items():
            for strat2, corr in correlations_dict.items():
                if strat1 != strat2:
                    correlations.append(corr)
        
        return sum(correlations) / len(correlations) if correlations else 0.0