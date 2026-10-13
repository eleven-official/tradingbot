"""
Parameter Sensitivity Analysis and Optimization
Implements sensitivity analysis, parameter optimization, and robustness testing
"""
import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from concurrent.futures import ProcessPoolExecutor
import itertools


class OptimizationMethod(Enum):
    """Optimization methods."""
    GRID_SEARCH = "grid_search"
    RANDOM_SEARCH = "random_search"
    BAYESIAN = "bayesian"
    GENETIC = "genetic"
    SIMULATED_ANNEALING = "simulated_annealing"


class SensitivityMetric(Enum):
    """Sensitivity metrics."""
    SHARPE_RATIO = "sharpe_ratio"
    TOTAL_RETURN = "total_return"
    MAX_DRAWDOWN = "max_drawdown"
    SORTINO_RATIO = "sortino_ratio"
    CALMAR_RATIO = "calmar_ratio"
    WIN_RATE = "win_rate"
    PROFIT_FACTOR = "profit_factor"


@dataclass
class ParameterRange:
    """Parameter range for optimization."""
    name: str
    min_value: float
    max_value: float
    step: float
    log_scale: bool = False


@dataclass
class OptimizationResult:
    """Optimization result."""
    best_parameters: Dict[str, float]
    best_score: float
    all_results: List[Dict[str, any]]
    optimization_method: OptimizationMethod
    computation_time: float
    timestamp: datetime


@dataclass
class SensitivityAnalysisResult:
    """Sensitivity analysis result."""
    parameter_name: str
    sensitivity_scores: Dict[str, float]
    tornado_chart_data: List[Tuple[str, float]]
    parameter_importance: Dict[str, float]
    recommendations: List[str]


class ParameterOptimizer:
    """
    Parameter optimization using multiple methods.
    """
    
    def __init__(self, optimization_method: OptimizationMethod = OptimizationMethod.GRID_SEARCH):
        self.optimization_method = optimization_method
        self.logger = logging.getLogger(__name__)
    
    def optimize(self, objective_function: Callable[[Dict[str, float]], float],
                parameter_ranges: List[ParameterRange],
                n_iterations: int = 100) -> OptimizationResult:
        """
        Optimize parameters using specified method.
        """
        start_time = datetime.now()
        
        if self.optimization_method == OptimizationMethod.GRID_SEARCH:
            result = self._grid_search(objective_function, parameter_ranges)
        elif self.optimization_method == OptimizationMethod.RANDOM_SEARCH:
            result = self._random_search(objective_function, parameter_ranges, n_iterations)
        elif self.optimization_method == OptimizationMethod.GENETIC:
            result = self._genetic_optimization(objective_function, parameter_ranges, n_iterations)
        else:
            result = self._grid_search(objective_function, parameter_ranges)
        
        computation_time = (datetime.now() - start_time).total_seconds()
        
        return OptimizationResult(
            best_parameters=result['best_params'],
            best_score=result['best_score'],
            all_results=result['all_results'],
            optimization_method=self.optimization_method,
            computation_time=computation_time,
            timestamp=datetime.now()
        )
    
    def _grid_search(self, objective_function: Callable[[Dict[str, float]], float],
                    parameter_ranges: List[ParameterRange]) -> Dict[str, any]:
        """Grid search optimization."""
        # Generate parameter grid
        param_names = [p.name for p in parameter_ranges]
        param_values = []
        
        for p in parameter_ranges:
            if p.log_scale:
                values = np.logspace(np.log10(p.min_value), np.log10(p.max_value), 
                                   int((p.max_value - p.min_value) / p.step) + 1)
            else:
                values = np.arange(p.min_value, p.max_value + p.step, p.step)
            param_values.append(values)
        
        # Generate all combinations
        param_combinations = list(itertools.product(*param_values))
        
        self.logger.info(f"Grid search: {len(param_combinations)} parameter combinations")
        
        # Evaluate all combinations
        all_results = []
        best_score = -np.inf
        best_params = {}
        
        for i, combination in enumerate(param_combinations):
            params = dict(zip(param_names, combination))
            
            try:
                score = objective_function(params)
                
                result = {
                    'parameters': params.copy(),
                    'score': score
                }
                all_results.append(result)
                
                if score > best_score:
                    best_score = score
                    best_params = params.copy()
                
                if (i + 1) % 100 == 0:
                    self.logger.info(f"Evaluated {i + 1}/{len(param_combinations)} combinations")
            
            except Exception as e:
                self.logger.error(f"Error evaluating parameters {params}: {e}")
        
        return {
            'best_params': best_params,
            'best_score': best_score,
            'all_results': all_results
        }
    
    def _random_search(self, objective_function: Callable[[Dict[str, float]], float],
                      parameter_ranges: List[ParameterRange],
                      n_iterations: int) -> Dict[str, any]:
        """Random search optimization."""
        all_results = []
        best_score = -np.inf
        best_params = {}
        
        for i in range(n_iterations):
            params = {}
            for p in parameter_ranges:
                if p.log_scale:
                    params[p.name] = np.random.uniform(np.log10(p.min_value), np.log10(p.max_value))
                    params[p.name] = 10 ** params[p.name]
                else:
                    params[p.name] = np.random.uniform(p.min_value, p.max_value)
            
            try:
                score = objective_function(params)
                
                result = {
                    'parameters': params.copy(),
                    'score': score
                }
                all_results.append(result)
                
                if score > best_score:
                    best_score = score
                    best_params = params.copy()
            
            except Exception as e:
                self.logger.error(f"Error evaluating parameters {params}: {e}")
        
        return {
            'best_params': best_params,
            'best_score': best_score,
            'all_results': all_results
        }
    
    def _genetic_optimization(self, objective_function: Callable[[Dict[str, float]], float],
                            parameter_ranges: List[ParameterRange],
                            n_iterations: int) -> Dict[str, any]:
        """Genetic algorithm optimization."""
        population_size = 50
        mutation_rate = 0.1
        crossover_rate = 0.7
        
        # Initialize population
        population = self._initialize_population(population_size, parameter_ranges)
        
        all_results = []
        best_score = -np.inf
        best_params = {}
        
        for generation in range(n_iterations):
            # Evaluate population
            fitness_scores = []
            for individual in population:
                try:
                    score = objective_function(individual)
                    fitness_scores.append(score)
                    
                    if score > best_score:
                        best_score = score
                        best_params = individual.copy()
                    
                    all_results.append({
                        'parameters': individual.copy(),
                        'score': score
                    })
                except Exception as e:
                    fitness_scores.append(-np.inf)
            
            # Selection
            selected = self._selection(population, fitness_scores, population_size // 2)
            
            # Crossover
            offspring = self._crossover(selected, crossover_rate, parameter_ranges)
            
            # Mutation
            offspring = self._mutation(offspring, mutation_rate, parameter_ranges)
            
            # New population
            population = offspring + selected[:population_size - len(offspring)]
        
        return {
            'best_params': best_params,
            'best_score': best_score,
            'all_results': all_results
        }
    
    def _initialize_population(self, size: int, parameter_ranges: List[ParameterRange]) -> List[Dict[str, float]]:
        """Initialize random population."""
        population = []
        for _ in range(size):
            individual = {}
            for p in parameter_ranges:
                if p.log_scale:
                    individual[p.name] = 10 ** np.random.uniform(np.log10(p.min_value), np.log10(p.max_value))
                else:
                    individual[p.name] = np.random.uniform(p.min_value, p.max_value)
            population.append(individual)
        return population
    
    def _selection(self, population: List[Dict[str, float]], 
                  fitness_scores: List[float], n_select: int) -> List[Dict[str, float]]:
        """Tournament selection."""
        selected = []
        for _ in range(n_select):
            # Tournament
            tournament_size = 3
            tournament_indices = np.random.choice(len(population), tournament_size, replace=False)
            tournament_fitness = [fitness_scores[i] for i in tournament_indices]
            winner_index = tournament_indices[np.argmax(tournament_fitness)]
            selected.append(population[winner_index].copy())
        return selected
    
    def _crossover(self, population: List[Dict[str, float]], crossover_rate: float,
                  parameter_ranges: List[ParameterRange]) -> List[Dict[str, float]]:
        """Crossover operation."""
        offspring = []
        for i in range(0, len(population) - 1, 2):
            if np.random.random() < crossover_rate:
                parent1 = population[i]
                parent2 = population[i + 1]
                
                child1 = {}
                child2 = {}
                
                for p in parameter_ranges:
                    if np.random.random() < 0.5:
                        child1[p.name] = parent1[p.name]
                        child2[p.name] = parent2[p.name]
                    else:
                        child1[p.name] = parent2[p.name]
                        child2[p.name] = parent1[p.name]
                
                offspring.extend([child1, child2])
        
        return offspring
    
    def _mutation(self, population: List[Dict[str, float]], mutation_rate: float,
                parameter_ranges: List[ParameterRange]) -> List[Dict[str, float]]:
        """Mutation operation."""
        for individual in population:
            for p in parameter_ranges:
                if np.random.random() < mutation_rate:
                    if p.log_scale:
                        individual[p.name] = 10 ** np.random.uniform(np.log10(p.min_value), np.log10(p.max_value))
                    else:
                        individual[p.name] = np.random.uniform(p.min_value, p.max_value)
        return population


class SensitivityAnalyzer:
    """
    Parameter sensitivity analysis.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def analyze_sensitivity(self, objective_function: Callable[[Dict[str, float]], float],
                          base_parameters: Dict[str, float],
                          parameter_ranges: List[ParameterRange],
                          metric: SensitivityMetric = SensitivityMetric.SHARPE_RATIO) -> SensitivityAnalysisResult:
        """
        Analyze parameter sensitivity.
        """
        base_score = objective_function(base_parameters)
        
        sensitivity_scores = {}
        tornado_chart_data = []
        parameter_importance = {}
        
        for param_range in parameter_ranges:
            param_name = param_range.name
            base_value = base_parameters.get(param_name, param_range.min_value)
            
            # Test variations
            variations = np.linspace(param_range.min_value, param_range.max_value, 10)
            scores = []
            
            for value in variations:
                test_params = base_parameters.copy()
                test_params[param_name] = value
                
                try:
                    score = objective_function(test_params)
                    scores.append(score)
                except Exception as e:
                    scores.append(-np.inf)
            
            # Calculate sensitivity (standard deviation of scores)
            if len(scores) > 1:
                sensitivity = np.std(scores)
                sensitivity_scores[param_name] = sensitivity
                
                # Tornado chart data (max deviation from base)
                max_deviation = max(abs(score - base_score) for score in scores)
                tornado_chart_data.append((param_name, max_deviation))
                
                # Parameter importance (normalized sensitivity)
                parameter_importance[param_name] = sensitivity
        
        # Normalize importance
        total_importance = sum(parameter_importance.values())
        if total_importance > 0:
            parameter_importance = {k: v / total_importance for k, v in parameter_importance.items()}
        
        # Sort tornado chart
        tornado_chart_data.sort(key=lambda x: x[1], reverse=True)
        
        # Generate recommendations
        recommendations = self._generate_sensitivity_recommendations(
            sensitivity_scores, parameter_importance, tornado_chart_data
        )
        
        return SensitivityAnalysisResult(
            parameter_name="All",
            sensitivity_scores=sensitivity_scores,
            tornado_chart_data=tornado_chart_data,
            parameter_importance=parameter_importance,
            recommendations=recommendations
        )
    
    def _generate_sensitivity_recommendations(self, sensitivity_scores: Dict[str, float],
                                            parameter_importance: Dict[str, float],
                                            tornado_chart_data: List[Tuple[str, float]]) -> List[str]:
        """Generate recommendations based on sensitivity analysis."""
        recommendations = []
        
        # Identify most important parameters
        if tornado_chart_data:
            most_important = tornado_chart_data[0][0]
            recommendations.append(f"Most sensitive parameter: {most_important}")
        
        # Identify robust parameters
        robust_params = [p for p, score in sensitivity_scores.items() if score < 0.01]
        if robust_params:
            recommendations.append(f"Robust parameters (low sensitivity): {', '.join(robust_params)}")
        
        # Identify sensitive parameters
        sensitive_params = [p for p, score in sensitivity_scores.items() if score > 0.1]
        if sensitive_params:
            recommendations.append(f"Sensitive parameters (high sensitivity): {', '.join(sensitive_params)}")
            recommendations.append("Consider optimizing sensitive parameters with finer granularity")
        
        return recommendations


class RobustnessTester:
    """
    Strategy robustness testing.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def test_robustness(self, objective_function: Callable[[Dict[str, float]], float],
                       base_parameters: Dict[str, float],
                       parameter_ranges: List[ParameterRange],
                       n_scenarios: int = 100) -> Dict[str, any]:
        """
        Test strategy robustness across parameter variations.
        """
        # Generate random parameter scenarios
        scenarios = []
        for _ in range(n_scenarios):
            scenario = base_parameters.copy()
            for p in parameter_ranges:
                if np.random.random() < 0.5:  # 50% chance to vary each parameter
                    if p.log_scale:
                        scenario[p.name] = 10 ** np.random.uniform(np.log10(p.min_value), np.log10(p.max_value))
                    else:
                        scenario[p.name] = np.random.uniform(p.min_value, p.max_value)
            scenarios.append(scenario)
        
        # Evaluate scenarios
        scores = []
        for scenario in scenarios:
            try:
                score = objective_function(scenario)
                scores.append(score)
            except Exception as e:
                scores.append -np.inf
        
        # Calculate robustness metrics
        valid_scores = [s for s in scores if s != -np.inf]
        
        if valid_scores:
            robustness_metrics = {
                'mean_score': np.mean(valid_scores),
                'std_score': np.std(valid_scores),
                'min_score': np.min(valid_scores),
                'max_score': np.max(valid_scores),
                'percentile_5': np.percentile(valid_scores, 5),
                'percentile_25': np.percentile(valid_scores, 25),
                'percentile_75': np.percentile(valid_scores, 75),
                'percentile_95': np.percentile(valid_scores, 95),
                'success_rate': len(valid_scores) / len(scores),
                'coefficient_of_variation': np.std(valid_scores) / np.mean(valid_scores) if np.mean(valid_scores) > 0 else np.inf
            }
        else:
            robustness_metrics = {
                'mean_score': 0,
                'std_score': 0,
                'min_score': 0,
                'max_score': 0,
                'percentile_5': 0,
                'percentile_25': 0,
                'percentile_75': 0,
                'percentile_95': 0,
                'success_rate': 0,
                'coefficient_of_variation': 0
            }
        
        return robustness_metrics


class ParameterSensitivitySuite:
    """
    Complete parameter sensitivity and optimization suite.
    """
    
    def __init__(self):
        self.optimizer = ParameterOptimizer()
        self.sensitivity_analyzer = SensitivityAnalyzer()
        self.robustness_tester = RobustnessTester()
        self.logger = logging.getLogger(__name__)
    
    def full_analysis(self, objective_function: Callable[[Dict[str, float]], float],
                     base_parameters: Dict[str, float],
                     parameter_ranges: List[ParameterRange]) -> Dict[str, any]:
        """
        Run complete parameter analysis: optimization, sensitivity, and robustness.
        """
        self.logger.info("Starting full parameter analysis")
        
        # Optimization
        self.logger.info("Running parameter optimization...")
        optimization_result = self.optimizer.optimize(objective_function, parameter_ranges)
        
        # Sensitivity analysis
        self.logger.info("Running sensitivity analysis...")
        sensitivity_result = self.sensitivity_analyzer.analyze_sensitivity(
            objective_function, base_parameters, parameter_ranges
        )
        
        # Robustness testing
        self.logger.info("Running robustness testing...")
        robustness_result = self.robustness_tester.test_robustness(
            objective_function, base_parameters, parameter_ranges
        )
        
        return {
            'optimization': optimization_result,
            'sensitivity': sensitivity_result,
            'robustness': robustness_result
        }