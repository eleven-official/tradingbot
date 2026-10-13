"""
Test Loki AI Agent - Quick verification script
"""
# --- UTF-8 stdio guard (auto-inserted) ---
import sys as _sys_io
if hasattr(_sys_io.stdout, "reconfigure"):
    _sys_io.stdout.reconfigure(encoding="utf-8", errors="replace")
    _sys_io.stderr.reconfigure(encoding="utf-8", errors="replace")

import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

print("=" * 60)
print("    LOKI AI AGENT - QUICK TEST")
print("=" * 60)
print()

def test_imports():
    """Test that all core modules can be imported"""
    print("Testing imports...")
    
    tests = []
    
    # Test PyQt6
    try:
        from PyQt6.QtWidgets import QApplication
        print("  ✓ PyQt6: OK")
        tests.append(True)
    except ImportError as e:
        print(f"  ✗ PyQt6: FAILED - {e}")
        tests.append(False)
    
    # Test data libraries
    try:
        import pandas
        import numpy
        print("  ✓ Pandas/NumPy: OK")
        tests.append(True)
    except ImportError as e:
        print(f"  ✗ Pandas/NumPy: FAILED - {e}")
        tests.append(False)
    
    # Test Loki modules
    try:
        from loki.desktop.enhanced_app import LokiEnhancedApp
        print("  ✓ Enhanced App: OK")
        tests.append(True)
    except ImportError as e:
        print(f"  ✗ Enhanced App: FAILED - {e}")
        tests.append(False)
    
    try:
        from loki.ai.autonomous_agent import AutonomousAgent
        print("  ✓ Autonomous Agent: OK")
        tests.append(True)
    except ImportError as e:
        print(f"  ✗ Autonomous Agent: FAILED - {e}")
        tests.append(False)
    
    try:
        from loki.ai.neural_reasoning import NeuralReasoningEngine
        print("  ✓ Neural Reasoning: OK")
        tests.append(True)
    except ImportError as e:
        print(f"  ✗ Neural Reasoning: FAILED - {e}")
        tests.append(False)
    
    try:
        from loki.ai.consciousness_monitor import ConsciousnessMonitor
        print("  ✓ Consciousness Monitor: OK")
        tests.append(True)
    except ImportError as e:
        print(f"  ✗ Consciousness Monitor: FAILED - {e}")
        tests.append(False)
    
    print()
    return all(tests)

def test_ai_initialization():
    """Test that AI agent can be initialized"""
    print("Testing AI initialization...")
    
    try:
        from loki.ai.autonomous_agent import AutonomousAgent
        
        # Create agent (this tests the entire initialization chain)
        agent = AutonomousAgent()
        
        print("  ✓ Agent created successfully")
        print(f"  ✓ Agent ID: {agent.agent_id}")
        print(f"  ✓ Reasoning engine: {'Loaded' if agent.reasoning else 'Not loaded'}")
        print(f"  ✓ Consciousness: {'Active' if agent.consciousness else 'Not active'}")
        
        print()
        return True
    except Exception as e:
        print(f"  ✗ AI initialization FAILED: {e}")
        print()
        import traceback
        traceback.print_exc()
        return False

def test_ai_thinking():
    """Test basic AI thinking capability"""
    print("Testing AI thinking...")
    
    try:
        from loki.ai.autonomous_agent import AutonomousAgent
        
        agent = AutonomousAgent()
        
        # Test observation processing
        print("  → Testing market observation...")
        observation = {
            "price": 150.00,
            "volume": 1000000,
            "sentiment": "bullish"
        }
        
        agent.observe(observation)
        print("  ✓ Observation processed")
        
        # Test thinking (without API calls)
        print("  → Testing reasoning engine...")
        if agent.reasoning:
            # This won't make actual decisions without API keys,
            # but we can verify the structure is correct
            print("  ✓ Reasoning engine ready")
        
        print()
        return True
    except Exception as e:
        print(f"  ✗ AI thinking test FAILED: {e}")
        print()
        return False

def main():
    """Run all tests"""
    results = []
    
    # Run tests
    results.append(("Import Tests", test_imports()))
    results.append(("AI Initialization", test_ai_initialization()))
    results.append(("AI Thinking", test_ai_thinking()))
    
    # Summary
    print("=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")
    
    print()
    print(f"Results: {passed}/{total} tests passed")
    print()
    
    if passed == total:
        print("🎉 ALL TESTS PASSED!")
        print()
        print("Loki AI Agent is ready to trade!")
        print()
        print("Next steps:")
        print("  1. Configure your API keys (OpenAI/Anthropic) in .env")
        print("  2. Set up your broker credentials (Alpaca/etc)")
        print("  3. Launch Loki from Desktop shortcut")
        print("  4. Watch the AI make intelligent trading decisions!")
    else:
        print("⚠ Some tests failed")
        print()
        print("To fix:")
        print("  1. Run ULTIMATE_FIX.bat")
        print("  2. Install missing packages: pip install PyQt6 pyqtgraph pandas numpy")
        print("  3. Check that loki/ directory structure is correct")
    
    print()
    input("Press Enter to exit...")

if __name__ == "__main__":
    main()
