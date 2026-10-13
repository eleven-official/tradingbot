"""
Neural Self-Evolution & Strategy Mutation Engine
Genetic algorithm-based strategy optimization with shadow backtesting
"""
import asyncio
import logging
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import json
import random
from collections import deque
import pickle


class MutationType(Enum):
    """Types of strategy mutations."""
    INDICATOR_WEIGHT = "indicator_weight"
    ENTRY_THRESHOLD = "entry_threshold"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    TIMEFRAME = "timeframe"
    NEW_INDICATOR = "new_indicator"


@dataclass
class StrategyGenome:
    """Represents a trading strategy's genetic makeup."""
    genome_id: str
    indicator_weights: Dict[str, float]
    entry_thresholds: Dict[str, float]
    stop_loss_atr_multiplier: float
    take_profit_atr_multiplier: float
    primary_timeframe: str
    secondary_timeframe: str
    fitness_score: float
    age: int = 0
    total_trades: int = 0
    winning_trades: int = 0
    total_profit: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    last_mutated: Optional[datetime] = None


class GeneticOptimizer:
    """
    Genetic algorithm-based strategy optimizer.
    Evolves trading strategies through mutation, crossover, and selection.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.mutation_config = config.get('neural_mutation', {})
        
        # Configuration
        self.enabled = self.mutation_config.get('enabled', True)
        self.population_size = self.mutation_config.get('population_size', 50)
        self.mutation_rate = self.mutation_config.get('mutation_rate', 0.1)
        self.selection_pressure = self.mutation_config.get('selection_pressure', 0.7)
        self.evolution_interval_hours = self.mutation_config.get('evolution_interval_hours', 1)
        
        # Population
        self.population: List[StrategyGenome] = []
        self.generation = 0
        
        # Available indicators
        self.available_indicators = [
            'rsi', 'macd', 'bollinger', 'ema', 'atr', 'volume',
            'stochastic', 'williams_r', 'adx', 'cci', 'momentum'
        ]
        
        # Timeframes
        self.available_timeframes = ['1m', '5m', '15m', '1h', '4h', '1d']
        
        # Evolution state
        self.last_evolution: Optional[datetime] = None
        self.total_mutations = 0
        
        logging.info("Genetic Optimizer initialized")
    
    async def initialize(self):
        """Initialize the genetic optimizer."""
        if not self.enabled:
            return
        
        self.logger = logging.getLogger(__name__)
        
        # Load existing population or create initial population
        await self._load_or_create_population()
        
        self.logger.info(f"Genetic Optimizer initialized with {len(self.population)} strategies")
    
    async def _load_or_create_population(self):
        """Load existing population or create initial random population."""
        try:
            # Try to load from file
            with open('strategy_population.pkl', 'rb') as f:
                self.population = pickle.load(f)
                self.logger.info(f"Loaded {len(self.population)} strategies from file")
        except FileNotFoundError:
            # Create initial random population
            self.logger.info("Creating initial random population...")
            for i in range(self.population_size):
                genome = self._create_random_genome(f"gen_{i}")
                self.population.append(genome)
            
            # Save initial population
            await self._save_population()
    
    def _create_random_genome(self, genome_id: str) -> StrategyGenome:
        """Create a random strategy genome."""
        # Random indicator weights
        indicator_weights = {}
        for indicator in self.available_indicators:
            indicator_weights[indicator] = random.random()
        
        # Normalize weights
        total_weight = sum(indicator_weights.values())
        indicator_weights = {k: v/total_weight for k, v in indicator_weights.items()}
        
        # Random entry thresholds
        entry_thresholds = {
            'rsi_oversold': random.uniform(20, 40),
            'rsi_overbought': random.uniform(60, 80),
            'macd_signal': random.uniform(-1, 1),
            'bollinger_position': random.uniform(-2, 2)
        }
        
        # Random ATR multipliers
        stop_loss_atr = random.uniform(1.5, 3.0)
        take_profit_atr = random.uniform(2.0, 5.0)
        
        # Random timeframes
        primary_tf = random.choice(self.available_timeframes)
        secondary_tf = random.choice(self.available_timeframes)
        
        return StrategyGenome(
            genome_id=genome_id,
            indicator_weights=indicator_weights,
            entry_thresholds=entry_thresholds,
            stop_loss_atr_multiplier=stop_loss_atr,
            take_profit_atr_multiplier=take_profit_atr,
            primary_timeframe=primary_tf,
            secondary_timeframe=secondary_tf,
            fitness_score=0.0
        )
    
    async def should_mutate(self) -> bool:
        """Check if it's time to mutate the population."""
        if not self.enabled:
            return False
        
        if self.last_evolution is None:
            return True
        
        hours_since_evolution = (datetime.now() - self.last_evolution).total_seconds() / 3600
        return hours_since_evolution >= self.evolution_interval_hours
    
    async def mutate_strategy(self):
        """Evolve the population through genetic operations."""
        self.logger.info("Starting strategy mutation...")
        
        # Evaluate fitness of current population
        await self._evaluate_population_fitness()
        
        # Selection - keep top performers
        sorted_population = sorted(self.population, key=lambda g: g.fitness_score, reverse=True)
        survivors = sorted_population[:int(self.population_size * self.selection_pressure)]
        
        # Create new generation through crossover and mutation
        new_generation = []
        
        # Keep survivors
        new_generation.extend(survivors)
        
        # Create offspring through crossover
        while len(new_generation) < self.population_size:
            parent1 = random.choice(survivors)
            parent2 = random.choice(survivors)
            offspring = self._crossover(parent1, parent2)
            new_generation.append(offspring)
        
        # Apply mutations
        for genome in new_generation:
            if random.random() < self.mutation_rate:
                self._mutate_genome(genome)
        
        # Update population
        self.population = new_generation
        self.generation += 1
        self.last_evolution = datetime.now()
        self.total_mutations += 1
        
        # Save population
        await self._save_population()
        
        self.logger.info(f"Strategy mutation complete. Generation: {self.generation}, Mutations: {self.total_mutations}")
    
    def _crossover(self, parent1: StrategyGenome, parent2: StrategyGenome) -> StrategyGenome:
        """Crossover two parent genomes to create offspring."""
        offspring_id = f"gen_{self.generation}_{random.randint(1000, 9999)}"
        
        # Crossover indicator weights
        indicator_weights = {}
        for indicator in self.available_indicators:
            weight1 = parent1.indicator_weights.get(indicator, 0)
            weight2 = parent2.indicator_weights.get(indicator, 0)
            # Weighted random selection
            offspring_weight = weight1 if random.random() < 0.5 else weight2
            indicator_weights[indicator] = offspring_weight
        
        # Normalize weights
        total_weight = sum(indicator_weights.values())
        indicator_weights = {k: v/total_weight for k, v in indicator_weights.items()}
        
        # Crossover entry thresholds
        entry_thresholds = {}
        for key in parent1.entry_thresholds:
            threshold1 = parent1.entry_thresholds[key]
            threshold2 = parent2.entry_thresholds[key]
            offspring_threshold = threshold1 if random.random() < 0.5 else threshold2
            entry_thresholds[key] = offspring_threshold
        
        # Crossover ATR multipliers
        stop_loss_atr = (parent1.stop_loss_atr_multiplier + parent2.stop_loss_atr_multiplier) / 2
        take_profit_atr = (parent1.take_profit_atr_multiplier + parent2.take_profit_atr_multiplier) / 2
        
        # Crossover timeframes
        primary_tf = parent1.primary_timeframe if random.random() < 0.5 else parent2.primary_timeframe
        secondary_tf = parent1.secondary_timeframe if random.random() < 0.5 else parent2.secondary_timeframe
        
        return StrategyGenome(
            genome_id=offspring_id,
            indicator_weights=indicator_weights,
            entry_thresholds=entry_thresholds,
            stop_loss_atr_multiplier=stop_loss_atr,
            take_profit_atr_multiplier=take_profit_atr,
            primary_timeframe=primary_tf,
            secondary_timeframe=secondary_tf,
            fitness_score=0.0
        )
    
    def _mutate_genome(self, genome: StrategyGenome):
        """Apply random mutations to a genome."""
        mutation_type = random.choice(list(MutationType))
        
        if mutation_type == MutationType.INDICATOR_WEIGHT:
            # Mutate indicator weights
            indicator = random.choice(self.available_indicators)
            genome.indicator_weights[indicator] = random.random()
            
            # Renormalize
            total_weight = sum(genome.indicator_weights.values())
            genome.indicator_weights = {k: v/total_weight for k, v in genome.indicator_weights.items()}
        
        elif mutation_type == MutationType.ENTRY_THRESHOLD:
            # Mutate entry thresholds
            threshold_key = random.choice(list(genome.entry_thresholds.keys()))
            genome.entry_thresholds[threshold_key] = random.uniform(0, 100)
        
        elif mutation_type == MutationType.STOP_LOSS:
            # Mutate stop loss ATR multiplier
            genome.stop_loss_atr_multiplier = random.uniform(1.0, 4.0)
        
        elif mutation_type == MutationType.TAKE_PROFIT:
            # Mutate take profit ATR multiplier
            genome.take_profit_atr_multiplier = random.uniform(1.5, 6.0)
        
        elif mutation_type == MutationType.TIMEFRAME:
            # Mutate timeframes
            genome.primary_timeframe = random.choice(self.available_timeframes)
            genome.secondary_timeframe = random.choice(self.available_timeframes)
        
        genome.last_mutated = datetime.now()
    
    async def _evaluate_population_fitness(self):
        """Evaluate fitness of all genomes in population."""
        for genome in self.population:
            genome.age += 1
            
            # Fitness calculation based on historical performance
            # In production, this would use actual backtest results
            base_fitness = genome.fitness_score * 0.7  # Carry over some previous fitness
            
            # Age penalty (prefer newer strategies)
            age_penalty = max(0, genome.age - 10) * 0.01
            age_adjusted_fitness = base_fitness - age_penalty
            
            # Add bonus for diversity
            diversity_bonus = self._calculate_diversity_bonus(genome)
            
            genome.fitness_score = age_adjusted_fitness + diversity_bonus
    
    def _calculate_diversity_bonus(self, genome: StrategyGenome) -> float:
        """Calculate diversity bonus to encourage exploration."""
        # Compare with average population
        if not self.population:
            return 0.0
        
        avg_weights = {}
        for indicator in self.available_indicators:
            weights = [g.indicator_weights.get(indicator, 0) for g in self.population]
            avg_weights[indicator] = sum(weights) / len(weights)
        
        # Calculate distance from average
        distance = 0.0
        for indicator in self.available_indicators:
            distance += abs(genome.indicator_weights.get(indicator, 0) - avg_weights[indicator])
        
        distance = distance / len(self.available_indicators)
        
        # Reward diversity
        return distance * 0.1
    
    async def detect_regime(self) -> str:
        """Detect current market regime."""
        # This would analyze market data to detect regime
        # For now, return neutral
        return "neutral"
    
    async def get_best_strategy(self) -> Optional[StrategyGenome]:
        """Get the best performing strategy from population."""
        if not self.population:
            return None
        
        return max(self.population, key=lambda g: g.fitness_score)
    
    async def shutdown(self):
        """Shutdown the genetic optimizer."""
        if self.enabled:
            await self._save_population()
            self.logger.info("Genetic Optimizer shutdown complete")
    
    async def _save_population(self):
        """Save population to file."""
        try:
            with open('strategy_population.pkl', 'wb') as f:
                pickle.dump(self.population, f)
        except Exception as e:
            self.logger.error(f"Failed to save population: {e}")


class ShadowBacktester:
    """
    Shadow backtesting system running in parallel with live trading.
    Continuously tests strategies on recent data to detect performance degradation.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.backtest_config = config.get('backtesting', {})
        
        # Configuration
        self.shadow_count = self.backtest_config.get('shadow_count', 10)
        self.lookback_days = self.backtest_config.get('lookback_days', 30)
        self.min_trades_required = self.backtest_config.get('min_trades_required', 20)
        
        # Shadow results
        self.shadow_results: Dict[str, Dict[str, Any]] = {}
        
        logging.info("Shadow Backtester initialized")
    
    async def initialize(self):
        """Initialize the shadow backtester."""
        self.logger = logging.getLogger(__name__)
        self.logger.info("Shadow Backtester initialized")
    
    async def run_shadow_tests(self):
        """Run shadow backtests on current strategies."""
        # This would continuously backtest strategies on recent data
        # For now, this is a placeholder
        pass
    
    async def shutdown(self):
        """Shutdown the shadow backtester."""
        self.logger.info("Shadow Backtester shutdown complete")