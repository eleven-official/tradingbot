"""
Machine Learning Strategy Selector
Uses ML to automatically select the best trading strategy based on market conditions
"""
import logging
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from collections import defaultdict
import json
from datetime import datetime


class MarketCondition(Enum):
    """Market condition types."""
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    VOLATILE = "volatile"
    QUIET = "quiet"
    BREAKOUT = "breakout"


@dataclass
class StrategyPerformance:
    """Performance data for a strategy."""
    strategy_name: str
    total_trades: int
    win_rate: float
    profit_factor: float
    average_return: float
    sharpe_ratio: float
    max_drawdown: float
    last_trades: List[float]
    market_conditions: List[str]
    fitness_score: float


class MLStrategySelector:
    """
    Machine Learning-based strategy selector that automatically chooses
    the best trading strategy based on current market conditions and
    historical performance.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.ml_config = config.get('ml_strategy_selector', {})
        
        # Configuration
        self.enabled = self.ml_config.get('enabled', True)
        self.learning_rate = self.ml_config.get('learning_rate', 0.1)
        self.retrain_interval_hours = self.ml_config.get('retrain_interval_hours', 24)
        self.min_samples = self.ml_config.get('min_samples', 10)
        
        # Strategy performance database
        self.strategy_performance: Dict[str, StrategyPerformance] = {}
        
        # Market condition model
        self.market_condition_model = {}
        
        # Strategy weights for different conditions
        self.condition_strategy_weights: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        
        # Learning state
        self.last_retrain_time: Optional[datetime] = None
        self.total_selections = 0
        self.selection_accuracy = 0.0
        
        logging.info("ML Strategy Selector initialized")
    
    def analyze_market_condition(self, df: pd.DataFrame) -> MarketCondition:
        """
        Analyze current market condition using technical indicators.
        """
        try:
            if len(df) < 20:
                return MarketCondition.QUIET
            
            # Calculate indicators
            df = df.copy()
            df['sma_20'] = df['close'].rolling(window=20).mean()
            df['sma_50'] = df['close'].rolling(window=50).mean()
            df['std_20'] = df['close'].rolling(window=20).std()
            df['rsi'] = self._calculate_rsi(df['close'], period=14)
            
            current_price = df['close'].iloc[-1]
            sma_20 = df['sma_20'].iloc[-1]
            sma_50 = df['sma_50'].iloc[-1]
            std_20 = df['std_20'].iloc[-1]
            rsi = df['rsi'].iloc[-1]
            
            # Determine market condition
            volatility = std_20 / current_price
            
            if volatility > 0.03:  # High volatility
                return MarketCondition.VOLATILE
            elif volatility < 0.01:  # Low volatility
                return MarketCondition.QUIET
            
            # Trend analysis
            if current_price > sma_20 > sma_50 and rsi > 50:
                return MarketCondition.TRENDING_UP
            elif current_price < sma_20 < sma_50 and rsi < 50:
                return MarketCondition.TRENDING_DOWN
            elif abs(current_price - sma_20) / current_price < 0.01:
                return MarketCondition.RANGING
            else:
                return MarketCondition.BREAKOUT
                
        except Exception as e:
            logging.error(f"Market condition analysis error: {e}")
            return MarketCondition.QUIET
    
    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> float:
        """Calculate RSI indicator."""
        try:
            delta = prices.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            return rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50.0
        except:
            return 50.0
    
    def select_strategy(self, df: pd.DataFrame, available_strategies: List[str]) -> str:
        """
        Select the best strategy for current market conditions using ML.
        """
        if not self.enabled or not available_strategies:
            return available_strategies[0] if available_strategies else "default"
        
        try:
            # Analyze current market condition
            current_condition = self.analyze_market_condition(df)
            
            # Get strategy weights for this condition
            condition_weights = self.condition_strategy_weights[current_condition.value]
            
            # If we have performance data, use it
            if condition_weights:
                # Select strategy with highest weight
                best_strategy = max(condition_weights.items(), key=lambda x: x[1])[0]
                
                # Only select if it's in available strategies
                if best_strategy in available_strategies:
                    self.total_selections += 1
                    logging.info(f"ML selected strategy: {best_strategy} for condition: {current_condition.value}")
                    return best_strategy
            
            # Fallback: return first available strategy
            self.total_selections += 1
            return available_strategies[0]
            
        except Exception as e:
            logging.error(f"Strategy selection error: {e}")
            return available_strategies[0] if available_strategies else "default"
    
    def record_strategy_performance(self, strategy_name: str, trade_result: Dict[str, Any], 
                                  market_condition: MarketCondition):
        """
        Record performance of a strategy for learning.
        """
        try:
            pnl = trade_result.get('net', 0)
            
            # Initialize if not exists
            if strategy_name not in self.strategy_performance:
                self.strategy_performance[strategy_name] = StrategyPerformance(
                    strategy_name=strategy_name,
                    total_trades=0,
                    win_rate=0.0,
                    profit_factor=0.0,
                    average_return=0.0,
                    sharpe_ratio=0.0,
                    max_drawdown=0.0,
                    last_trades=[],
                    market_conditions=[],
                    fitness_score=0.0
                )
            
            # Update performance
            perf = self.strategy_performance[strategy_name]
            perf.total_trades += 1
            perf.last_trades.append(pnl)
            perf.market_conditions.append(market_condition.value)
            
            # Keep only last 50 trades
            if len(perf.last_trades) > 50:
                perf.last_trades.pop(0)
                perf.market_conditions.pop(0)
            
            # Recalculate metrics
            if len(perf.last_trades) >= self.min_samples:
                wins = [t for t in perf.last_trades if t > 0]
                losses = [abs(t) for t in perf.last_trades if t < 0]
                
                perf.win_rate = len(wins) / len(perf.last_trades) * 100
                perf.average_return = sum(perf.last_trades) / len(perf.last_trades)
                
                if losses:
                    perf.profit_factor = sum(wins) / sum(losses)
                else:
                    perf.profit_factor = float('inf')
                
                # Calculate fitness score
                perf.fitness_score = self._calculate_fitness_score(perf)
                
                # Update condition weights
                self._update_condition_weights(strategy_name, market_condition, perf.fitness_score)
            
            logging.debug(f"Recorded performance for {strategy_name}: P&L={pnl:.2f}, Fitness={perf.fitness_score:.2f}")
            
        except Exception as e:
            logging.error(f"Performance recording error: {e}")
    
    def _calculate_fitness_score(self, perf: StrategyPerformance) -> float:
        """Calculate fitness score for strategy selection."""
        try:
            # Weighted combination of metrics
            score = (
                perf.win_rate * 0.3 +
                min(perf.profit_factor, 5.0) * 0.2 * 20 +  # Cap at 5.0
                perf.average_return * 0.01 +
                perf.sharpe_ratio * 0.1 * 10  # Scale Sharpe
            )
            
            # Penalize high drawdown
            if perf.max_drawdown > 0:
                score -= perf.max_drawdown * 0.2
            
            return max(0, min(100, score))
            
        except Exception as e:
            logging.error(f"Fitness score calculation error: {e}")
            return 0.0
    
    def _update_condition_weights(self, strategy_name: str, condition: MarketCondition, 
                                fitness_score: float):
        """Update strategy weights for specific market condition."""
        try:
            condition_key = condition.value
            current_weight = self.condition_strategy_weights[condition_key][strategy_name]
            
            # Update using learning rate
            new_weight = current_weight + self.learning_rate * (fitness_score - current_weight)
            self.condition_strategy_weights[condition_key][strategy_name] = new_weight
            
            # Normalize weights for this condition
            total_weight = sum(self.condition_strategy_weights[condition_key].values())
            if total_weight > 0:
                for strat in self.condition_strategy_weights[condition_key]:
                    self.condition_strategy_weights[condition_key][strat] /= total_weight
            
        except Exception as e:
            logging.error(f"Weight update error: {e}")
    
    def get_strategy_rankings(self, market_condition: Optional[MarketCondition] = None) -> List[Tuple[str, float]]:
        """Get ranked strategies for specific or all market conditions."""
        if market_condition:
            condition_key = market_condition.value
            weights = self.condition_strategy_weights[condition_key]
            return sorted(weights.items(), key=lambda x: x[1], reverse=True)
        else:
            # Aggregate across all conditions
            overall_scores = defaultdict(float)
            for condition, weights in self.condition_strategy_weights.items():
                for strategy, weight in weights.items():
                    overall_scores[strategy] += weight
            
            return sorted(overall_scores.items(), key=lambda x: x[1], reverse=True)
    
    def should_retrain(self) -> bool:
        """Check if model should be retrained."""
        if not self.last_retrain_time:
            return True
        
        hours_since_retrain = (datetime.now() - self.last_retrain_time).total_seconds() / 3600
        return hours_since_retrain >= self.retrain_interval_hours
    
    def retrain_model(self):
        """Retrain the ML model with recent performance data."""
        try:
            logging.info("Retraining ML strategy selector...")
            
            # Update learning rate based on recent performance
            recent_performances = [perf.fitness_score for perf in self.strategy_performance.values()]
            if recent_performances:
                avg_fitness = sum(recent_performances) / len(recent_performances)
                # Reduce learning rate if performance is good
                if avg_fitness > 70:
                    self.learning_rate = max(0.01, self.learning_rate * 0.9)
                else:
                    self.learning_rate = min(0.5, self.learning_rate * 1.1)
            
            self.last_retrain_time = datetime.now()
            logging.info(f"ML model retrained. New learning rate: {self.learning_rate:.3f}")
            
        except Exception as e:
            logging.error(f"Model retraining error: {e}")
    
    def save_state(self, filepath: str):
        """Save ML model state to file."""
        try:
            state = {
                'strategy_performance': {
                    name: {
                        'strategy_name': perf.strategy_name,
                        'total_trades': perf.total_trades,
                        'win_rate': perf.win_rate,
                        'profit_factor': perf.profit_factor,
                        'average_return': perf.average_return,
                        'sharpe_ratio': perf.sharpe_ratio,
                        'max_drawdown': perf.max_drawdown,
                        'last_trades': perf.last_trades,
                        'market_conditions': perf.market_conditions,
                        'fitness_score': perf.fitness_score
                    }
                    for name, perf in self.strategy_performance.items()
                },
                'condition_strategy_weights': dict(self.condition_strategy_weights),
                'learning_rate': self.learning_rate,
                'last_retrain_time': self.last_retrain_time.isoformat() if self.last_retrain_time else None,
                'total_selections': self.total_selections
            }
            
            with open(filepath, 'w') as f:
                json.dump(state, f, indent=2)
            
            logging.info(f"ML model state saved to {filepath}")
            
        except Exception as e:
            logging.error(f"Failed to save ML state: {e}")
    
    def load_state(self, filepath: str):
        """Load ML model state from file."""
        try:
            with open(filepath, 'r') as f:
                state = json.load(f)
            
            # Restore strategy performance
            self.strategy_performance = {
                name: StrategyPerformance(**data)
                for name, data in state['strategy_performance'].items()
            }
            
            # Restore condition weights
            self.condition_strategy_weights = defaultdict(lambda: defaultdict(float))
            for condition, weights in state['condition_strategy_weights'].items():
                for strategy, weight in weights.items():
                    self.condition_strategy_weights[condition][strategy] = weight
            
            # Restore other state
            self.learning_rate = state['learning_rate']
            self.last_retrain_time = datetime.fromisoformat(state['last_retrain_time']) if state['last_retrain_time'] else None
            self.total_selections = state['total_selections']
            
            logging.info(f"ML model state loaded from {filepath}")
            
        except Exception as e:
            logging.error(f"Failed to load ML state: {e}")
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the ML model."""
        return {
            'enabled': self.enabled,
            'learning_rate': self.learning_rate,
            'total_selections': self.total_selections,
            'strategies_tracked': len(self.strategy_performance),
            'market_conditions_monitored': len(self.condition_strategy_weights),
            'last_retrain': self.last_retrain_time.isoformat() if self.last_retrain_time else None,
            'strategy_rankings': self.get_strategy_rankings()
        }