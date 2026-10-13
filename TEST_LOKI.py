#!/usr/bin/env python3
"""
LOKI v7.0 - Comprehensive System Test
======================================
Tests all imports, checks for errors, validates configuration
"""

# --- UTF-8 stdio guard (auto-inserted) ---
import sys as _sys_io
if hasattr(_sys_io.stdout, "reconfigure"):
    _sys_io.stdout.reconfigure(encoding="utf-8", errors="replace")
    _sys_io.stderr.reconfigure(encoding="utf-8", errors="replace")

import sys
import os
from pathlib import Path

# Colors
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def print_header(text):
    print(f"\n{BLUE}{'='*70}{RESET}")
    print(f"{BLUE}{text.center(70)}{RESET}")
    print(f"{BLUE}{'='*70}{RESET}\n")

def test_result(name, passed, message=""):
    status = f"{GREEN}✓ PASS{RESET}" if passed else f"{RED}✗ FAIL{RESET}"
    print(f"  {status} {name}")
    if message:
        print(f"      {message}")
    return passed

def main():
    """Run comprehensive system test"""
    print_header("LOKI v7.0 ENTERPRISE - SYSTEM TEST")
    
    total_tests = 0
    passed_tests = 0
    
    # Test 1: Python Version
    print(f"\n{BLUE}[TEST 1] Python Environment{RESET}")
    total_tests += 1
    py_version = sys.version_info
    py_ok = py_version >= (3, 8)
    if test_result("Python version", py_ok, f"Version: {py_version.major}.{py_version.minor}.{py_version.micro}"):
        passed_tests += 1
    
    # Test 2: Core Dependencies
    print(f"\n{BLUE}[TEST 2] Core Dependencies{RESET}")
    core_deps = [
        ("PyQt6", "PyQt6"),
        ("pyqtgraph", "pyqtgraph"),
        ("pandas", "pandas"),
        ("numpy", "numpy"),
    ]
    
    for module, name in core_deps:
        total_tests += 1
        try:
            __import__(module)
            if test_result(name, True, "Installed"):
                passed_tests += 1
        except ImportError as e:
            test_result(name, False, f"Missing: {e}")
    
    # Test 3: Trading Dependencies
    print(f"\n{BLUE}[TEST 3] Trading Dependencies{RESET}")
    trading_deps = [
        ("alpaca", "alpaca-py"),
        ("yfinance", "yfinance"),
        ("dotenv", "python-dotenv"),
    ]
    
    for module, name in trading_deps:
        total_tests += 1
        try:
            __import__(module)
            if test_result(name, True, "Installed"):
                passed_tests += 1
        except ImportError:
            test_result(name, False, "Optional - install if needed")
            passed_tests += 1  # Don't fail on optional
    
    # Test 4: LOKI Modules
    print(f"\n{BLUE}[TEST 4] LOKI Modules{RESET}")
    loki_modules = [
        "loki.data",
        "loki.strategies",
        "loki.ml",
        "loki.trading",
        "loki.ui.candlestick_chart",
    ]
    
    for module in loki_modules:
        total_tests += 1
        try:
            __import__(module)
            if test_result(module, True):
                passed_tests += 1
        except ImportError as e:
            test_result(module, False, str(e))
    
    # Test 5: Files Exist
    print(f"\n{BLUE}[TEST 5] Required Files{RESET}")
    required_files = [
        "loki_enterprise.py",
        "LOKI_NEURAL_TERMINAL.py",
        "CREATE_LOKI_SHORTCUTS.bat",
    ]
    
    for file in required_files:
        total_tests += 1
        exists = Path(file).exists()
        if test_result(file, exists):
            passed_tests += 1
    
    # Test 6: Configuration
    print(f"\n{BLUE}[TEST 6] Configuration{RESET}")
    total_tests += 1
    env_file = Path(".env")
    env_exists = env_file.exists()
    if test_result(".env file", env_exists, "Required for Alpaca API" if not env_exists else "Found"):
        passed_tests += 1
    elif not env_exists:
        print(f"      {YELLOW}Create .env with: ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_BASE_URL{RESET}")
    
    # Test 7: Try Importing Main App
    print(f"\n{BLUE}[TEST 7] Main Application{RESET}")
    total_tests += 1
    try:
        import loki_enterprise
        if test_result("loki_enterprise.py", True, "Main app can be imported"):
            passed_tests += 1
    except ImportError as e:
        test_result("loki_enterprise.py", False, str(e))
    except Exception as e:
        test_result("loki_enterprise.py", False, f"Error: {e}")
    
    # Summary
    print(f"\n{BLUE}{'='*70}{RESET}")
    print(f"{BLUE}TEST SUMMARY{RESET}")
    print(f"{BLUE}{'='*70}{RESET}")
    
    pass_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
    
    print(f"Total Tests: {total_tests}")
    print(f"Passed: {GREEN}{passed_tests}{RESET}")
    print(f"Failed: {RED}{total_tests - passed_tests}{RESET}")
    print(f"Pass Rate: {pass_rate:.1f}%")
    
    if pass_rate == 100:
        print(f"\n{GREEN}✓ ALL TESTS PASSED - LOKI IS READY!{RESET}")
        print(f"\n🚀 Launch LOKI:")
        print(f"   • Click your desktop 'LOKI' icon")
        print(f"   • Or run: python loki_enterprise.py")
        return 0
    elif pass_rate >= 80:
        print(f"\n{YELLOW}⚠ MOSTLY READY - Some optional features missing{RESET}")
        print(f"\n💡 To install missing packages:")
        print(f"   pip install PyQt6 pyqtgraph pandas numpy alpaca-py yfinance")
        return 0
    else:
        print(f"\n{RED}✗ SYSTEM NOT READY{RESET}")
        print(f"\n💡 Install required packages:")
        print(f"   pip install -r requirements.txt")
        return 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(f"\n\n{YELLOW}Test interrupted{RESET}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{RED}Test error: {e}{RESET}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
