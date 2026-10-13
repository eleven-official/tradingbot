"""
Evolutionary Optimizer - Self-improving trading system.
Uses genetic algorithms and performance feedback to optimize trading parameters.
"""
import logging
import random
import json
import copy
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import statistics


class OptimizationTarget(Enum):
    """What to optimize for."""
    MAXIMIZE_PROFIT = "maximize_profit"
    MAXIMIZE_WIN_RATE = "maximize_win_rate"
    MINIMIZE_DRAWDOWN = "minimize_drawdown"
    BALANCED = "balanced"


@dataclass
class TradingParameters:
    """Set of trading parameters to optimize."""
    risk_per_trade: float = 1.0
    stop_loss_percent: float = 15.0
    take_profit_percent: float = 30.0
    max_trades_per_day: int = 5
    atr_multiplier: float = 2.0
    vix_threshold: float = 22.0
    position_size_multiplier: float = 1.0
    
    def mutate(self, mutation_rate: float = 0.1) -> 'TradingParameters':
        """Create a mutated version of these parameters."""
        mutated = copy.deepcopy(self)
        
        # Mutate each parameter with probability mutation_rate
        if random.random() < mutation_rate:
            mutated.risk_per_trade = max(0.1, min(5.0, mutated.risk_per_trade * random.uniform(0.8, 1.2)))
        
        if random.random() < mutation_rate:
            mutated.stop_loss_percent = max(5.0, min(50.0, mutated.stop_loss_percent * random.uniform(0.8, 1.2)))
        
        if random.random() < mutation_rate:
            mutated.take_profit_percent = max(10.0, min(100.0, mutated.take_profit_percent * random.uniform(0.8, 1.2)))
        
        if random.random() < mutation_rate:
            mutated.max_trades_per_day = max(1, min(10, int(mutated.max_trades_per_day * random.uniform(0.8, 1.2))))
        
        if random.random() < mutation_rate:
            mutated.atr_multiplier = max(1.0, min(5.0, mutated.atr_multiplier * random.uniform(0.8, 1.2)))
        
        if random.random() < mutation_rate:
            mutated.vix_threshold = max(15.0, min(35.0, mutated.vix_threshold * random.uniform(0.8, 1.2)))
        
        if random.random() < mutation_rate:
            mutated.position_size_multiplier = max(0.5, min(2.0, mutated.position_size_multiplier * random.uniform(0.8, 1.2)))
        
        return mutated
    
    def crossover(self, other: 'TradingParameters') -> 'TradingParameters':
        """Create offspring by combining with another parameter set."""
        child = copy.deepcopy(self)
        
        # Randomly select parameters from either parent
        if random.random() < 0.5:
            child.risk_per_trade = other.risk_per_trade
        if random.random() < 0.5:
            child.stop_loss_percent = other.stop_loss_percent
        if random.random() < 0.5:
            child.take_profit_percent = other.take_profit_percent
        if random.random() < 0.5:
            child.max_trades_per_day = other.max_trades_per_day
        if random.random() < 0.5:
            child.atr_multiplier = other.atr_multiplier
        if random.random() < 0.5:
            child.vix_threshold = other.vix_threshold
        if random.random() < 0.5:
            child.position_size_multiplier = other.position_size_multiplier
        
        return child
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'risk_per_trade': self.risk_per_trade,
            'stop_loss_percent': self.stop_loss_percent,
            'take_profit_percent': self.take_profit_percent,
            'max_trades_per_day': self.max_trades_per_day,
            'atr_multiplier': self.atr_multiplier,
            'vix_threshold': self.vix_threshold,
            'position_size_multiplier': self.position_size_multiplier
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TradingParameters':
        """Create from dictionary."""
        return cls(
            risk_per_trade=data.get('risk_per_trade', 1.0),
            stop_loss_percent=data.get('stop_loss_percent', 15.0),
            take_profit_percent=data.get('take_profit_percent', 30.0),
            max_trades_per_day=data.get('max_trades_per_day', 5),
            atr_multiplier=data.get('atr_multiplier', 2.0),
            vix_threshold=data.get('vix_threshold', 22.0),
            position_size_multiplier=data.get('position_size_multiplier', 1.0)
        )


@dataclass
class PerformanceMetrics:
    """Performance metrics for parameter evaluation."""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_profit: float = 0.0
    total_loss: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    
    def calculate_fitness(self, target: OptimizationTarget) -> float:
        """Calculate fitness score based on optimization target."""
        if target == OptimizationTarget.MAXIMIZE_PROFIT:
            return self.total_profit - (self.max_drawdown * 2)
        
        elif target == OptimizationTarget.MAXIMIZE_WIN_RATE:
            return self.win_rate * 100
        
        elif target == OptimizationTarget.MINIMIZE_DRAWDOWN:
            return -self.max_drawdown * 100
        
        elif target == OptimizationTarget.BALANCED:
            # Balanced approach: profit * win_rate / drawdown
            if self.max_drawdown == 0:
                return self.total_profit * self.win_rate
            return (self.total_profit * self.win_rate) / abs(self.max_drawdown)
        
        return 0.0


class EvolutionaryOptimizer:
    """
    Genetic algorithm-based optimizer for trading parameters.
    Evolves parameter sets over time based on performance feedback.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.evolution_config = config.get('evolutionary_optimizer', {})
        
        # Configuration
        self.enabled = self.evolution_config.get('enabled', True)
        self.population_size = self.evolution_config.get('population_size', 10)
        self.mutation_rate = self.evolution_config.get('mutation_rate', 0.1)
        self.elite_count = self.evolution_config.get('elite_count', 2)
        self.optimization_target = OptimizationTarget(
            self.evolution_config.get('optimization_target', 'balanced')
        )
        self.evolution_interval_days = self.evolution_config.get('evolution_interval_days', 7)
        
        # Population and performance tracking
        self.population: List[Tuple[TradingParameters, PerformanceMetrics]] = []
        self.current_parameters: TradingParameters = TradingParameters()
        self.generation: int = 0
        self.last_evolution_date: Optional[datetime] = None
        self.best_fitness_history: List[float] = []
        
        # Initialize population
        if self.enabled:
            self._initialize_population()
        
        logging.info("Evolutionary Optimizer initialized")
    
    def _initialize_population(self):
        """Initialize the population with random parameters."""
        self.population = []
        
        # Start with current parameters
        current_params = self._load_current_parameters()
        self.population.append((current_params, PerformanceMetrics()))
        
        # Generate random variations
        for _ in range(self.population_size - 1):
            params = TradingParameters()
            # Randomize parameters within reasonable ranges
            params.risk_per_trade = random.uniform(0.5, 2.0)
            params.stop_loss_percent = random.uniform(10.0, 25.0)
            params.take_profit_percent = random.uniform(20.0, 50.0)
            params.max_trades_per_day = random.randint(3, 8)
            params.atr_multiplier = random.uniform(1.5, 3.0)
            params.vix_threshold = random.uniform(18.0, 28.0)
            
            self.population.append((params, PerformanceMetrics()))
        
        logging.info(f"Initialized population with {len(self.population)} parameter sets")
    
    def _load_current_parameters(self) -> TradingParameters:
        """Load current parameters from config."""
        trading_flags = self.config.get('trading_flags', {})
        risk_config = self.config.get('risk_management', {})
        
        return TradingParameters(
            risk_per_trade=trading_flags.get('risk_per_trade_percent', 1.0),
            stop_loss_percent=trading_flags.get('stop_loss_percent', 15.0),
            take_profit_percent=trading_flags.get('take_profit_percent', 30.0),
            max_trades_per_day=trading_flags.get('max_trades_per_day', 5),
            atr_multiplier=risk_config.get('atr_multiplier', 2.0),
            vix_threshold=risk_config.get('high_vix_threshold', 22.0),
            position_size_multiplier=1.0
        )
    
    def record_performance(self, trade_results: List[Dict[str, Any]]):
        """
        Record performance data for the current parameters.
        
        Args:
            trade_results: List of trade result dictionaries
        """
        if not self.enabled or not trade_results:
            return
        
        # Calculate performance metrics
        metrics = PerformanceMetrics()
        
        for trade in trade_results:
            metrics.total_trades += 1
            pnl = trade.get('net', 0)
            
            if pnl > 0:
                metrics.winning_trades += 1
                metrics.total_profit += pnl
            elif pnl < 0:
                metrics.losing_trades += 1
                metrics.total_loss += abs(pnl)
        
        # Calculate derived metrics
        if metrics.total_trades > 0:
            metrics.win_rate = metrics.winning_trades / metrics.total_trades
        
        if metrics.total_loss > 0:
            metrics.profit_factor = metrics.total_profit / metrics.total_loss
        
        # Update current parameters' performance
        if self.population:
            self.population[0] = (self.population[0][0], metrics)
        
        logging.info(f"Recorded performance: {metrics.total_trades} trades, "
                    f"{metrics.win_rate:.1%} win rate, ${metrics.total_profit:.2f} profit")
    
    def should_evolve(self) -> bool:
        """Check if it's time to evolve the population."""
        if not self.enabled:
            return False
        
        if self.last_evolution_date is None:
            return True
        
        days_since_evolution = (datetime.now() - self.last_evolution_date).days
        return days_since_evolution >= self.evolution_interval_days
    
    def evolve(self) -> Optional[TradingParameters]:
        """
        Perform one generation of evolution.
        
        Returns:
            New best parameters if evolution occurred, None otherwise
        """
        if not self.enabled or not self.should_evolve():
            return None
        
        logging.info(f"Starting evolution generation {self.generation + 1}")
        
        # Calculate fitness for all individuals
        fitness_scores = []
        for params, metrics in self.population:
            fitness = metrics.calculate_fitness(self.optimization_target)
            fitness_scores.append((params, metrics, fitness))
        
        # Sort by fitness (descending)
        fitness_scores.sort(key=lambda x: x[2], reverse=True)
        
        # Track best fitness
        best_fitness = fitness_scores[0][2]
        self.best_fitness_history.append(best_fitness)
        
        logging.info(f"Best fitness this generation: {best_fitness:.2f}")
        
        # Select elite individuals
        elite = fitness_scores[:self.elite_count]
        
        # Create new population
        new_population = []
        
        # Keep elite
        for params, metrics, fitness in elite:
            new_population.append((params, PerformanceMetrics()))  # Reset metrics
        
        # Generate offspring through crossover and mutation
        while len(new_population) < self.population_size:
            # Select parents (tournament selection)
            parent1 = self._tournament_select(fitness_scores)
            parent2 = self._tournament_select(fitness_scores)
            
            # Crossover
            child = parent1.crossover(parent2)
            
            # Mutate
            child = child.mutate(self.mutation_rate)
            
            new_population.append((child, PerformanceMetrics()))
        
        # Update population
        self.population = new_population
        self.generation += 1
        self.last_evolution_date = datetime.now()
        
        # Return best parameters
        best_params = fitness_scores[0][0]
        self.current_parameters = best_params
        
        logging.info(f"Evolution complete. Generation {self.generation}")
        logging.info(f"New best parameters: {best_params.to_dict()}")
        
        return best_params
    
    def _tournament_select(self, fitness_scores: List[Tuple], tournament_size: int = 3) -> TradingParameters:
        """Select a parent using tournament selection."""
        tournament = random.sample(fitness_scores, min(tournament_size, len(fitness_scores)))
        tournament.sort(key=lambda x: x[2], reverse=True)
        return tournament[0][0]
    
    def get_current_parameters(self) -> TradingParameters:
        """Get the current best parameters."""
        return self.current_parameters
    
    def get_evolution_status(self) -> Dict[str, Any]:
        """Get status of the evolutionary optimization."""
        return {
            'enabled': self.enabled,
            'generation': self.generation,
            'population_size': len(self.population),
            'last_evolution': self.last_evolution_date.isoformat() if self.last_evolution_date else None,
            'best_fitness_history': self.best_fitness_history[-10:],  # Last 10 generations
            'current_parameters': self.current_parameters.to_dict(),
            'optimization_target': self.optimization_target.value
        }
    
    def apply_parameters_to_config(self, params: TradingParameters) -> Dict[str, Any]:
        """
        Apply evolved parameters to the configuration.
        
        Returns:
            Updated configuration dictionary
        """
        updated_config = copy.deepcopy(self.config)
        
        # Update trading flags
        updated_config.setdefault('trading_flags', {})
        updated_config['trading_flags']['risk_per_trade_percent'] = params.risk_per_trade
        updated_config['trading_flags']['stop_loss_percent'] = params.stop_loss_percent
        updated_config['trading_flags']['take_profit_percent'] = params.take_profit_percent
        updated_config['trading_flags']['max_trades_per_day'] = params.max_trades_per_day
        
        # Update risk management
        updated_config.setdefault('risk_management', {})
        updated_config['risk_management']['atr_multiplier'] = params.atr_multiplier
        updated_config['risk_management']['high_vix_threshold'] = params.vix_threshold
        
        logging.info("Applied evolved parameters to configuration")
        
        return updated_config
    
    def save_state(self, filepath: str):
        """Save the evolutionary state to file."""
        state = {
            'generation': self.generation,
            'last_evolution_date': self.last_evolution_date.isoformat() if self.last_evolution_date else None,
            'current_parameters': self.current_parameters.to_dict(),
            'best_fitness_history': self.best_fitness_history,
            'population': [(params.to_dict(), metrics.__dict__) for params, metrics in self.population]
        }
        
        with open(filepath, 'w') as f:
            json.dump(state, f, indent=2)
        
        logging.info(f"Saved evolutionary state to {filepath}")
    
    def load_state(self, filepath: str):
        """Load the evolutionary state from file."""
        try:
            with open(filepath, 'r') as f:
                state = json.load(f)
            
            self.generation = state.get('generation', 0)
            
            if state.get('last_evolution_date'):
                self.last_evolution_date = datetime.fromisoformat(state['last_evolution_date'])
            
            self.current_parameters = TradingParameters.from_dict(state.get('current_parameters', {}))
            self.best_fitness_history = state.get('best_fitness_history', [])
            
            # Reconstruct population
            self.population = []
            for params_dict, metrics_dict in state.get('population', []):
                params = TradingParameters.from_dict(params_dict)
                metrics = PerformanceMetrics(**metrics_dict)
                self.population.append((params, metrics))
            
            logging.info(f"Loaded evolutionary state from {filepath}")
            
        except Exception as e:
            logging.error(f"Failed to load evolutionary state: {e}")
            self._initialize_population()