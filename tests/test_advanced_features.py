"""
Comprehensive Test Suite for New Core Engine Modules
Tests all the new advanced features added to the trading bot
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import asyncio


class TestRealExchangeManager:
    """Test real exchange manager."""
    
    @pytest.fixture
    def config(self):
        return {
            'exchanges': {
                'primary': 'binance',
                'backup': ['bybit', 'kraken'],
                'api_keys': {
                    'binance': {
                        'api_key': 'test_key',
                        'api_secret': 'test_secret',
                        'sandbox': True
                    }
                }
            }
        }
    
    @pytest.mark.asyncio
    async def test_initialization(self, config):
        """Test exchange manager initialization."""
        try:
            from core_engine.real_exchange_manager import RealExchangeManager
        except ImportError:
            pytest.skip("CCXT not available")
            return
        
        manager = RealExchangeManager(config)
        # Don't actually connect in tests
        assert manager.primary_exchange == 'binance'
        assert manager.backup_exchanges == ['bybit', 'kraken']
    
    def test_config_validation(self, config):
        """Test configuration validation."""
        try:
            from core_engine.real_exchange_manager import RealExchangeManager
        except ImportError:
            pytest.skip("CCXT not available")
            return
        
        manager = RealExchangeManager(config)
        assert manager.config == config


class TestHistoricalDataManager:
    """Test historical data manager."""
    
    @pytest.fixture
    def config(self):
        return {
            'data_db_path': 'test_data.db'
        }
    
    @pytest.mark.asyncio
    async def test_initialization(self, config):
        """Test data manager initialization."""
        from core_engine.historical_data_manager import HistoricalDataManager
        
        # Use unique filename to avoid conflicts
        import uuid
        unique_name = f"test_data_{uuid.uuid4().hex}.db"
        config['data_db_path'] = unique_name
        
        manager = HistoricalDataManager(config)
        await manager.initialize(None)
        
        assert manager.db_path.name == unique_name
        assert manager.exchange_manager is None
        
        # Cleanup
        import os
        if os.path.exists(unique_name):
            try:
                os.remove(unique_name)
            except:
                pass  # File might be locked


class TestAcademicStrategies:
    """Test academic trading strategies."""
    
    def test_momentum_strategy(self):
        """Test momentum strategy."""
        from core_engine.academic_strategies import MomentumStrategy
        
        # Create sample data
        dates = pd.date_range(start='2024-01-01', periods=100, freq='D')
        data = pd.DataFrame({
            'open': np.random.randn(100).cumsum() + 100,
            'high': np.random.randn(100).cumsum() + 102,
            'low': np.random.randn(100).cumsum() + 98,
            'close': np.random.randn(100).cumsum() + 100,
            'volume': np.random.randint(1000, 10000, 100)
        }, index=dates)
        
        strategy = MomentumStrategy()
        signals = strategy.generate_signals(data)
        
        assert strategy.validate_params()
        assert isinstance(signals, list)
    
    def test_mean_reversion_strategy(self):
        """Test mean reversion strategy."""
        from core_engine.academic_strategies import MeanReversionStrategy
        
        # Create sample data
        dates = pd.date_range(start='2024-01-01', periods=100, freq='D')
        data = pd.DataFrame({
            'open': np.random.randn(100).cumsum() + 100,
            'high': np.random.randn(100).cumsum() + 102,
            'low': np.random.randn(100).cumsum() + 98,
            'close': np.random.randn(100).cumsum() + 100,
            'volume': np.random.randint(1000, 10000, 100)
        }, index=dates)
        
        strategy = MeanReversionStrategy()
        signals = strategy.generate_signals(data)
        
        assert strategy.validate_params()
        assert isinstance(signals, list)
    
    def test_strategy_library(self):
        """Test strategy library."""
        from core_engine.academic_strategies import StrategyLibrary
        
        library = StrategyLibrary()
        strategies = library.list_strategies()
        
        assert 'momentum' in strategies
        assert 'mean_reversion' in strategies
        assert 'breakout' in strategies


class TestExecutionCostModel:
    """Test execution cost and slippage model."""
    
    def test_slippage_calculation(self):
        """Test slippage calculation."""
        from core_engine.execution_cost_model import SlippageModel, TransactionCostModel, Order, OrderSide, OrderType, MarketCondition
        
        config = TransactionCostModel()
        model = SlippageModel(config)
        
        order = Order(
            symbol='BTCUSDT',
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1.0
        )
        
        market_data = {
            'volatility': 0.02,
            'volume': 1000000,
            'avg_volume': 1000000
        }
        
        slippage, condition = model.calculate_slippage(order, None, market_data)
        
        assert slippage >= 0
        assert isinstance(condition, MarketCondition)
    
    def test_transaction_cost_calculation(self):
        """Test transaction cost calculation."""
        from core_engine.execution_cost_model import TransactionCostCalculator, TransactionCostModel, Order, OrderSide, OrderType
        
        config = TransactionCostModel()
        calculator = TransactionCostCalculator(config)
        
        order = Order(
            symbol='BTCUSDT',
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1.0
        )
        
        market_data = {
            'close': 50000,
            'volatility': 0.02,
            'volume': 1000000
        }
        
        fill = calculator.calculate_total_cost(order, 50000, None, market_data)
        
        assert fill.filled_quantity == 1.0
        assert fill.commission >= 0
        assert fill.total_cost > 0


class TestStrategyValidator:
    """Test strategy validation framework."""
    
    def test_performance_stats(self):
        """Test performance statistics calculation."""
        try:
            from core_engine.strategy_validator import PerformanceStats
        except ImportError:
            pytest.skip("scipy not available")
            return
        
        returns = pd.Series(np.random.randn(100) * 0.01)
        stats = PerformanceStats(returns)
        
        metrics = stats.calculate_metrics()
        
        assert 'sharpe_ratio' in metrics
        assert 'max_drawdown' in metrics
        assert 'win_rate' in metrics
    
    def test_normality_test(self):
        """Test normality testing."""
        try:
            from core_engine.strategy_validator import StatisticalValidator, SCIPY_AVAILABLE
        except ImportError:
            pytest.skip("scipy not available")
            return
        
        if not SCIPY_AVAILABLE:
            pytest.skip("scipy not available")
            return
        
        validator = StatisticalValidator(confidence_level=0.95)
        returns = pd.Series(np.random.randn(100))
        
        results = validator.test_normality(returns)
        
        assert 'shapiro_wilk' in results or 'jarque_bera' in results
    
    def test_strategy_validation(self):
        """Test full strategy validation."""
        try:
            from core_engine.strategy_validator import StrategyValidator
        except ImportError:
            pytest.skip("scipy not available")
            return
        
        validator = StrategyValidator(confidence_level=0.95)
        returns = pd.Series(np.random.randn(100) * 0.01)
        
        report = validator.validate_strategy('test_strategy', returns)
        
        assert report.strategy_name == 'test_strategy'
        assert isinstance(report.is_valid, bool)
        assert len(report.recommendations) > 0


class TestPaperTradingEngine:
    """Test paper trading engine."""
    
    def test_initialization(self):
        """Test paper trading engine initialization."""
        from core_engine.paper_trading_engine import PaperTradingEngine
        
        config = {
            'initial_balance': 100000,
            'maker_fee_bps': 0.02,
            'taker_fee_bps': 0.04
        }
        
        engine = PaperTradingEngine(config)
        
        assert engine.initial_balance == 100000
        assert engine.current_balance == 100000
    
    def test_account_summary(self):
        """Test account summary."""
        from core_engine.paper_trading_engine import PaperTradingEngine
        
        config = {'initial_balance': 100000}
        engine = PaperTradingEngine(config)
        
        summary = engine.get_account_summary()
        
        assert summary.initial_balance == 100000
        assert summary.current_balance == 100000


class TestPerformanceAttribution:
    """Test performance attribution."""
    
    def test_attribution_calculation(self):
        """Test performance attribution calculation."""
        from core_engine.performance_attribution import PerformanceAttributor
        
        attributor = PerformanceAttributor()
        
        strategy_returns = pd.Series(np.random.randn(100) * 0.01)
        benchmark_returns = pd.Series(np.random.randn(100) * 0.01)
        
        report = attributor.calculate_attribution(strategy_returns, benchmark_returns)
        
        assert report.total_return is not None
        assert report.active_return is not None
        assert 'selection' in report.attribution or 'timing' in report.attribution
    
    def test_strategy_comparison(self):
        """Test strategy comparison."""
        from core_engine.performance_attribution import StrategyComparator
        
        comparator = StrategyComparator()
        
        returns_dict = {
            'strategy1': pd.Series(np.random.randn(100) * 0.01),
            'strategy2': pd.Series(np.random.randn(100) * 0.01)
        }
        
        comparison = comparator.compare_strategies(returns_dict)
        
        assert len(comparison.strategies) == 2
        assert 'sharpe_ratio' in comparison.metrics['strategy1']


class TestParameterOptimization:
    """Test parameter optimization."""
    
    def test_grid_search(self):
        """Test grid search optimization."""
        from core_engine.parameter_optimization import ParameterOptimizer, ParameterRange, OptimizationMethod
        
        def simple_objective(params):
            # Simple quadratic function for testing
            return -((params['x'] - 5) ** 2 + (params['y'] - 3) ** 2)
        
        optimizer = ParameterOptimizer(OptimizationMethod.GRID_SEARCH)
        
        parameter_ranges = [
            ParameterRange('x', 0, 10, 1),
            ParameterRange('y', 0, 10, 1)
        ]
        
        result = optimizer.optimize(simple_objective, parameter_ranges, n_iterations=10)
        
        assert result.best_parameters is not None
        assert result.best_score is not None
    
    def test_sensitivity_analysis(self):
        """Test sensitivity analysis."""
        from core_engine.parameter_optimization import SensitivityAnalyzer, ParameterRange
        
        def simple_objective(params):
            return -((params['x'] - 5) ** 2)
        
        analyzer = SensitivityAnalyzer()
        
        base_params = {'x': 5.0}
        parameter_ranges = [ParameterRange('x', 0, 10, 0.5)]
        
        result = analyzer.analyze_sensitivity(simple_objective, base_params, parameter_ranges)
        
        assert result.parameter_importance is not None
        assert len(result.recommendations) > 0


class TestHistoricalReplay:
    """Test historical replay engine."""
    
    def test_initialization(self):
        """Test replay engine initialization."""
        from core_engine.historical_replay import HistoricalReplayEngine
        
        config = {
            'initial_balance': 100000,
            'maker_fee_bps': 0.02
        }
        
        engine = HistoricalReplayEngine(config)
        
        assert engine.initial_balance == 100000
        assert len(engine.positions) == 0
    
    def test_state_reset(self):
        """Test state reset."""
        from core_engine.historical_replay import HistoricalReplayEngine
        
        config = {'initial_balance': 100000}
        engine = HistoricalReplayEngine(config)
        
        engine._reset_state()
        
        assert engine.current_balance == 100000
        assert len(engine.positions) == 0


class TestMonitoringSystem:
    """Test monitoring system."""
    
    def test_metrics_collector(self):
        """Test metrics collection."""
        from core_engine.monitoring_system import MetricsCollector, MetricType
        
        collector = MetricsCollector()
        
        collector.record_metric('test_metric', 100.0, MetricType.GAUGE)
        
        stats = collector.get_metric_stats('test_metric')
        
        assert stats['count'] == 1
        assert stats['mean'] == 100.0
    
    def test_alert_manager(self):
        """Test alert manager."""
        from core_engine.monitoring_system import AlertManager, AlertSeverity, AlertChannel
        
        config = {'alerts': {}}
        manager = AlertManager(config)
        
        rule = {
            'name': 'Test Alert',
            'metric': 'test_metric',
            'condition': 'greater_than',
            'threshold': 50,
            'severity': 'warning',
            'channels': [AlertChannel.LOG]
        }
        
        manager.add_alert_rule(rule)
        
        assert len(manager.alert_rules) == 1
    
    def test_health_monitor(self):
        """Test health monitoring."""
        from core_engine.monitoring_system import HealthMonitor
        
        monitor = HealthMonitor()
        
        async def dummy_check():
            return {'status': 'healthy', 'message': 'OK'}
        
        monitor.register_health_check('test_component', dummy_check)
        
        assert 'test_component' in monitor.health_checks


# Run tests
if __name__ == '__main__':
    pytest.main([__file__, '-v'])