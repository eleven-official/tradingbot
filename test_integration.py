"""
Integration Test Script
Tests all newly integrated features with historical data
"""

import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Force UTF-8 encoding for Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Import integrated modules
from core.enhanced_indicators import EnhancedIndicators
from core.portfolio_optimizer import PortfolioOptimizer
from core.risk_analytics import compute_comprehensive_risk_analysis
from core.multi_agent_system import MultiAgentOrchestrator
from core.enhanced_backtester import EnhancedBacktester


def test_enhanced_indicators():
    """Test enhanced technical indicators."""
    print("\n" + "="*60)
    print("Testing Enhanced Indicators")
    print("="*60)
    
    # Create sample OHLCV data
    dates = pd.date_range(start='2024-01-01', periods=100, freq='D')
    np.random.seed(42)
    
    close = 100 + np.cumsum(np.random.randn(100) * 0.5)
    high = close + np.random.rand(100) * 2
    low = close - np.random.rand(100) * 2
    open_price = close + np.random.randn(100) * 0.5
    volume = np.random.randint(1000000, 10000000, 100)
    
    df = pd.DataFrame({
        'date': dates,
        'open': open_price,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume
    })
    
    indicators = EnhancedIndicators()
    
    # Test individual indicators
    print("Testing SMA: ", end="")
    sma = indicators.calculate_sma(df, 20)
    print(f"[OK] Last value: {sma.iloc[-1]:.2f}")
    
    print("Testing EMA: ", end="")
    ema = indicators.calculate_ema(df, 12)
    print(f"[OK] Last value: {ema.iloc[-1]:.2f}")
    
    print("Testing RSI: ", end="")
    rsi = indicators.calculate_rsi(df, 14)
    print(f"[OK] Last value: {rsi.iloc[-1]:.2f}")
    
    print("Testing MACD: ", end="")
    macd = indicators.calculate_macd(df)
    print(f"[OK] MACD: {macd['macd'].iloc[-1]:.4f}")
    
    print("Testing Bollinger Bands: ", end="")
    bb = indicators.calculate_bollinger_bands(df)
    print(f"[OK] Upper: {bb['upper'].iloc[-1]:.2f}, Lower: {bb['lower'].iloc[-1]:.2f}")
    
    print("Testing ATR: ", end="")
    atr = indicators.calculate_atr(df)
    print(f"[OK] Last value: {atr.iloc[-1]:.2f}")
    
    # Test all indicators at once
    print("Testing calculate_all_indicators: ", end="")
    all_indicators = indicators.calculate_all_indicators(df, include_all=False)
    print(f"[OK] Generated {len(all_indicators.columns)} indicator columns")
    
    # Test signal generation
    print("Testing get_indicator_signals: ", end="")
    signals = indicators.get_indicator_signals(df)
    print(f"[OK] Generated {len(signals)} signals")
    for key, value in signals.items():
        print(f"  - {key}: {value}")
    
    print("\n[PASS] Enhanced Indicators Test PASSED")
    return True


def test_portfolio_optimizer():
    """Test portfolio optimization strategies."""
    print("\n" + "="*60)
    print("Testing Portfolio Optimizer")
    print("="*60)
    
    # Create sample returns data
    np.random.seed(42)
    dates = pd.date_range(start='2024-01-01', periods=252, freq='D')
    
    symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN']
    returns = pd.DataFrame(
        np.random.randn(252, 4) * 0.02,
        index=dates,
        columns=list(symbols)
    )
    
    optimizer = PortfolioOptimizer()
    
    # Test each optimization method
    methods = ['equal_weight', 'inverse_volatility', 'risk_parity', 'mean_variance', 'max_diversification']
    
    for method in methods:
        print(f"Testing {method}: ", end="")
        try:
            weights = optimizer.optimize(returns, method=method)
            print(f"[OK] Weights: {[f'{w:.3f}' for w in weights]}")
        except Exception as e:
            print(f"[FAIL] Error: {e}")
            return False
    
    # Test with constraints
    print("Testing with constraints: ", end="")
    try:
        weights = optimizer.optimize_with_constraints(
            returns,
            method='risk_parity',
            min_weight=0.05,
            max_weight=0.5
        )
        print(f"[OK] Weights: {[f'{w:.3f}' for w in weights]}")
    except Exception as e:
        print(f"[FAIL] Error: {e}")
        return False
    
    print("\n[PASS] Portfolio Optimizer Test PASSED")
    return True


def test_risk_analytics():
    """Test risk analytics module."""
    print("\n" + "="*60)
    print("Testing Risk Analytics")
    print("="*60)
    
    # Create sample data
    np.random.seed(42)
    dates = pd.date_range(start='2024-01-01', periods=100, freq='D')
    
    symbols = ['BTC', 'ETH', 'SOL']
    price_history = {}
    positions = {}
    
    for sym in symbols:
        close = 100 + np.cumsum(np.random.randn(100) * 2)
        df = pd.DataFrame({
            'date': dates,
            'open': close + np.random.randn(100) * 0.5,
            'high': close + np.random.rand(100) * 2,
            'low': close - np.random.rand(100) * 2,
            'close': close,
            'volume': np.random.randint(1000000, 10000000, 100)
        })
        price_history[sym] = df
        positions[sym] = 10  # 10 units of each
    
    print("Testing compute_comprehensive_risk_analysis: ", end="")
    try:
        risk_analysis = compute_comprehensive_risk_analysis(positions, price_history)
        print("[OK]")
        
        # Print key metrics
        print(f"  - Portfolio Value: ${risk_analysis['portfolio_value']:.2f}")
        print(f"  - Symbols: {risk_analysis['symbols']}")
        print(f"  - Weights: {risk_analysis['weights']}")
        print(f"  - Annualized Vol: {risk_analysis['volatility']['annualized_vol']:.2%}")
        print(f"  - Max Drawdown: {risk_analysis['drawdown']['max_drawdown']:.2%}")
        print(f"  - Diversification Ratio: {risk_analysis['diversification']['diversification_ratio']:.3f}")
        
    except Exception as e:
        print(f"[FAIL] Error: {e}")
        return False
    
    print("\n[PASS] Risk Analytics Test PASSED")
    return True


def test_multi_agent_system():
    """Test multi-agent trading system."""
    print("\n" + "="*60)
    print("Testing Multi-Agent System")
    print("="*60)
    
    # Create sample data
    np.random.seed(42)
    dates = pd.date_range(start='2024-01-01', periods=100, freq='D')
    
    close_prices = 100 + np.cumsum(np.random.randn(100) * 0.5)
    price_data = pd.DataFrame({
        'date': dates,
        'open': close_prices + np.random.randn(100) * 0.5,
        'high': close_prices + np.random.rand(100) * 2,
        'low': close_prices - np.random.rand(100) * 2,
        'close': close_prices,
        'volume': np.random.randint(1000000, 10000000, 100)
    })
    
    portfolio_state = {
        'total_value': 25000,
        'total_exposure': 0.5,
        'cash': 12500
    }
    
    orchestrator = MultiAgentOrchestrator()
    
    print("Testing run_analysis: ", end="")
    try:
        analysis = orchestrator.run_analysis(
            symbol='BTC/USD',
            price_data=price_data,
            portfolio_state=portfolio_state,
            current_price=close_prices[-1]
        )
        print("[OK]")
        
        print(f"  - Recommendation: {analysis['recommendation']}")
        print(f"  - Confidence: {analysis['confidence']:.2%}")
        print(f"  - Rationale: {analysis['rationale']}")
        print(f"  - Agents run: {list(analysis['agent_outputs'].keys())}")
        
    except Exception as e:
        print(f"[FAIL] Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n[PASS] Multi-Agent System Test PASSED")
    return True


def test_enhanced_backtester():
    """Test enhanced backtester with historical data."""
    print("\n" + "="*60)
    print("Testing Enhanced Backtester")
    print("="*60)
    
    # Create sample historical data (simulating 1 year)
    np.random.seed(42)
    dates = pd.date_range(start='2023-01-01', end='2023-12-31', freq='D')
    
    close = 100 + np.cumsum(np.random.randn(len(dates)) * 0.5)
    data = pd.DataFrame({
        'date': dates,
        'open': close + np.random.randn(len(dates)) * 0.5,
        'high': close + np.random.rand(len(dates)) * 2,
        'low': close - np.random.rand(len(dates)) * 2,
        'close': close,
        'volume': np.random.randint(1000000, 10000000, len(dates))
    })
    
    backtester = EnhancedBacktester(initial_capital=25000)
    
    # Define a simple strategy function
    def simple_strategy(df, **kwargs):
        """Simple moving average crossover strategy."""
        sma_short = df['close'].rolling(20).mean()
        sma_long = df['close'].rolling(50).mean()
        
        signals = pd.Series(0, index=df.index)
        signals[sma_short > sma_long] = 1  # Buy
        signals[sma_short < sma_long] = -1  # Sell
        
        return signals
    
    print("Testing run_backtest: ", end="")
    try:
        result = backtester.run_backtest(
            data=data,
            strategy_func=simple_strategy,
            strategy_params={'name': 'SMA_Crossover'},
            symbol='TEST'
        )
        print("[OK]")
        
        print(f"  - Total Trades: {result.total_trades}")
        print(f"  - Win Rate: {result.win_rate:.2%}")
        print(f"  - Total Return: {result.total_return:.2%}")
        print(f"  - Max Drawdown: {result.max_drawdown:.2%}")
        print(f"  - Sharpe Ratio: {result.sharpe_ratio:.2f}")
        print(f"  - Profit Factor: {result.profit_factor:.2f}")
        
    except Exception as e:
        print(f"[FAIL] Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test walk-forward analysis
    print("Testing walk_forward_analysis: ", end="")
    try:
        wf_results = backtester.run_walk_forward_analysis(
            data=data,
            strategy_func=simple_strategy,
            strategy_params={'name': 'SMA_Crossover'},
            in_sample_months=6,
            out_sample_months=2
        )
        print(f"[OK] {len(wf_results)} walk-forward windows")
        
        if wf_results:
            avg_win_rate = np.mean([r.win_rate for r in wf_results])
            avg_return = np.mean([r.annualized_return for r in wf_results])
            print(f"  - Average Win Rate: {avg_win_rate:.2%}")
            print(f"  - Average Annual Return: {avg_return:.2%}")
        
    except Exception as e:
        print(f"[FAIL] Error: {e}")
        return False
    
    print("\n[PASS] Enhanced Backtester Test PASSED")
    return True


def run_all_tests():
    """Run all integration tests."""
    print("\n" + "="*60)
    print("LOKI INTEGRATION TEST SUITE")
    print("="*60)
    print("Testing all newly integrated features from:")
    print("- Vibe-Trading (Risk Analytics, Portfolio Optimizers)")
    print("- FinceptTerminal (Enhanced Indicators)")
    print("- AutoHedge (Multi-Agent System)")
    print("="*60)
    
    results = []
    
    # Run tests
    results.append(("Enhanced Indicators", test_enhanced_indicators()))
    results.append(("Portfolio Optimizer", test_portfolio_optimizer()))
    results.append(("Risk Analytics", test_risk_analytics()))
    results.append(("Multi-Agent System", test_multi_agent_system()))
    results.append(("Enhanced Backtester", test_enhanced_backtester()))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{name}: {status}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n[SUCCESS] ALL TESTS PASSED! Integration successful.")
        return True
    else:
        print(f"\n[WARNING] {total - passed} test(s) failed. Please review errors above.")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
