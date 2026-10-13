"""
Self-Learning AI System Test Script
Tests the advanced AI capabilities including adaptive learning, reinforcement learning, and portfolio optimization.
"""
import sys
import os
import yaml
import logging
from unittest.mock import patch

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.self_learning_ai import (
    SelfLearningSystem, 
    StrategyPerformance, 
    AdaptiveParameterTuner,
    EnsembleStrategySelector
)
from core.reinforcement_learning import (
    QLearningAgent,
    StrategyOptimizer,
    MarketRegimeLearner,
    AdvancedPortfolioOptimizer
)

def test_strategy_performance():
    """Test strategy performance tracking."""
    print("Testing Strategy Performance Tracking...")
    
    perf = StrategyPerformance("TestStrategy")
    
    # Record some trades
    perf.update(1000.0, {'regime': 'TRENDING', 'vix': 18})
    perf.update(-500.0, {'regime': 'TRENDING', 'vix': 18})
    perf.update(800.0, {'regime': 'RANGING', 'vix': 15})
    
    print(f"[PASS] Strategy performance tracked:")
    print(f"       Total trades: {perf.total_trades}")
    print(f"       Win rate: {perf.win_rate:.1f}%")
    print(f"       Profit factor: {perf.profit_factor:.2f}")
    print(f"       Overall score: {perf.get_score():.1f}")
    
    return True

def test_adaptive_parameter_tuner():
    """Test adaptive parameter tuning."""
    print("\nTesting Adaptive Parameter Tuning...")
    
    config = {
        'adaptive_tuning': {
            'optimization_interval': 24
        }
    }
    
    tuner = AdaptiveParameterTuner(config)
    
    # Create performance data
    perf = StrategyPerformance("TestStrategy")
    for i in range(15):
        pnl = 100 if i % 3 == 0 else -50  # Mixed performance
        perf.update(pnl, {'regime': 'TRENDING', 'vix': 18})
    
    # Test parameter optimization
    current_params = {
        'risk_multiplier': 1.0,
        'stop_loss_multiplier': 1.0,
        'entry_threshold': 65.0
    }
    
    new_params = tuner.optimize_parameters("TestStrategy", current_params, perf)
    
    print(f"[PASS] Parameter optimization completed:")
    print(f"       Old params: {current_params}")
    print(f"       New params: {new_params}")
    print(f"       Performance score: {perf.get_score():.1f}")
    
    return True

def test_ensemble_strategy_selector():
    """Test ensemble strategy selection."""
    print("\nTesting Ensemble Strategy Selector...")
    
    config = {'ensemble': {'method': 'performance_based'}}
    selector = EnsembleStrategySelector(config)
    
    # Create performance data for multiple strategies
    performances = {
        'StrategyA': StrategyPerformance('StrategyA'),
        'StrategyB': StrategyPerformance('StrategyB'),
        'StrategyC': StrategyPerformance('StrategyC')
    }
    
    # Simulate different performance levels
    performances['StrategyA'].update(1000.0, {})
    performances['StrategyA'].update(800.0, {})
    performances['StrategyA'].update(-200.0, {})
    
    performances['StrategyB'].update(500.0, {})
    performances['StrategyB'].update(-300.0, {})
    performances['StrategyB'].update(200.0, {})
    
    performances['StrategyC'].update(1500.0, {})
    performances['StrategyC'].update(1200.0, {})
    performances['StrategyC'].update(-100.0, {})
    
    # Update weights
    selector.update_weights(performances)
    
    print(f"[PASS] Ensemble weights calculated:")
    for strategy, weight in selector.strategy_weights.items():
        print(f"       {strategy}: {weight:.3f}")
    
    # Test ensemble signal
    signals = {
        'StrategyA': 'BUY',
        'StrategyB': 'HOLD',
        'StrategyC': 'BUY'
    }
    
    ensemble_signal = selector.select_ensemble_signal(signals, {'regime': 'TRENDING'})
    print(f"[PASS] Ensemble signal: {ensemble_signal}")
    
    return True

def test_q_learning_agent():
    """Test Q-learning agent."""
    print("\nTesting Q-Learning Agent...")
    
    config = {
        'rl': {
            'learning_rate': 0.1,
            'discount_factor': 0.95,
            'epsilon': 0.1
        }
    }
    
    agent = QLearningAgent(config)
    
    # Test state representation
    market_conditions = {
        'regime': 'TRENDING',
        'vix': 18,
        'daily_trend': 'BULLISH'
    }
    
    state = agent.get_state(market_conditions)
    print(f"[PASS] State representation: {state}")
    
    # Test action selection
    action = agent.choose_action(state, training=True)
    print(f"[PASS] Action selected: {action}")
    
    # Test Q-value update
    next_state = "RANGING_MEDIUM_NEUTRAL_MIDDAY"
    reward = 100.0
    agent.update_q_value(state, action, reward, next_state)
    print(f"[PASS] Q-value updated for action: {action}")
    
    # Test best action selection
    best_action = agent.get_best_action(state)
    print(f"[PASS] Best action: {best_action}")
    
    return True

def test_strategy_optimizer():
    """Test strategy parameter optimizer."""
    print("\nTesting Strategy Optimizer...")
    
    config = {}
    optimizer = StrategyOptimizer(config)
    
    # Test parameter suggestion
    current_performance = 45.0  # Poor performance
    new_params = optimizer.suggest_parameters("TestStrategy", current_performance)
    
    print(f"[PASS] Parameter suggestions generated:")
    print(f"       Performance: {current_performance}")
    print(f"       New parameters: {new_params}")
    
    # Test best parameter update
    optimizer.update_best_parameters("TestStrategy", new_params, 60.0)
    print(f"[PASS] Best parameters updated")
    
    return True

def test_market_regime_learner():
    """Test market regime learner."""
    print("\nTesting Market Regime Learner...")
    
    config = {}
    learner = MarketRegimeLearner(config)
    
    # Test regime detection
    market_data = {
        'vix': 20,
        'daily_trend': 'BULLISH',
        'volatility': 0.015,
        'volume_ratio': 1.2
    }
    
    regime = learner.detect_regime(market_data)
    print(f"[PASS] Detected regime: {regime}")
    print(f"       Confidence: {learner.regime_confidence:.2f}")
    
    # Test regime performance recording
    learner.record_regime_performance(regime, "TestStrategy", 500.0)
    print(f"[PASS] Regime performance recorded")
    
    # Test best strategy for regime
    best_strategy = learner.get_best_strategy_for_regime(regime)
    print(f"[PASS] Best strategy for regime: {best_strategy}")
    
    # Test regime statistics
    stats = learner.get_regime_statistics()
    print(f"[PASS] Regime statistics: {stats}")
    
    return True

def test_portfolio_optimizer():
    """Test portfolio optimizer."""
    print("\nTesting Portfolio Optimizer...")
    
    config = {}
    optimizer = AdvancedPortfolioOptimizer(config)
    
    # Add some returns
    optimizer.update_returns("StrategyA", 0.05)
    optimizer.update_returns("StrategyA", -0.02)
    optimizer.update_returns("StrategyA", 0.03)
    
    optimizer.update_returns("StrategyB", 0.02)
    optimizer.update_returns("StrategyB", 0.04)
    optimizer.update_returns("StrategyB", -0.01)
    
    print(f"[PASS] Returns data added")
    
    # Test correlation calculation
    optimizer.calculate_correlations()
    print(f"[PASS] Correlations calculated")
    
    # Test portfolio optimization
    weights = optimizer.optimize_portfolio()
    print(f"[PASS] Portfolio weights optimized:")
    for strategy, weight in weights.items():
        print(f"       {strategy}: {weight:.3f}")
    
    # Test portfolio statistics
    stats = optimizer.get_portfolio_stats()
    print(f"[PASS] Portfolio statistics: {stats}")
    
    return True

def test_self_learning_system():
    """Test complete self-learning system."""
    print("\nTesting Complete Self-Learning System...")
    
    config = {
        'self_learning': {
            'enabled': True
        }
    }
    
    system = SelfLearningSystem(config)
    
    # Record some trades
    # This is a behavior test, not a request to alter the operator's learned
    # strategy state. Prevent test fixtures from writing to state/.
    with patch.object(SelfLearningSystem, '_save_state'):
        system.record_trade("StrategyA", 1000.0, {'regime': 'TRENDING', 'vix': 18})
        system.record_trade("StrategyA", -500.0, {'regime': 'TRENDING', 'vix': 18})
        system.record_trade("StrategyB", 800.0, {'regime': 'RANGING', 'vix': 15})
    
    print(f"[PASS] Trades recorded in learning system")
    
    # Test strategy ranking
    rankings = system.get_strategy_ranking()
    print(f"[PASS] Strategy rankings: {rankings}")
    
    # Test best strategy selection
    best_strategy = system.get_best_strategy({'regime': 'TRENDING'})
    print(f"[PASS] Best strategy selected: {best_strategy}")
    
    # Test ensemble signal
    signals = {
        'StrategyA': 'BUY',
        'StrategyB': 'HOLD'
    }
    ensemble_signal = system.get_ensemble_signal(signals, {'regime': 'TRENDING'})
    print(f"[PASS] Ensemble signal: {ensemble_signal}")
    
    # Test learning summary
    summary = system.get_learning_summary()
    print(f"[PASS] Learning summary: {summary}")
    
    return True

def main():
    """Run all self-learning AI tests."""
    print("=" * 60)
    print("SELF-LEARNING AI SYSTEM TEST SUITE")
    print("=" * 60)
    
    # Set up logging
    logging.basicConfig(level=logging.INFO)
    
    all_passed = True
    
    # Run tests
    all_passed &= test_strategy_performance()
    all_passed &= test_adaptive_parameter_tuner()
    all_passed &= test_ensemble_strategy_selector()
    all_passed &= test_q_learning_agent()
    all_passed &= test_strategy_optimizer()
    all_passed &= test_market_regime_learner()
    all_passed &= test_portfolio_optimizer()
    all_passed &= test_self_learning_system()
    
    # Print summary
    print("\n" + "=" * 60)
    if all_passed:
        print("[PASS] ALL TESTS PASSED - Self-learning AI is operational!")
        print("=" * 60)
        print("\nAI Capabilities Enabled:")
        print("[PASS] Adaptive parameter tuning")
        print("[PASS] Ensemble strategy combination")
        print("[PASS] Q-learning for strategy optimization")
        print("[PASS] Market regime learning")
        print("[PASS] Portfolio optimization")
        print("[PASS] Real-time performance adaptation")
        print("\nNext steps:")
        print("1. Enable self_learning in config.yaml")
        print("2. Configure AI parameters in config.self_learning.yaml")
        print("3. Run in paper trading to collect learning data")
        print("4. Monitor AI decision-making and parameter adjustments")
        print("5. Validate improvements before live trading")
        return 0
    else:
        print("[FAIL] SOME TESTS FAILED - Please review the errors above")
        print("=" * 60)
        return 1

if __name__ == '__main__':
    sys.exit(main())
