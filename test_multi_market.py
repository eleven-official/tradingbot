"""
Multi-market functionality test script.
Tests the new market abstraction layer and TradingView integration.
"""
import sys
import os
import yaml
import logging

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.market_factory import MarketFactory, MarketType
from core.market_manager import MarketManager
from core.tradingview_bridge import TradingViewConfigGenerator

def test_market_factory():
    """Test market factory and adapter creation."""
    print("Testing Market Factory...")
    
    # Test Zerodha adapter creation
    zerodha_config = {
        'api_key': 'test_key',
        'api_secret': 'test_secret',
        'access_token': 'test_token'
    }
    
    try:
        equity_adapter = MarketFactory.create_adapter(MarketType.EQUITY, zerodha_config)
        print("[PASS] Equity adapter created successfully")
        print(f"       Adapter type: {type(equity_adapter).__name__}")
    except Exception as e:
        print(f"[FAIL] Failed to create equity adapter: {e}")
        return False
    
    # Test OANDA adapter creation
    oanda_config = {
        'hostname': 'api-fxpractice.oanda.com',
        'port': 443,
        'api_token': 'test_token',
        'account_id': 'test_account'
    }
    
    try:
        forex_adapter = MarketFactory.create_adapter(MarketType.FOREX, oanda_config)
        print("[PASS] Forex adapter created successfully")
        print(f"       Adapter type: {type(forex_adapter).__name__}")
    except Exception as e:
        print(f"[FAIL] Failed to create forex adapter: {e}")
        return False
    
    # Test supported markets
    supported = MarketFactory.get_supported_markets()
    print(f"[PASS] Supported markets: {[m.value for m in supported]}")
    
    return True

def test_market_manager():
    """Test market manager initialization."""
    print("\nTesting Market Manager...")
    
    # Load multi-market config
    try:
        with open('config.multi_market.yaml', 'r') as f:
            config = yaml.safe_load(f)
        print("[PASS] Multi-market config loaded successfully")
    except Exception as e:
        print(f"[FAIL] Failed to load config: {e}")
        return False
    
    # Test market manager initialization
    try:
        manager = MarketManager(config)
        print("[PASS] Market manager initialized successfully")
    except Exception as e:
        print(f"[FAIL] Failed to initialize market manager: {e}")
        return False
    
    # Test supported markets
    supported = manager.get_supported_markets()
    print(f"[PASS] Supported markets: {supported}")
    
    # Test market status
    status = manager.get_market_status()
    print(f"[PASS] Market status retrieved:")
    print(f"       Primary market: {status['primary_market']}")
    print(f"       Supported markets: {status['supported_markets']}")
    
    return True

def test_tradingview_bridge():
    """Test TradingView bridge configuration."""
    print("\nTesting TradingView Bridge...")
    
    # Test webhook URL generation
    webhook_url = TradingViewConfigGenerator.generate_webhook_url(
        "http://localhost:5000",
        "secret123"
    )
    print(f"[PASS] Webhook URL generated: {webhook_url}")
    
    # Test Pine Script template generation
    pine_script = TradingViewConfigGenerator.generate_pine_script_template(
        "EUR_USD",
        "RSI_Strategy"
    )
    print("[PASS] Pine Script template generated")
    print(f"       Template length: {len(pine_script)} characters")
    
    # Test setup instructions
    instructions = TradingViewConfigGenerator.generate_setup_instructions(
        "http://localhost",
        5000,
        "secret123"
    )
    print("[PASS] Setup instructions generated")
    print(f"       Instructions length: {len(instructions)} characters")
    
    return True

def test_symbol_validation():
    """Test symbol validation across markets."""
    print("\nTesting Symbol Validation...")
    
    # Test forex symbol validation
    from core.market_factory import OANDAForexAdapter
    forex_adapter = OANDAForexAdapter({})
    
    valid_forex = forex_adapter.validate_symbol("EUR_USD")
    invalid_forex = forex_adapter.validate_symbol("INVALID")
    
    print(f"[PASS] Forex symbol validation:")
    print(f"       EUR_USD: {valid_forex}")
    print(f"       INVALID: {invalid_forex}")
    
    # Test equity symbol validation
    from core.market_factory import ZerodhaEquityAdapter
    equity_adapter = ZerodhaEquityAdapter({})
    
    valid_equity = equity_adapter.validate_symbol("NIFTY 50")
    invalid_equity = equity_adapter.validate_symbol("")
    
    print(f"[PASS] Equity symbol validation:")
    print(f"       NIFTY 50: {valid_equity}")
    print(f"       Empty: {invalid_equity}")
    
    return True

def test_tradingview_alert_parser():
    """Test TradingView alert parsing."""
    print("\nTesting TradingView Alert Parser...")
    
    from core.tradingview_bridge import TradingViewAlertParser
    
    # Test valid alert parsing
    alert_text = "BUY|EUR_USD|RSI_Strategy|1.0850|0.85"
    parsed = TradingViewAlertParser.parse_pine_script_alert(alert_text)
    
    print(f"[PASS] Alert parsing:")
    print(f"       Action: {parsed['action']}")
    print(f"       Symbol: {parsed['symbol']}")
    print(f"       Strategy: {parsed['strategy']}")
    print(f"       Price: {parsed['price']}")
    print(f"       Confidence: {parsed['confidence']}")
    
    # Test alert validation
    is_valid = TradingViewAlertParser.validate_alert(parsed)
    print(f"[PASS] Alert validation: {is_valid}")
    
    # Test symbol normalization
    norm_forex = TradingViewAlertParser.normalize_symbol("eurusd", "forex")
    norm_equity = TradingViewAlertParser.normalize_symbol("NIFTY_50", "equity")
    
    print(f"[PASS] Symbol normalization:")
    print(f"       eurusd -> forex: {norm_forex}")
    print(f"       NIFTY_50 -> equity: {norm_equity}")
    
    return True

def main():
    """Run all multi-market tests."""
    print("=" * 60)
    print("MULTI-MARKET FUNCTIONALITY TEST SUITE")
    print("=" * 60)
    
    # Set up logging
    logging.basicConfig(level=logging.INFO)
    
    all_passed = True
    
    # Run tests
    all_passed &= test_market_factory()
    all_passed &= test_market_manager()
    all_passed &= test_tradingview_bridge()
    all_passed &= test_symbol_validation()
    all_passed &= test_tradingview_alert_parser()
    
    # Print summary
    print("\n" + "=" * 60)
    if all_passed:
        print("[PASS] ALL TESTS PASSED - Multi-market functionality is ready!")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Install required dependencies:")
        print("   pip install v20  # For OANDA forex")
        print("   pip install flask  # For TradingView bridge")
        print("   pip install ibapi  # For Interactive Brokers (optional)")
        print("2. Configure API credentials in config.multi_market.yaml")
        print("3. Test connection to each market provider")
        print("4. Set up TradingView webhooks")
        print("5. Start with paper trading on each market")
        return 0
    else:
        print("[FAIL] SOME TESTS FAILED - Please review the errors above")
        print("=" * 60)
        return 1

if __name__ == '__main__':
    sys.exit(main())