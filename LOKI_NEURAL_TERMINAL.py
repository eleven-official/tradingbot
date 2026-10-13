#!/usr/bin/env python3
"""
LOKI v7.0 - ENTERPRISE PLATFORM AUTO-LAUNCHER
==============================================
🎯 YOUR DESKTOP SHORTCUT USES THIS FILE!

This launcher AUTOMATICALLY uses the latest LOKI Enterprise version.
Every time you click your shortcut, it launches the newest features!

✨ No need to recreate shortcuts - updates happen automatically!
"""

import sys
import os
import subprocess
from pathlib import Path

# Ensure we're in the correct directory
os.chdir(Path(__file__).parent)

def check_dependencies():
    """Auto-install missing dependencies"""
    required = {
        "PyQt6": "PyQt6",
        "pyqtgraph": "pyqtgraph",
        "pandas": "pandas",
        "numpy": "numpy",
        "alpaca": "alpaca-py",
        "yfinance": "yfinance",
        "dotenv": "python-dotenv",
    }
    
    missing = []
    for module, package in required.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(package)
    
    if missing:
        print(f"📦 Installing {len(missing)} required packages...")
        for pkg in missing:
            try:
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", pkg],
                    stdout=subprocess.DEVNULL
                )
                print(f"   ✅ {pkg}")
            except:
                pass
        print()

def main():
    """Launch the latest Loki Neural Terminal"""
    
    # Clear screen and show banner
    os.system('cls' if os.name == 'nt' else 'clear')
    
    print("=" * 70)
    print("🤖 LOKI v7.0 ENTERPRISE")
    print("   Professional AI Trading Platform")
    print("=" * 70)
    print()
    print("✨ Auto-updating launcher - always uses the latest version!")
    print()
    
    # Check and install dependencies
    check_dependencies()
    
    # Launch v7.0 enterprise
    try:
        print("🚀 Starting LOKI v7.0 Enterprise...")
        print("   Loading systems...")
        print()
        
        # Import and launch enterprise platform
        import loki_enterprise
        return loki_enterprise.main()
        
    except ImportError as e:
        print(f"❌ Module not found: {e}")
        print()
        print("💡 Installing all dependencies...")
        
        # Force install everything
        deps = [
            "PyQt6", "pyqtgraph", "pandas", "numpy",
            "alpaca-py", "yfinance", "python-dotenv", 
            "pyyaml", "scikit-learn"
        ]
        
        for dep in deps:
            print(f"   Installing {dep}...")
            subprocess.call([sys.executable, "-m", "pip", "install", dep])
        
        print()
        print("✅ Installation complete!")
        print("🔄 Please click your desktop shortcut again to launch.")
        print()
        input("Press Enter to close...")
        return 0
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print()
        import traceback
        traceback.print_exc()
        print()
        input("Press Enter to close...")
        return 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        input("\nPress Enter to close...")
        sys.exit(1)
