"""
LOKI - Complete Diagnostic and Fix Script
Tests all components and fixes issues automatically
"""

# --- UTF-8 stdio guard (auto-inserted) ---
import sys as _sys_io
if hasattr(_sys_io.stdout, "reconfigure"):
    _sys_io.stdout.reconfigure(encoding="utf-8", errors="replace")
    _sys_io.stderr.reconfigure(encoding="utf-8", errors="replace")

import sys
import os
from pathlib import Path
import subprocess
import importlib.util

# Add project to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

print("=" * 60)
print("    LOKI TRADING PLATFORM - DIAGNOSTIC & FIX")
print("=" * 60)
print()

# Color codes for Windows
GREEN = ""
RED = ""
YELLOW = ""
RESET = ""

results = {
    "passed": [],
    "failed": [],
    "warnings": []
}

def test_step(name, test_func):
    """Run a test step and record results"""
    print(f"Testing: {name}...", end=" ")
    try:
        success, message = test_func()
        if success:
            print(f"✓ PASS")
            if message:
                print(f"  → {message}")
            results["passed"].append(name)
            return True
        else:
            print(f"✗ FAIL")
            print(f"  → {message}")
            results["failed"].append((name, message))
            return False
    except Exception as e:
        print(f"✗ ERROR")
        print(f"  → {str(e)}")
        results["failed"].append((name, str(e)))
        return False

def check_python_version():
    """Check Python version"""
    version = sys.version_info
    if version.major >= 3 and version.minor >= 8:
        return True, f"Python {version.major}.{version.minor}.{version.micro}"
    else:
        return False, f"Python {version.major}.{version.minor} too old, need 3.8+"

def check_package(package_name, import_name=None):
    """Check if a package is installed"""
    if import_name is None:
        import_name = package_name
    
    spec = importlib.util.find_spec(import_name)
    if spec is not None:
        return True, f"{package_name} is installed"
    else:
        return False, f"{package_name} is not installed"

def check_pyqt6():
    """Check PyQt6 installation"""
    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QT_VERSION_STR
        return True, f"PyQt6 {QT_VERSION_STR} works"
    except ImportError as e:
        return False, f"PyQt6 import failed: {e}"

def check_pyqtgraph():
    """Check pyqtgraph installation"""
    try:
        import pyqtgraph
        return True, f"pyqtgraph {pyqtgraph.__version__} works"
    except ImportError:
        return False, "pyqtgraph not installed (optional)"
    except Exception as e:
        return False, f"pyqtgraph error: {e}"

def check_numpy_pandas():
    """Check numpy and pandas"""
    try:
        import numpy as np
        import pandas as pd
        return True, f"numpy {np.__version__}, pandas {pd.__version__}"
    except ImportError as e:
        return False, f"Import failed: {e}"

def check_loki_structure():
    """Check Loki directory structure"""
    required_dirs = [
        "loki",
        "loki/desktop",
        "loki/ai",
        "loki/api",
    ]
    
    missing = []
    for dir_path in required_dirs:
        full_path = PROJECT_ROOT / dir_path
        if not full_path.exists():
            missing.append(dir_path)
    
    if missing:
        return False, f"Missing directories: {', '.join(missing)}"
    return True, "All core directories exist"

def check_enhanced_app():
    """Check if enhanced app can be imported"""
    try:
        from loki.desktop.enhanced_app import main
        return True, "Enhanced app module loads correctly"
    except ImportError as e:
        return False, f"Enhanced app import failed: {e}"
    except Exception as e:
        return False, f"Enhanced app error: {e}"

def check_autonomous_agent():
    """Check autonomous agent"""
    try:
        from loki.ai.autonomous_agent import AutonomousAgent
        return True, "Autonomous agent module loads"
    except ImportError as e:
        return False, f"Autonomous agent import failed: {e}"

def check_launchers():
    """Check launcher scripts exist"""
    launchers = {
        "START_LOKI.bat": "Main launcher",
        "TEST_LOKI.bat": "Test launcher",
        "launch_loki.py": "Python launcher",
        "loki.bat": "Quick launcher"
    }
    
    missing = []
    for launcher, desc in launchers.items():
        if not (PROJECT_ROOT / launcher).exists():
            missing.append(f"{launcher} ({desc})")
    
    if missing:
        return False, f"Missing: {', '.join(missing)}"
    return True, "All launchers present"

def check_windows_registry():
    """Check Windows registry entries"""
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\App Paths\loki"
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                value, _ = winreg.QueryValueEx(key, "")
                return True, f"Registry entry exists: {value}"
        except FileNotFoundError:
            return False, "Registry entry not found"
    except ImportError:
        return False, "Cannot check registry (not Windows?)"

def check_shortcuts():
    """Check if shortcuts were created"""
    desktop = Path.home() / "Desktop" / "Loki Trading.lnk"
    start_menu = Path(os.getenv("APPDATA")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Loki Trading.lnk"
    
    shortcuts = []
    if desktop.exists():
        shortcuts.append("Desktop")
    if start_menu.exists():
        shortcuts.append("Start Menu")
    
    if shortcuts:
        return True, f"Shortcuts in: {', '.join(shortcuts)}"
    else:
        return False, "No shortcuts found"

def install_missing_packages():
    """Install missing packages"""
    print("\n" + "=" * 60)
    print("INSTALLING MISSING PACKAGES")
    print("=" * 60)
    
    packages = [
        "PyQt6",
        "pyqtgraph",
        "pandas",
        "numpy",
        "matplotlib",
        "plotly",
        "requests",
        "pyyaml",
        "sqlalchemy",
        "fastapi",
        "uvicorn"
    ]
    
    for package in packages:
        print(f"\nInstalling {package}...")
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade", package],
                check=True,
                capture_output=True
            )
            print(f"  ✓ {package} installed successfully")
        except subprocess.CalledProcessError:
            print(f"  ⚠ Warning: Could not install {package}")

def create_missing_files():
    """Create missing essential files"""
    print("\n" + "=" * 60)
    print("CREATING MISSING FILES")
    print("=" * 60)
    
    # Ensure __init__.py files exist
    init_files = [
        "loki/__init__.py",
        "loki/desktop/__init__.py",
        "loki/ai/__init__.py",
        "loki/api/__init__.py",
        "loki/risk/__init__.py"
    ]
    
    for init_file in init_files:
        init_path = PROJECT_ROOT / init_file
        if not init_path.exists():
            init_path.parent.mkdir(parents=True, exist_ok=True)
            init_path.write_text("# Loki Trading Platform\n")
            print(f"  ✓ Created {init_file}")
    
    # Create launch_loki.py if missing
    launcher_path = PROJECT_ROOT / "launch_loki.py"
    if not launcher_path.exists():
        launcher_code = '''import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from loki.desktop.enhanced_app import main
    main()
except ImportError:
    try:
        from loki.desktop.app import main
        main()
    except Exception as e:
        print(f"Error: {e}")
        input("Press Enter to exit...")
'''
        launcher_path.write_text(launcher_code)
        print(f"  ✓ Created launch_loki.py")
    
    # Create START_LOKI.bat if missing
    start_bat = PROJECT_ROOT / "START_LOKI.bat"
    if not start_bat.exists():
        bat_code = f'''@echo off
cd /d "{PROJECT_ROOT}"
echo Starting Loki Trading Platform...
pythonw "{PROJECT_ROOT}\\launch_loki.py"
if errorlevel 1 (
    echo Error launching Loki. Trying with console...
    python "{PROJECT_ROOT}\\launch_loki.py"
    pause
)
'''
        start_bat.write_text(bat_code)
        print(f"  ✓ Created START_LOKI.bat")

def main():
    """Main diagnostic routine"""
    print("\n📋 RUNNING DIAGNOSTICS...\n")
    
    # Run all tests
    test_step("Python Version", check_python_version)
    test_step("PyQt6", check_pyqt6)
    test_step("pyqtgraph", check_pyqtgraph)
    test_step("NumPy & Pandas", check_numpy_pandas)
    test_step("Loki Directory Structure", check_loki_structure)
    test_step("Enhanced App Module", check_enhanced_app)
    test_step("Autonomous Agent Module", check_autonomous_agent)
    test_step("Launcher Scripts", check_launchers)
    test_step("Windows Registry", check_windows_registry)
    test_step("Shortcuts", check_shortcuts)
    
    # Print summary
    print("\n" + "=" * 60)
    print("DIAGNOSTIC SUMMARY")
    print("=" * 60)
    print(f"✓ Passed: {len(results['passed'])}")
    print(f"✗ Failed: {len(results['failed'])}")
    print()
    
    if results["failed"]:
        print("FAILED TESTS:")
        for name, message in results["failed"]:
            print(f"  • {name}")
            print(f"    → {message}")
        print()
        
        # Attempt fixes
        response = input("Attempt to fix these issues? (y/n): ")
        if response.lower() == 'y':
            install_missing_packages()
            create_missing_files()
            
            print("\n" + "=" * 60)
            print("FIXES APPLIED!")
            print("=" * 60)
            print()
            print("Please run FIX_AND_TEST_EVERYTHING.bat to complete setup")
            print("Then restart your computer for Windows Search to work")
    else:
        print("✓ ALL TESTS PASSED!")
        print()
        print("Loki is properly configured and ready to use!")
        print()
        print("To launch Loki:")
        print("  1. Double-click 'Loki Trading' on your Desktop")
        print("  2. OR search 'Loki Trading' in Windows Search")
        print("  3. OR run START_LOKI.bat")
    
    print()
    input("Press Enter to exit...")

if __name__ == "__main__":
    main()
