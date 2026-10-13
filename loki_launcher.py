#!/usr/bin/env python3
"""
LOKI MASTER LAUNCHER - AUTO-UPDATING
====================================
Automatically launches the latest version of Loki!
Your desktop shortcut will always use the newest features.

This file auto-detects updates and launches them automatically.
"""

import sys
import os
from pathlib import Path

# Ensure we're in the right directory
os.chdir(Path(__file__).parent)

def main():
    """Master launcher - automatically uses latest version"""
    
    print("=" * 70)
    print("🤖 LOKI AI TRADING SYSTEM")
    print("=" * 70)
    print()
    
    # Check which version to launch
    neural_terminal = Path("loki_neural_terminal.py")
    
    if neural_terminal.exists():
        print("✨ Launching LOKI NEURAL TERMINAL v6.0 (Latest Version)")
        print("   • Real market data")
        print("   • AI-powered trading")
        print("   • Professional interface")
        print("   • Paper & Live modes")
        print()
        
        try:
            # Launch v6.0
            import loki_neural_terminal
            return loki_neural_terminal.main()
            
        except ImportError as e:
            print(f"📦 Installing dependencies: {e}")
            
            import subprocess
            deps = ["PyQt6", "pyqtgraph", "pandas", "numpy", "alpaca-py", "yfinance"]
            
            for dep in deps:
                print(f"   Installing {dep}...")
                subprocess.call([sys.executable, "-m", "pip", "install", dep])
            
            print("\n✅ Dependencies installed!")
            print("🔄 Please run again to start the terminal.\n")
            input("Press Enter to exit...")
            return 0
            
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
            input("\nPress Enter to exit...")
            return 1
    
    else:
        print("⚠️  Neural Terminal not found")
        print("📁 Looking for alternative versions...\n")
        
        # Try legacy version
        try:
            import loki_desktop
            print("📺 Launching Legacy Terminal v5.0")
            return loki_desktop.main()
        except:
            print("❌ No Loki terminal found!")
            print("📥 Please ensure loki_neural_terminal.py exists in this folder.")
            input("\nPress Enter to exit...")
            return 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
        sys.exit(0)
