"""Quick module test to verify installations"""
# --- UTF-8 stdio guard (auto-inserted) ---
import sys as _sys_io
if hasattr(_sys_io.stdout, "reconfigure"):
    _sys_io.stdout.reconfigure(encoding="utf-8", errors="replace")
    _sys_io.stderr.reconfigure(encoding="utf-8", errors="replace")

import sys
from pathlib import Path

# Enable UTF-8 for Windows console
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).parent))

print("Testing Loki Modules...")
print()


# Test 1: Basic imports
try:
    import numpy as np
    import pandas as pd
    print("✓ NumPy & Pandas")
except ImportError as e:
    print(f"✗ NumPy/Pandas: {e}")

# Test 2: Market Analyzer
try:
    from loki.ai.advanced_market_analyzer import AdvancedMarketAnalyzer
    print("✓ Advanced Market Analyzer")
except ImportError as e:
    print(f"✗ Market Analyzer: {e}")

# Test 3: Strategies
try:
    from loki.ai.sophisticated_strategies import StrategyManager
    print("✓ Sophisticated Strategies")
except ImportError as e:
    print(f"✗ Strategies: {e}")

# Test 4: Notifications
try:
    from loki.core.smart_notifications import SmartNotificationSystem
    print("✓ Smart Notifications")
except ImportError as e:
    print(f"✗ Notifications: {e}")

# Test 5: Risk Management
try:
    from loki.risk.advanced_risk import AdvancedRiskManager
    print("✓ Advanced Risk Manager")
except ImportError as e:
    print(f"✗ Risk Manager: {e}")

# Test 6: UI Modules
try:
    import customtkinter as ctk
    import loki_desktop
    print("✓ CustomTkinter Desktop UI (Ready to launch)")
except ImportError as e:
    print(f"✗ CustomTkinter UI: {e}")

try:
    from PyQt6.QtWidgets import QApplication
    print("✓ PyQt6 Available")
    try:
        from loki.desktop.ultra_modern_ui import LokiUltraModernUI
        print("✓ Ultra Modern UI")
    except ImportError as e:
        print(f"✗ Ultra Modern UI: {e}")
except ImportError:
    print("ℹ PyQt6 not installed (optional - CustomTkinter UI is active)")

print()
print("Quick test complete!")

