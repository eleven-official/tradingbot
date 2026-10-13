"""
Paper Trading Mode Test Script
Tests that the bot can be properly initialized in paper trading mode.
"""
import sys
import os
import yaml
import logging

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.config_validator import ConfigValidator, ConfigurationError
from core.risk_controller import RiskController
from core.state_manager import StateManager
from core.metrics import MetricsCollector

def test_paper_trading_config():
    """Test paper trading configuration validation."""
    print("Testing Paper Trading Configuration...")
    
    # Load paper trading config
    try:
        with open('config.paper_trading.yaml', 'r') as f:
            config = yaml.safe_load(f)
        print("[PASS] Paper trading config loaded successfully")
    except Exception as e:
        print(f"[FAIL] Failed to load config: {e}")
        return False
    
    # Validate configuration
    try:
        validator = ConfigValidator(config)
        validated_config = validator.validate()
        print("[PASS] Configuration validation passed")
    except ConfigurationError as e:
        print(f"[FAIL] Configuration validation failed: {e}")
        return False
    
    # Check paper trading mode is enabled
    if not validator.get_paper_trading_mode():
        print("[FAIL] Paper trading mode is not enabled")
        return False
    print("[PASS] Paper trading mode is enabled")
    
    # Check risk parameters are conservative
    risk_percent = config['trading_flags']['risk_per_trade_percent']
    if risk_percent > 2.0:
        print(f"[FAIL] Risk per trade ({risk_percent}%) is too high for paper trading")
        return False
    print(f"[PASS] Risk per trade is conservative ({risk_percent}%)")
    
    # Check daily loss limit accommodates risk tiers
    max_daily_loss = config['risk_management']['max_daily_loss_percent']
    max_risk_tier = max([tier['risk_pct'] for tier in config['risk_tiers']])
    if max_risk_tier > max_daily_loss / 2:
        print(f"[WARN] Risk tier ({max_risk_tier}%) exceeds daily loss/2 ({max_daily_loss/2:.1f}%)")
    else:
        print(f"[PASS] Risk tiers are coherent with daily loss limit")
    
    # Check max trades per day is limited
    max_trades = config['trading_flags']['max_trades_per_day']
    if max_trades > 5:
        print(f"[FAIL] Max trades per day ({max_trades}) is too high for paper trading")
        return False
    print(f"[PASS] Max trades per day is limited ({max_trades})")
    
    # Check daily loss limit is enabled
    if not config['risk_management']['enable_daily_loss_limit']:
        print("[FAIL] Daily loss limit is not enabled")
        return False
    print("[PASS] Daily loss limit is enabled")
    
    return True

def test_component_initialization():
    """Test that core components can be initialized."""
    print("\nTesting Component Initialization...")
    
    # Load config
    with open('config.paper_trading.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    # Test RiskController
    try:
        risk_controller = RiskController(config)
        print("[PASS] RiskController initialized successfully")
    except Exception as e:
        print(f"[FAIL] RiskController initialization failed: {e}")
        return False
    
    # Test StateManager
    try:
        state_manager = StateManager(config)
        print("[PASS] StateManager initialized successfully")
    except Exception as e:
        print(f"[FAIL] StateManager initialization failed: {e}")
        return False
    
    # Test MetricsCollector
    try:
        metrics = MetricsCollector(config)
        print("[PASS] MetricsCollector initialized successfully")
    except Exception as e:
        print(f"[FAIL] MetricsCollector initialization failed: {e}")
        return False
    
    return True

def test_risk_calculations():
    """Test risk calculation logic."""
    print("\nTesting Risk Calculations...")
    
    # Load config
    with open('config.paper_trading.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    risk_controller = RiskController(config)
    
    # Test position size calculation
    capital = 100000
    option_price = 100
    
    try:
        lots = risk_controller.calculate_position_size(capital, option_price)
        print(f"[PASS] Position size calculated: {lots} lots for Rs.{capital:,} capital")
        
        # Verify position size is reasonable
        if lots <= 0 or lots > 1000:
            print(f"[FAIL] Position size {lots} is unreasonable")
            return False
        print("[PASS] Position size is reasonable")
    except Exception as e:
        print(f"[FAIL] Position size calculation failed: {e}")
        return False
    
    # Test risk tier selection
    try:
        risk_small = risk_controller.get_risk_per_trade(50000)
        risk_medium = risk_controller.get_risk_per_trade(200000)
        risk_large = risk_controller.get_risk_per_trade(500000)
        
        print(f"[PASS] Risk tiers: Small={risk_small}%, Medium={risk_medium}%, Large={risk_large}%")
        
        # Verify risk decreases with capital
        if risk_small <= risk_medium or risk_medium <= risk_large:
            print("[FAIL] Risk tiers don't decrease with capital")
            return False
        print("[PASS] Risk tiers properly decrease with capital")
    except Exception as e:
        print(f"[FAIL] Risk tier calculation failed: {e}")
        return False
    
    return True

def test_metrics_collection():
    """Test metrics collection."""
    print("\nTesting Metrics Collection...")
    
    # Load config
    with open('config.paper_trading.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    metrics = MetricsCollector(config)
    
    # Test recording trades
    try:
        metrics.record_trade({'net': 1000.0, 'strategy': 'TestStrategy'})
        metrics.record_trade({'net': -500.0, 'strategy': 'TestStrategy'})
        metrics.record_trade({'net': 0.0, 'strategy': 'TestStrategy'})
        
        print(f"[PASS] Trade recording: {metrics.total_trades} trades recorded")
        
        # Test metrics calculation
        win_rate = metrics.get_win_rate()
        print(f"[PASS] Win rate calculated: {win_rate:.1f}%")
        
        # Test session summary
        summary = metrics.get_session_summary()
        print(f"[PASS] Session summary generated with {len(summary)} metrics")
        
        # Test health status
        health = metrics.get_health_status()
        print(f"[PASS] Health status generated: {health['healthy']}")
    except Exception as e:
        print(f"[FAIL] Metrics collection failed: {e}")
        return False
    
    return True

def main():
    """Run all paper trading tests."""
    print("=" * 60)
    print("PAPER TRADING MODE TEST SUITE")
    print("=" * 60)
    
    # Set up logging
    logging.basicConfig(level=logging.INFO)
    
    all_passed = True
    
    # Run tests
    all_passed &= test_paper_trading_config()
    all_passed &= test_component_initialization()
    all_passed &= test_risk_calculations()
    all_passed &= test_metrics_collection()
    
    # Print summary
    print("\n" + "=" * 60)
    if all_passed:
        print("[PASS] ALL TESTS PASSED - Paper trading mode is ready!")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Copy config.paper_trading.yaml to config.yaml")
        print("2. Add your API credentials to config.yaml")
        print("3. Run: python trading_bot.py")
        print("4. Monitor via: python dashboard.py")
        return 0
    else:
        print("[FAIL] SOME TESTS FAILED - Please review the errors above")
        print("=" * 60)
        return 1

if __name__ == '__main__':
    sys.exit(main())