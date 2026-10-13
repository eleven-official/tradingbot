#!/usr/bin/env python3
"""
Simple launcher for Loki Neural Terminal v6.0
Just run this file to start the terminal!
"""

if __name__ == "__main__":
    print("🚀 Starting Loki Neural Terminal v6.0...")
    
    try:
        import loki_neural_terminal
        loki_neural_terminal.main()
    except ImportError as e:
        print(f"\n❌ Import Error: {e}")
        print("\n📦 Installing required packages...")
        
        import subprocess
        import sys
        
        packages = [
            "PyQt6",
            "pyqtgraph", 
            "pandas",
            "numpy",
            "alpaca-py",
            "yfinance",
            "python-dotenv",
            "pyyaml",
            "scikit-learn"
        ]
        
        for pkg in packages:
            print(f"Installing {pkg}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])
        
        print("\n✅ Packages installed! Starting terminal...")
        import loki_neural_terminal
        loki_neural_terminal.main()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        input("\nPress Enter to exit...")
