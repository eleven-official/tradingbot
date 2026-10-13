"""
Comprehensive Module Testing Script
Tests all Loki modules and reports errors
"""
import sys
from pathlib import Path
import traceback

# Enable UTF-8 for Windows console
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Add project to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

print("=" * 70)
print("    LOKI MODULE TESTING")
print("=" * 70)
print()

test_results = []


def test_module(module_name, import_statement, test_func=None):
    """Test a module import and optional functionality"""
    print(f"Testing: {module_name}...", end=" ")
    try:
        # Try import
        exec(import_statement, globals())
        
        # Run test function if provided
        if test_func:
            test_func()
        
        print("✓ PASS")
        test_results.append((module_name, True, None))
        return True
    except Exception as e:
        print(f"✗ FAIL")
        error_msg = str(e)
        print(f"  Error: {error_msg}")
        test_results.append((module_name, False, error_msg))
        return False


print("\n[1/5] TESTING AI MODULES\n")

test_module(
    "Advanced Market Analyzer",
    "from loki.ai.advanced_market_analyzer import AdvancedMarketAnalyzer"
)

test_module(
    "Sophisticated Strategies",
    "from loki.ai.sophisticated_strategies import StrategyManager, MomentumStrategy"
)

test_module(
    "Autonomous Agent",
    "from loki.ai.autonomous_agent import AutonomousAIAgent"
)

test_module(
    "Neural Reasoning",
    "from loki.ai.neural_reasoning import NeuralReasoningEngine"
)

test_module(
    "Consciousness Monitor",
    "from loki.ai.consciousness_monitor import ConsciousnessMonitor"
)

print("\n[2/5] TESTING CORE MODULES\n")

test_module(
    "Smart Notifications",
    "from loki.core.smart_notifications import SmartNotificationSystem, get_notification_system"
)

test_module(
    "Risk Controller",
    "from loki.risk.advanced_risk import AdvancedRiskManager as RiskController"
)

print("\n[3/5] TESTING DESKTOP UI MODULES\n")

test_module(
    "CustomTkinter Desktop Terminal",
    "import loki_desktop"
)

# Test with PyQt6 check
def test_ui_import():
    try:
        from PyQt6.QtWidgets import QApplication
        return True
    except ImportError:
        return False

if test_ui_import():

    test_module(
        "Ultra Modern UI",
        "from loki.desktop.ultra_modern_ui import LokiUltraModernUI"
    )
    
    test_module(
        "Advanced Charting",
        "from loki.desktop.advanced_charting import TradingViewChart"
    )
    
    test_module(
        "AI Explanation Panel",
        "from loki.desktop.ai_explanation_panel import AIExplanationPanel"
    )
    
    test_module(
        "Performance Analytics",
        "from loki.desktop.performance_analytics import PerformanceAnalyticsDashboard"
    )
    
    test_module(
        "Portfolio Optimization",
        "from loki.desktop.portfolio_optimization import PortfolioOptimizationDashboard"
    )
else:
    print("⚠ PyQt6 not available, skipping UI tests")
    print("  Install with: pip install PyQt6 pyqtgraph")

print("\n[4/5] TESTING DEPENDENCIES\n")

deps = [
    ("NumPy", "import numpy"),
    ("Pandas", "import pandas"),
    ("OpenAI", "import openai"),
    ("Anthropic", "import anthropic"),
    ("Requests", "import requests"),
    ("YAML", "import yaml"),
]

for name, import_stmt in deps:
    test_module(name, import_stmt)

print("\n[5/5] FUNCTIONAL TESTS\n")

def test_market_analyzer():
    """Test market analyzer with sample data"""
    from loki.ai.advanced_market_analyzer import AdvancedMarketAnalyzer
    import pandas as pd
    import numpy as np
    
    # Create sample data
    dates = pd.date_range(end=pd.Timestamp.now(), periods=100, freq='D')
    data = pd.DataFrame({
        'open': np.random.randn(100).cumsum() + 100,
        'high': np.random.randn(100).cumsum() + 102,
        'low': np.random.randn(100).cumsum() + 98,
        'close': np.random.randn(100).cumsum() + 100,
        'volume': np.random.randint(1000000, 10000000, 100)
    }, index=dates)
    
    analyzer = AdvancedMarketAnalyzer()
    analysis = analyzer.analyze(data, "TEST")
    
    assert analysis is not None
    assert analysis.symbol == "TEST"
    print(f"  Analysis: {analysis.recommended_action} ({analysis.confidence:.1f}%)")

def test_strategy_manager():
    """Test strategy manager"""
    from loki.ai.sophisticated_strategies import StrategyManager
    import pandas as pd
    import numpy as np
    
    dates = pd.date_range(end=pd.Timestamp.now(), periods=100, freq='D')
    data = pd.DataFrame({
        'open': np.random.randn(100).cumsum() + 100,
        'high': np.random.randn(100).cumsum() + 102,
        'low': np.random.randn(100).cumsum() + 98,
        'close': np.random.randn(100).cumsum() + 100,
        'volume': np.random.randint(1000000, 10000000, 100)
    }, index=dates)
    
    manager = StrategyManager()
    signals = manager.analyze_all(data)
    
    assert len(signals) > 0
    print(f"  Generated {len(signals)} strategy signals")

def test_notifications():
    """Test notification system"""
    from loki.core.smart_notifications import get_notification_system
    
    notif_sys = get_notification_system()
    
    # Test rule evaluation
    notif_sys.evaluate_rules({
        'signal': 'BUY',
        'confidence': 85,
        'symbol': 'TEST',
        'entry_price': 100.0
    })
    
    stats = notif_sys.get_stats()
    assert stats['total'] > 0
    print(f"  Notifications: {stats['total']} total, {stats['unread']} unread")

print("\nTesting Market Analyzer...")
try:
    test_market_analyzer()
    print("✓ Market Analyzer functional test PASSED")
except Exception as e:
    print(f"✗ Market Analyzer test FAILED: {e}")

print("\nTesting Strategy Manager...")
try:
    test_strategy_manager()
    print("✓ Strategy Manager functional test PASSED")
except Exception as e:
    print(f"✗ Strategy Manager test FAILED: {e}")

print("\nTesting Notification System...")
try:
    test_notifications()
    print("✓ Notification System functional test PASSED")
except Exception as e:
    print(f"✗ Notification System test FAILED: {e}")

# Summary
print("\n" + "=" * 70)
print("TEST SUMMARY")
print("=" * 70)

passed = sum(1 for _, success, _ in test_results if success)
failed = sum(1 for _, success, _ in test_results if not success)
total = len(test_results)

print(f"\nTotal Tests: {total}")
print(f"✓ Passed: {passed}")
print(f"✗ Failed: {failed}")
print(f"Success Rate: {passed/total*100:.1f}%")

if failed > 0:
    print("\n❌ FAILED TESTS:")
    for name, success, error in test_results:
        if not success:
            print(f"  • {name}")
            if error:
                print(f"    → {error}")

print("\n" + "=" * 70)

if failed == 0:
    print("🎉 ALL TESTS PASSED!")
else:
    print(f"⚠ {failed} test(s) need attention")

print()
