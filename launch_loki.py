#!/usr/bin/env python3
"""
LOKI NEURAL TERMINAL v6.0 - AUTO-UPDATING LAUNCHER
==================================================
This launcher automatically uses the latest version!
Your desktop shortcut will always launch the newest terminal.

No need to change shortcuts - updates happen automatically!
"""

# --- UTF-8 stdio guard (auto-inserted) ---
import sys as _sys_io
if hasattr(_sys_io.stdout, "reconfigure"):
    _sys_io.stdout.reconfigure(encoding="utf-8", errors="replace")
    _sys_io.stderr.reconfigure(encoding="utf-8", errors="replace")

import sys
import subprocess
from pathlib import Path

def auto_install_packages():
    """Auto-install missing packages"""
    packages = {
        "PyQt6": "PyQt6>=6.5.0",
        "pyqtgraph": "pyqtgraph>=0.13.3",
        "pandas": "pandas>=2.0.0",
        "numpy": "numpy>=1.24.0",
        "alpaca": "alpaca-py>=0.9.0",
        "yfinance": "yfinance>=0.2.28",
        "dotenv": "python-dotenv",
        "yaml": "pyyaml",
    }
    
    print("🔍 Checking dependencies...")
    missing = []
    
    for module, pip_name in packages.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(pip_name)
    
    if missing:
        print(f"\n📦 Installing {len(missing)} missing packages...")
        for pkg in missing:
            print(f"   Installing {pkg}...")
            try:
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", pkg],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                print(f"   ✅ {pkg}")
            except:
                print(f"   ⚠️ {pkg} (optional)")
    else:
        print("✅ All dependencies ready!")

def main():
    """Launch the latest Loki Neural Terminal"""
    print("=" * 60)
    print("🤖 LOKI NEURAL TERMINAL v6.0")
    print("   Production AI Trading Platform")
    print("=" * 60)
    print()
    
    # Auto-install if needed
    auto_install_packages()
    
    print("\n🚀 Starting Loki Neural Terminal v6.0...")
    print("   (Your shortcut automatically uses the latest version!)")
    print()
    
    try:
        # Launch the NEW v6.0 terminal
        import loki_neural_terminal
        sys.exit(loki_neural_terminal.main())
        
    except ImportError as e:
        print(f"\n❌ Could not load terminal: {e}")
        print("\n💡 Trying fallback installation...")
        
        # Force install everything
        required = [
            "PyQt6", "pyqtgraph", "pandas", "numpy", 
            "alpaca-py", "yfinance", "python-dotenv", "pyyaml"
        ]
        
        for pkg in required:
            subprocess.call([sys.executable, "-m", "pip", "install", pkg])
        
        print("\n✅ Installation complete! Please run again.")
        input("\nPress Enter to exit...")
        return 1
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        input("\nPress Enter to exit...")
        return 1

if __name__ == "__main__":
    sys.exit(main())
