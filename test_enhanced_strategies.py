#!/usr/bin/env python3
"""
Test script for enhanced strategy_factory.py
Tests all new features, error handling, and backward compatibility.
"""

import sys
import os
import pandas as pd
import numpy as np
import datetime
import logging
from unittest.mock import Mock, MagicMock

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def create_mock_data(periods=100):
    """Create mock market data for testing."""
    dates = pd.date_range(start='2024-01-01 09:15:00', periods=periods, freq='5min')
    
    # Generate realistic OHLCV data
    np.random.seed(42)
    base_price = 100.0
    prices = []
    volumes = []
    
    for i in range(periods):
        # Random walk with slight upward bias
        change = np.random.normal(0.001, 0.01)  # 0.1% mean, 1% volatility
        base_price *= (1 + change)
        
        # Generate OHLC around close price
        high = base_price * (1 + abs(np.random.normal(0, 0.005)))
        low = base_price * (1 - abs(np.random.normal(0, 0.005)))
        open_price = base_price * (1 + np.random.normal(0, 0.002))
        
        prices.append([open_price, high, low, base_price])
        volumes.append(np.random.randint(1000, 10000))
    
    df = pd.DataFrame(prices, columns=['open', 'high', 'low', 'close'], index=dates)
    df['volume'] = volumes
    
    # Add basic indicators
    df['rsi'] = calculate_rsi_simple(df['close'], 14)
    df['ema_9'] = df['close'].ewm(span=9).mean()
    df['ema_15'] = df['close'].ewm(span=15).mean()
    df['ema_21'] = df['close'].ewm(span=21).mean()
    df['ema_50'] = df['close'].ewm(span=50).mean()
    df['volume_ma'] = df['volume'].rolling(window=20).mean()
    df['atr'] = calculate_atr_simple(df, 14)
    df['vwap'] = calculate_vwap_simple(df)
    
    return df

def calculate_rsi_simple(close_prices, period=14):
    """Simple RSI calculation for testing."""
    delta = close_prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_atr_simple(df, period=14):
    """Simple ATR calculation for testing."""
    high_low = df['high'] - df['low']
    high_close = abs(df['high'] - df['close'].shift())
    low_close = abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def calculate_vwap_simple(df):
    """Simple VWAP calculation for testing."""
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    return (typical_price * df['volume']).cumsum() / df['volume'].cumsum()

def create_mock_config():
    """Create mock configuration for testing."""
    return {
        'trading_flags': {
            'max_signals_per_hour': 3,
            'min_confidence_threshold': 0.6,
            'log_hold_reasons': True,
            'ema_cross_lookback': 5,
            'orb_minutes': 30
        },
        'risk_management': {
            'max_position_size': 10000,
            'max_daily_loss': 1000,
            'default_stop_loss_pct': 0.02
        }
    }

def test_strategy_imports():
    """Test if strategy_factory imports correctly."""
    try:
        from strategy_factory import (
            StrategySignal, BaseStrategy, Gemini_Default_Strategy,
            QuantumMomentumStrategy, NeuralNetworkStrategy, 
            AdaptiveArbitrageStrategy, get_strategy, get_available_strategies
        )
        logger.info("✅ All strategy imports successful")
        return True
    except ImportError as e:
        logger.error(f"❌ Import error: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error during import: {e}")
        return False

def test_strategy_signal_class():
    """Test StrategySignal dataclass."""
    try:
        from strategy_factory import StrategySignal
        
        signal = StrategySignal(
            action='BUY',
            confidence=0.85,
            reasons=['Test reason'],
            timestamp=datetime.datetime.now(),
            price=100.0,
            stop_loss=98.0,
            target=104.0,
            risk_reward_ratio=2.0
        )
        
        assert signal.action == 'BUY'
        assert signal.confidence == 0.85
        assert len(signal.reasons) == 1
        
        logger.info("✅ StrategySignal class test passed")
        return True
    except Exception as e:
        logger.error(f"❌ StrategySignal test failed: {e}")
        return False

def test_enhanced_strategies():
    """Test enhanced strategies with mock data."""
    try:
        from strategy_factory import get_strategy
        
        mock_kite = Mock()
        config = create_mock_config()
        mock_data = create_mock_data(100)
        
        # Test new enhanced strategies
        strategies_to_test = [
            'Gemini_Default',
            'Quantum_Momentum', 
            'Neural_Network',
            'Adaptive_Arbitrage'
        ]
        
        results = {}
        
        for strategy_name in strategies_to_test:
            try:
                logger.info(f"Testing {strategy_name} strategy...")
                
                # Test enhanced mode
                strategy = get_strategy(strategy_name, mock_kite, config, enhanced=True)
                
                # Generate test signal
                signal = strategy.generate_signals(
                    mock_data, 
                    'Bullish', 
                    index=len(mock_data)-1,
                    cpr_pivots={'tc': 101, 'bc': 99, 'pivot': 100},
                    vix_conditions=set()
                )
                
                # Validate signal structure
                assert hasattr(signal, 'action')
                assert hasattr(signal, 'confidence')
                assert hasattr(signal, 'reasons')
                assert signal.action in ['BUY', 'SELL', 'HOLD']
                assert 0.0 <= signal.confidence <= 1.0
                
                results[strategy_name] = {
                    'status': 'PASS',
                    'signal': signal.action,
                    'confidence': signal.confidence,
                    'reasons_count': len(signal.reasons)
                }
                
                logger.info(f"✅ {strategy_name}: {signal.action} (confidence: {signal.confidence:.1%})")
                
            except Exception as e:
                results[strategy_name] = {
                    'status': 'FAIL',
                    'error': str(e)
                }
                logger.error(f"❌ {strategy_name} failed: {e}")
        
        return results
        
    except Exception as e:
        logger.error(f"❌ Enhanced strategies test failed: {e}")
        return {}

def test_backward_compatibility():
    """Test backward compatibility with legacy code."""
    try:
        from strategy_factory import get_strategy
        
        mock_kite = Mock()
        config = create_mock_config()
        mock_data = create_mock_data(100)
        
        # Test legacy mode (should return simple strings)
        strategy = get_strategy('Gemini_Default', mock_kite, config, enhanced=False)
        signal = strategy.generate_signals(
            mock_data,
            'Bullish',
            cpr_pivots={'tc': 101, 'bc': 99, 'pivot': 100}
        )
        
        # Should return simple string in legacy mode
        assert isinstance(signal, str)
        assert signal in ['BUY', 'SELL', 'HOLD']
        
        logger.info(f"✅ Backward compatibility test passed: {signal}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Backward compatibility test failed: {e}")
        return False

def test_error_handling():
    """Test error handling and edge cases."""
    try:
        from strategy_factory import get_strategy
        
        mock_kite = Mock()
        config = create_mock_config()
        
        # Test invalid strategy name
        try:
            strategy = get_strategy('NonExistent_Strategy', mock_kite, config)
            logger.error("❌ Should have raised ValueError for invalid strategy")
            return False
        except ValueError:
            logger.info("✅ Correctly handled invalid strategy name")
        
        # Test with insufficient data
        small_data = create_mock_data(5)  # Only 5 periods
        strategy = get_strategy('Neural_Network', mock_kite, config, enhanced=True)
        
        signal = strategy.generate_signals(small_data, 'Bullish')
        assert signal.action == 'HOLD'
        assert 'Insufficient data' in ' '.join(signal.reasons)
        
        logger.info("✅ Error handling tests passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error handling test failed: {e}")
        return False

def test_performance_metrics():
    """Test performance tracking functionality."""
    try:
        from strategy_factory import get_strategy
        
        mock_kite = Mock()
        config = create_mock_config()
        mock_data = create_mock_data(100)
        
        strategy = get_strategy('Gemini_Default', mock_kite, config, enhanced=True)
        
        # Generate multiple signals to test metrics
        for i in range(3):
            signal = strategy.generate_signals(
                mock_data,
                'Bullish',
                cpr_pivots={'tc': 101, 'bc': 99, 'pivot': 100}
            )
        
        # Check if performance metrics are being tracked
        metrics = strategy._performance_metrics
        assert 'signals_generated' in metrics
        assert 'avg_confidence' in metrics
        assert 'last_updated' in metrics
        
        logger.info("✅ Performance metrics test passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ Performance metrics test failed: {e}")
        return False

def run_all_tests():
    """Run all test suites."""
    logger.info("🚀 Starting Enhanced Strategy Factory Tests...")
    logger.info("=" * 60)
    
    test_results = {
        'imports': test_strategy_imports(),
        'strategy_signal': test_strategy_signal_class(),
        'enhanced_strategies': test_enhanced_strategies(),
        'backward_compatibility': test_backward_compatibility(),
        'error_handling': test_error_handling(),
        'performance_metrics': test_performance_metrics()
    }
    
    logger.info("=" * 60)
    logger.info("📊 TEST RESULTS SUMMARY:")
    
    passed = 0
    failed = 0
    
    for test_name, result in test_results.items():
        if test_name == 'enhanced_strategies':
            # Special handling for strategy tests
            if isinstance(result, dict):
                strategy_passed = sum(1 for r in result.values() if r.get('status') == 'PASS')
                strategy_failed = len(result) - strategy_passed
                logger.info(f"   {test_name}: {strategy_passed}/{len(result)} strategies passed")
                passed += strategy_passed
                failed += strategy_failed
            continue
            
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"   {test_name}: {status}")
        if result:
            passed += 1
        else:
            failed += 1
    
    total_tests = passed + failed
    success_rate = (passed / total_tests * 100) if total_tests > 0 else 0
    
    logger.info("=" * 60)
    logger.info(f"🎯 OVERALL RESULTS: {passed}/{total_tests} tests passed ({success_rate:.1f}%)")
    
    if failed == 0:
        logger.info("🎉 ALL TESTS PASSED! Strategy factory is ready for production.")
    else:
        logger.warning(f"⚠️  {failed} test(s) failed. Review and fix issues before deployment.")
    
    return test_results

if __name__ == "__main__":
    # Add current directory to path for imports
    sys.path.insert(0, os.getcwd())
    
    try:
        results = run_all_tests()
        
        # Exit with proper code
        failed_tests = sum(1 for r in results.values() 
                          if (isinstance(r, bool) and not r) or 
                             (isinstance(r, dict) and any(s.get('status') == 'FAIL' for s in r.values())))
        
        sys.exit(0 if failed_tests == 0 else 1)
        
    except Exception as e:
        logger.error(f"💥 Test suite crashed: {e}")
        sys.exit(2)