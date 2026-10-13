"""
Self-Learning AI System for Trading Bot
Implements adaptive learning, parameter optimization, and strategy evolution.
"""
import logging
import json
import os
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import deque
import numpy as np
from dataclasses import dataclass, field


@dataclass
class StrategyPerformance:
    """Track performance metrics for a strategy."""
    name: str
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    recent_performance: deque = field(default_factory=lambda: deque(maxlen=20))
    last_updated: datetime = field(default_factory=datetime.now)
    
    def update(self, pnl: float, market_conditions: Dict[str, Any]):
        """Update performance with new trade result."""
        self.total_trades += 1
        self.total_pnl += pnl
        self.last_updated = datetime.now()
        
        if pnl > 0:
            self.winning_trades += 1
            self.best_trade = max(self.best_trade, pnl)
            self.avg_win = ((self.avg_win * (self.winning_trades - 1)) + pnl) / self.winning_trades
        elif pnl < 0:
            self.losing_trades += 1
            self.worst_trade = min(self.worst_trade, pnl)
            self.avg_loss = ((self.avg_loss * (self.losing_trades - 1)) + pnl) / self.losing_trades
        
        # Update derived metrics
        self._update_metrics()
        
        # Track recent performance
        self.recent_performance.append({
            'pnl': pnl,
            'timestamp': datetime.now(),
            'market_conditions': market_conditions
        })
    
    def _update_metrics(self):
        """Update derived performance metrics."""
        total = self.winning_trades + self.losing_trades
        if total > 0:
            self.win_rate = (self.winning_trades / total) * 100
        
        gross_wins = self.avg_win * self.winning_trades
        gross_losses = abs(self.avg_loss * self.losing_trades)
        if gross_losses > 0:
            self.profit_factor = gross_wins / gross_losses
    
    def get_score(self) -> float:
        """Calculate overall strategy score (0-100)."""
        score = 0.0
        
        # Win rate component (40 points)
        score += min(self.win_rate * 0.4, 40)
        
        # Profit factor component (30 points)
        if self.profit_factor > 0:
            score += min(self.profit_factor * 5, 30)
        
        # Recent performance component (20 points)
        if len(self.recent_performance) >= 5:
            recent_pnl = sum(t['pnl'] for t in list(self.recent_performance)[-5:])
            score += min(max(recent_pnl * 2, 0), 20)
        
        # Consistency component (10 points)
        if self.total_trades >= 10:
            score += 10
        
        return min(score, 100)


class AdaptiveParameterTuner:
    """Automatically tunes strategy parameters based on performance."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.parameter_history: Dict[str, List[Dict[str, Any]]] = {}
        self.optimization_interval = timedelta(hours=24)
        self.last_optimization = datetime.now()
    
    def should_optimize(self) -> bool:
        """Check if it's time to optimize parameters."""
        return datetime.now() - self.last_optimization >= self.optimization_interval
    
    def optimize_parameters(self, strategy_name: str, current_params: Dict[str, float],
                          performance: StrategyPerformance) -> Dict[str, float]:
        """Optimize strategy parameters based on performance."""
        if not self.should_optimize():
            return current_params
        
        # Performance-based parameter adjustment
        new_params = current_params.copy()
        
        # If win rate is low, reduce risk parameters
        if performance.win_rate < 40:
            new_params['risk_multiplier'] = current_params.get('risk_multiplier', 1.0) * 0.9
            new_params['stop_loss_multiplier'] = current_params.get('stop_loss_multiplier', 1.0) * 1.1
        
        # If win rate is high, increase risk parameters
        elif performance.win_rate > 60:
            new_params['risk_multiplier'] = current_params.get('risk_multiplier', 1.0) * 1.1
            new_params['stop_loss_multiplier'] = current_params.get('stop_loss_multiplier', 1.0) * 0.95
        
        # If profit factor is low, tighten entry criteria
        if performance.profit_factor < 1.5:
            new_params['entry_threshold'] = current_params.get('entry_threshold', 65) + 5
        
        # If recent performance is declining, reduce position size
        if len(performance.recent_performance) >= 5:
            recent_pnl = sum(t['pnl'] for t in list(performance.recent_performance)[-5:])
            if recent_pnl < 0:
                new_params['position_size_multiplier'] = current_params.get('position_size_multiplier', 1.0) * 0.8
        
        # Log parameter changes
        self._log_parameter_change(strategy_name, current_params, new_params, performance)
        
        # Store in history
        if strategy_name not in self.parameter_history:
            self.parameter_history[strategy_name] = []
        
        self.parameter_history[strategy_name].append({
            'timestamp': datetime.now(),
            'old_params': current_params,
            'new_params': new_params,
            'performance_score': performance.get_score()
        })
        
        self.last_optimization = datetime.now()
        return new_params
    
    def _log_parameter_change(self, strategy_name: str, old_params: Dict[str, float],
                            new_params: Dict[str, float], performance: StrategyPerformance):
        """Log parameter changes for analysis."""
        changes = []
        for key in set(old_params.keys()) | set(new_params.keys()):
            if old_params.get(key) != new_params.get(key):
                changes.append(f"{key}: {old_params.get(key):.3f} -> {new_params.get(key):.3f}")
        
        if changes:
            logging.info(f"[AdaptiveTuning] {strategy_name} parameters adjusted:")
            for change in changes:
                logging.info(f"  {change}")
            logging.info(f"  Performance score: {performance.get_score():.1f}")


class EnsembleStrategySelector:
    """Combines multiple strategies using weighted voting."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.strategy_weights: Dict[str, float] = {}
        self.ensemble_methods = ['weighted_voting', 'performance_based', 'market_condition_based']
        self.current_method = 'performance_based'
    
    def update_weights(self, performances: Dict[str, StrategyPerformance]):
        """Update strategy weights based on performance."""
        total_score = sum(perf.get_score() for perf in performances.values())
        
        if total_score > 0:
            for strategy_name, performance in performances.items():
                self.strategy_weights[strategy_name] = performance.get_score() / total_score
        else:
            # Equal weights if no performance data
            count = len(performances)
            if count > 0:
                equal_weight = 1.0 / count
                for strategy_name in performances:
                    self.strategy_weights[strategy_name] = equal_weight
    
    def select_ensemble_signal(self, signals: Dict[str, str], 
                              market_conditions: Dict[str, Any]) -> str:
        """Combine signals from multiple strategies."""
        if not signals:
            return 'HOLD'
        
        if self.current_method == 'weighted_voting':
            return self._weighted_voting(signals)
        elif self.current_method == 'performance_based':
            return self._performance_based_voting(signals)
        elif self.current_method == 'market_condition_based':
            return self._market_condition_based_voting(signals, market_conditions)
        else:
            return self._weighted_voting(signals)
    
    def _weighted_voting(self, signals: Dict[str, str]) -> str:
        """Simple weighted voting."""
        buy_weight = sum(self.strategy_weights.get(s, 0.5) for s, sig in signals.items() if sig == 'BUY')
        sell_weight = sum(self.strategy_weights.get(s, 0.5) for s, sig in signals.items() if sig == 'SELL')
        
        if buy_weight > sell_weight * 1.5:
            return 'BUY'
        elif sell_weight > buy_weight * 1.5:
            return 'SELL'
        else:
            return 'HOLD'
    
    def _performance_based_voting(self, signals: Dict[str, str]) -> str:
        """Weight voting by recent performance."""
        buy_score = 0
        sell_score = 0
        
        for strategy, signal in signals.items():
            weight = self.strategy_weights.get(strategy, 0.5)
            if signal == 'BUY':
                buy_score += weight
            elif signal == 'SELL':
                sell_score += weight
        
        if buy_score > sell_score * 1.3:
            return 'BUY'
        elif sell_score > buy_score * 1.3:
            return 'SELL'
        else:
            return 'HOLD'
    
    def _market_condition_based_voting(self, signals: Dict[str, str],
                                      market_conditions: Dict[str, Any]) -> str:
        """Adjust voting based on market conditions."""
        # In trending markets, give more weight to trend-following strategies
        # In ranging markets, give more weight to mean-reversion strategies
        market_regime = market_conditions.get('regime', 'UNKNOWN')
        
        if market_regime == 'TRENDING':
            # Prefer trend strategies
            trend_strategies = ['EMA_Cross_RSI', 'Supertrend_MACD', 'Momentum_VWAP_RSI']
            for strategy in trend_strategies:
                if strategy in self.strategy_weights:
                    self.strategy_weights[strategy] *= 1.2
        
        elif market_regime == 'RANGE':
            # Prefer mean-reversion strategies
            range_strategies = ['VWAP_Reversion', 'RSI_Divergence']
            for strategy in range_strategies:
                if strategy in self.strategy_weights:
                    self.strategy_weights[strategy] *= 1.2
        
        # Normalize weights
        total = sum(self.strategy_weights.values())
        if total > 0:
            for strategy in self.strategy_weights:
                self.strategy_weights[strategy] /= total
        
        return self._weighted_voting(signals)


class SelfLearningSystem:
    """Main self-learning system that coordinates all AI components."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.strategy_performances: Dict[str, StrategyPerformance] = {}
        self.parameter_tuner = AdaptiveParameterTuner(config)
        self.ensemble_selector = EnsembleStrategySelector(config)
        self.learning_enabled = config.get('self_learning', {}).get('enabled', True)
        self.state_file = 'state/self_learning_state.json'
        
        # Load previous learning state
        self._load_state()
    
    def record_trade(self, strategy_name: str, pnl: float, 
                    market_conditions: Dict[str, Any]):
        """Record a trade result for learning."""
        if not self.learning_enabled:
            return
        
        if strategy_name not in self.strategy_performances:
            self.strategy_performances[strategy_name] = StrategyPerformance(strategy_name)
        
        self.strategy_performances[strategy_name].update(pnl, market_conditions)
        
        # Trigger adaptive tuning if needed
        self._check_and_adapt(strategy_name)
        
        # Save state periodically
        self._save_state()
    
    def _check_and_adapt(self, strategy_name: str):
        """Check if adaptation is needed and perform it."""
        performance = self.strategy_performances[strategy_name]
        
        # Only adapt after sufficient trades
        if performance.total_trades >= 10:
            # Update ensemble weights
            self.ensemble_selector.update_weights(self.strategy_performances)
            
            # Check parameter optimization
            if self.parameter_tuner.should_optimize():
                current_params = self.config.get('strategy_params', {}).get(strategy_name, {})
                new_params = self.parameter_tuner.optimize_parameters(
                    strategy_name, current_params, performance
                )
                
                # Update config with new parameters
                if 'strategy_params' not in self.config:
                    self.config['strategy_params'] = {}
                self.config['strategy_params'][strategy_name] = new_params
    
    def get_strategy_ranking(self) -> List[Tuple[str, float]]:
        """Get strategies ranked by performance score."""
        rankings = [(name, perf.get_score()) for name, perf in self.strategy_performances.items()]
        return sorted(rankings, key=lambda x: x[1], reverse=True)
    
    def get_best_strategy(self, market_conditions: Dict[str, Any]) -> str:
        """Get the best strategy for current conditions."""
        if not self.strategy_performances:
            return 'Gemini_Default'  # Default strategy
        
        # Get top performing strategies
        rankings = self.get_strategy_ranking()
        
        # Consider market conditions
        regime = market_conditions.get('regime', 'UNKNOWN')
        
        # Filter strategies appropriate for current regime
        appropriate_strategies = []
        for strategy_name, score in rankings:
            if self._is_strategy_appropriate(strategy_name, regime):
                appropriate_strategies.append((strategy_name, score))
        
        if appropriate_strategies:
            return appropriate_strategies[0][0]
        else:
            return rankings[0][0] if rankings else 'Gemini_Default'
    
    def _is_strategy_appropriate(self, strategy_name: str, regime: str) -> bool:
        """Check if strategy is appropriate for current market regime."""
        # Trend-following strategies
        trend_strategies = ['EMA_Cross_RSI', 'Supertrend_MACD', 'Momentum_VWAP_RSI']
        # Mean-reversion strategies
        mean_reversion_strategies = ['VWAP_Reversion', 'RSI_Divergence']
        # Breakout strategies
        breakout_strategies = ['Breakout_Prev_Day_HL', 'Opening_Range_Breakout', 'BB_Squeeze_Breakout']
        
        if regime == 'TRENDING':
            return strategy_name in trend_strategies + breakout_strategies
        elif regime == 'RANGE':
            return strategy_name in mean_reversion_strategies
        else:
            return True  # All strategies appropriate for unclear regime
    
    def get_ensemble_signal(self, signals: Dict[str, str], 
                          market_conditions: Dict[str, Any]) -> str:
        """Get ensemble signal from multiple strategies."""
        if not self.learning_enabled:
            # Return simple majority if learning disabled
            buy_count = sum(1 for s in signals.values() if s == 'BUY')
            sell_count = sum(1 for s in signals.values() if s == 'SELL')
            
            if buy_count > sell_count:
                return 'BUY'
            elif sell_count > buy_count:
                return 'SELL'
            else:
                return 'HOLD'
        
        return self.ensemble_selector.select_ensemble_signal(signals, market_conditions)
    
    def get_learning_summary(self) -> Dict[str, Any]:
        """Get summary of learning progress."""
        return {
            'learning_enabled': self.learning_enabled,
            'strategies_tracked': len(self.strategy_performances),
            'strategy_rankings': self.get_strategy_ranking(),
            'ensemble_weights': self.ensemble_selector.strategy_weights,
            'parameter_tuning_active': self.parameter_tuner.should_optimize(),
            'total_trades_recorded': sum(p.total_trades for p in self.strategy_performances.values())
        }
    
    def _load_state(self):
        """Load previous learning state from disk."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                
                # Restore strategy performances
                for name, perf_data in state.get('strategy_performances', {}).items():
                    perf = StrategyPerformance(name)
                    perf.__dict__.update(perf_data)
                    # Convert deque back
                    perf.recent_performance = deque(perf_data.get('recent_performance', []), maxlen=20)
                    self.strategy_performances[name] = perf
                
                # Restore ensemble weights
                self.ensemble_selector.strategy_weights = state.get('ensemble_weights', {})
                
                logging.info(f"Loaded learning state with {len(self.strategy_performances)} strategies")
            except Exception as e:
                logging.warning(f"Could not load learning state: {e}")
    
    def _save_state(self):
        """Save current learning state to disk."""
        try:
            state = {
                'strategy_performances': {},
                'ensemble_weights': self.ensemble_selector.strategy_weights,
                'last_updated': datetime.now().isoformat()
            }
            
            # Convert strategy performances to serializable format
            for name, perf in self.strategy_performances.items():
                state['strategy_performances'][name] = {
                    'name': perf.name,
                    'total_trades': perf.total_trades,
                    'winning_trades': perf.winning_trades,
                    'losing_trades': perf.losing_trades,
                    'total_pnl': perf.total_pnl,
                    'best_trade': perf.best_trade,
                    'worst_trade': perf.worst_trade,
                    'avg_win': perf.avg_win,
                    'avg_loss': perf.avg_loss,
                    'win_rate': perf.win_rate,
                    'profit_factor': perf.profit_factor,
                    'recent_performance': [
                        {
                            'pnl': r['pnl'],
                            'timestamp': r['timestamp'].isoformat() if isinstance(r['timestamp'], datetime) else r['timestamp'],
                            'market_conditions': r['market_conditions']
                        }
                        for r in perf.recent_performance
                    ],
                    'last_updated': perf.last_updated.isoformat() if isinstance(perf.last_updated, datetime) else perf.last_updated
                }
            
            os.makedirs('state', exist_ok=True)
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
            
        except Exception as e:
            logging.warning(f"Could not save learning state: {e}")
    
    def reset_learning(self):
        """Reset all learning state."""
        self.strategy_performances.clear()
        self.ensemble_selector.strategy_weights.clear()
        self.parameter_tuner.parameter_history.clear()
        
        if os.path.exists(self.state_file):
            os.remove(self.state_file)
        
        logging.info("Learning state reset")