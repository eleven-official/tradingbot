#!/usr/bin/env python3
"""
Comprehensive Loki Trading Bot System Test
Tests all modules and integrations for production readiness
"""

# --- UTF-8 stdio guard (auto-inserted) ---
import sys as _sys_io
if hasattr(_sys_io.stdout, "reconfigure"):
    _sys_io.stdout.reconfigure(encoding="utf-8", errors="replace")
    _sys_io.stderr.reconfigure(encoding="utf-8", errors="replace")

import sys
import os
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

# Color codes for terminal output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

class LokiSystemTester:
    """Comprehensive system testing for Loki Trading Bot"""
    
    def __init__(self):
        self.results: List[Tuple[str, bool, str]] = []
        self.total_tests = 0
        self.passed_tests = 0
        
    def log_test(self, name: str, passed: bool, message: str = ""):
        """Log test result"""
        self.total_tests += 1
        if passed:
            self.passed_tests += 1
            status = f"{GREEN}✓ PASS{RESET}"
        else:
            status = f"{RED}✗ FAIL{RESET}"
        
        print(f"  {status} {name}")
        if message:
            print(f"      {message}")
        
        self.results.append((name, passed, message))
    
    def test_imports(self) -> bool:
        """Test 1: Verify all required imports"""
        print(f"\n{BLUE}[TEST 1] Testing Imports{RESET}")
        
        imports = [
            ("pandas", "pandas"),
            ("numpy", "numpy"),
            ("yfinance", "yfinance"),
            ("alpaca", "alpaca-py"),
            ("PyQt6", "PyQt6"),
            ("pyqtgraph", "pyqtgraph"),
            ("sklearn", "scikit-learn"),
        ]
        
        all_passed = True
        for module, package_name in imports:
            try:
                __import__(module)
                self.log_test(f"Import {package_name}", True)
            except ImportError as e:
                self.log_test(f"Import {package_name}", False, f"Missing: {str(e)}")
                all_passed = False
        
        return all_passed
    
    def test_loki_modules(self) -> bool:
        """Test 2: Verify Loki module structure"""
        print(f"\n{BLUE}[TEST 2] Testing Loki Module Structure{RESET}")
        
        modules = [
            "loki.data.real_market_data",
            "loki.strategies.joshuas_strategy",
            "loki.ml.ai_trainer",
            "loki.trading.alpaca_trader",
            "loki.ui.candlestick_chart",
            "loki.ui.main_app",
        ]
        
        all_passed = True
        for module in modules:
            try:
                __import__(module)
                self.log_test(f"Module {module}", True)
            except (ImportError, NameError) as e:
                # NameError is common when a module's optional PyQt6/pyqtgraph
                # dependency is missing but not guarded — report it, don't crash.
                self.log_test(f"Module {module}", False, str(e))
                all_passed = False
        
        return all_passed
    
    def test_market_data(self) -> bool:
        """Test 3: Real market data retrieval"""
        print(f"\n{BLUE}[TEST 3] Testing Real Market Data{RESET}")
        
        try:
            from loki.data import get_stock_data
            
            # Test with a known stable symbol
            symbol = "AAPL"
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            
            df = get_stock_data(symbol, start_date, end_date)
            
            if df is not None and len(df) > 0:
                self.log_test("Market data retrieval", True, 
                            f"Retrieved {len(df)} bars for {symbol}")
                
                # Verify required columns
                required_cols = ['open', 'high', 'low', 'close', 'volume']
                has_cols = all(col in df.columns for col in required_cols)
                self.log_test("Market data columns", has_cols, 
                            f"Columns: {', '.join(df.columns)}")
                
                return has_cols
            else:
                self.log_test("Market data retrieval", False, 
                            "No data returned")
                return False
                
        except Exception as e:
            self.log_test("Market data retrieval", False, str(e))
            return False
    
    def test_joshuas_strategy(self) -> bool:
        """Test 4: Joshua's Strategy analysis"""
        print(f"\n{BLUE}[TEST 4] Testing Joshua's Strategy{RESET}")
        
        try:
            from loki.strategies import run_joshuas_strategy
            from loki.data import get_stock_data
            from datetime import datetime, timedelta
            
            # Get real market data
            end_date = datetime.now()
            start_date = end_date - timedelta(days=90)
            df = get_stock_data("SPY", start_date, end_date)
            
            if df is None or len(df) < 50:
                self.log_test("Joshua's Strategy", False, 
                            "Insufficient data for strategy test")
                return False
            
            # Run strategy
            signal = run_joshuas_strategy(df)
            
            if signal:
                self.log_test("Joshua's Strategy execution", True,
                            f"Action: {signal.action}, Confidence: {signal.confidence:.1f}%")
                
                # Verify signal structure
                has_valid_structure = (
                    signal.action in ['BUY', 'SELL', 'HOLD'] and
                    0 <= signal.confidence <= 100
                )
                self.log_test("Strategy signal structure", has_valid_structure)
                
                return has_valid_structure
            else:
                self.log_test("Joshua's Strategy execution", False, 
                            "No signal generated")
                return False
                
        except Exception as e:
            self.log_test("Joshua's Strategy", False, str(e))
            return False
    
    def test_ai_trainer(self) -> bool:
        """Test 5: AI Training Module"""
        print(f"\n{BLUE}[TEST 5] Testing AI Training Module{RESET}")
        
        try:
            from loki.ml import quick_train
            from loki.data import get_stock_data
            from datetime import datetime, timedelta
            
            # Get training data
            end_date = datetime.now()
            start_date = end_date - timedelta(days=180)
            df = get_stock_data("SPY", start_date, end_date)
            
            if df is None or len(df) < 100:
                self.log_test("AI Training", False, 
                            "Insufficient data for training")
                return False
            
            # Quick training test
            result = quick_train(df)
            
            if result:
                self.log_test("AI Training execution", True,
                            f"Accuracy: {result.accuracy:.1f}%, Reliability: {result.reliability_score:.1f}%")
                
                # Check if meets 80% reliability target
                meets_target = result.reliability_score >= 80.0
                self.log_test("AI Reliability >= 80%", meets_target,
                            f"Target: 80%, Achieved: {result.reliability_score:.1f}%")
                
                return True
            else:
                self.log_test("AI Training execution", False, 
                            "Training failed")
                return False
                
        except Exception as e:
            self.log_test("AI Training", False, str(e))
            return False
    
    def test_alpaca_connection(self) -> bool:
        """Test 6: Alpaca API Connection"""
        print(f"\n{BLUE}[TEST 6] Testing Alpaca Connection{RESET}")
        
        try:
            from loki.trading import get_alpaca_trader
            from loki.trading.alpaca_trader import TradingMode
            
            # Test paper trading connection (safe to test)
            trader = get_alpaca_trader(mode=TradingMode.PAPER)
            
            # Try to get account info
            account = trader.get_account_info()
            
            if account:
                self.log_test("Alpaca connection", True,
                            f"Account: {account.get('account_number', 'N/A')}")
                
                # Check if paper trading
                is_paper = account.get('account_number', '').startswith('P')
                self.log_test("Paper trading mode", is_paper)
                
                return True
            else:
                self.log_test("Alpaca connection", False, 
                            "Could not retrieve account info")
                return False
                
        except FileNotFoundError as e:
            self.log_test("Alpaca connection", False, 
                        "Missing .env file with API credentials")
            return False
        except Exception as e:
            self.log_test("Alpaca connection", False, str(e))
            return False
    
    def test_ui_components(self) -> bool:
        """Test 7: UI Components"""
        print(f"\n{BLUE}[TEST 7] Testing UI Components{RESET}")
        
        try:
            from PyQt6.QtWidgets import QApplication
            from loki.ui.candlestick_chart import ProfessionalCandlestickChart
            from loki.ui.main_app import LokiMainApp
            import sys
            
            # Create Qt application (required for widgets)
            app = QApplication.instance()
            if app is None:
                app = QApplication(sys.argv)
            
            # Test candlestick chart
            chart = ProfessionalCandlestickChart()
            self.log_test("Candlestick chart creation", True)
            
            # Test main app
            main_app = LokiMainApp()
            self.log_test("Main application creation", True)
            
            return True
            
        except Exception as e:
            self.log_test("UI Components", False, str(e))
            return False
    
    def test_error_handling(self) -> bool:
        """Test 8: Error Handling"""
        print(f"\n{BLUE}[TEST 8] Testing Error Handling{RESET}")
        
        try:
            from loki.data import get_stock_data
            from loki.strategies import run_joshuas_strategy
            
            # Test with invalid symbol
            df = get_stock_data("INVALID_SYMBOL_12345", 
                              datetime.now() - timedelta(days=30),
                              datetime.now())
            
            self.log_test("Invalid symbol handling", df is None or len(df) == 0,
                        "Gracefully handled invalid symbol")
            
            # Test with insufficient data
            import pandas as pd
            empty_df = pd.DataFrame()
            signal = run_joshuas_strategy(empty_df)
            
            self.log_test("Insufficient data handling", signal is None,
                        "Gracefully handled empty data")
            
            return True
            
        except Exception as e:
            self.log_test("Error Handling", False, str(e))
            return False
    
    def run_all_tests(self):
        """Run all system tests"""
        print(f"\n{'='*60}")
        print(f"{BLUE}LOKI TRADING BOT - COMPREHENSIVE SYSTEM TEST{RESET}")
        print(f"{'='*60}")
        print(f"Testing production readiness...")
        
        # Run all tests
        self.test_imports()
        self.test_loki_modules()
        self.test_market_data()
        self.test_joshuas_strategy()
        self.test_ai_trainer()
        self.test_alpaca_connection()
        self.test_ui_components()
        self.test_error_handling()
        
        # Print summary
        print(f"\n{'='*60}")
        print(f"{BLUE}TEST SUMMARY{RESET}")
        print(f"{'='*60}")
        
        pass_rate = (self.passed_tests / self.total_tests * 100) if self.total_tests > 0 else 0
        
        print(f"Total Tests: {self.total_tests}")
        print(f"Passed: {GREEN}{self.passed_tests}{RESET}")
        print(f"Failed: {RED}{self.total_tests - self.passed_tests}{RESET}")
        print(f"Pass Rate: {pass_rate:.1f}%")
        
        if pass_rate >= 90:
            print(f"\n{GREEN}✓ SYSTEM IS PRODUCTION READY{RESET}")
            return 0
        elif pass_rate >= 70:
            print(f"\n{YELLOW}⚠ SYSTEM NEEDS MINOR FIXES{RESET}")
            return 1
        else:
            print(f"\n{RED}✗ SYSTEM NOT READY FOR PRODUCTION{RESET}")
            return 2

def main():
    """Main test execution"""
    tester = LokiSystemTester()
    exit_code = tester.run_all_tests()
    
    print(f"\n{'='*60}\n")
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
