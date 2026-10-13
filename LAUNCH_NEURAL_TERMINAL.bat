@echo off
REM ========================================
REM Loki Neural Terminal Launcher v6.0
REM Production AI Trading Terminal
REM ========================================

echo.
echo ========================================
echo    LOKI NEURAL TERMINAL v6.0
echo    Production AI Trading System
echo ========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found
    pause
    exit /b 1
)

echo [*] Python version:
python --version

REM Check dependencies
echo [*] Checking dependencies...
python -c "import PyQt6; import pyqtgraph; import pandas; import numpy" >nul 2>&1
if errorlevel 1 (
    echo.
    echo [!] Installing required packages...
    pip install PyQt6 pyqtgraph pandas numpy alpaca-py yfinance python-dotenv pyyaml scikit-learn
)

REM Check .env
if not exist ".env" (
    if not exist ".env.alpaca" (
        echo.
        echo [!] WARNING: No .env file found
        echo     Create .env with your Alpaca credentials
        echo.
    )
)

echo [*] Starting Loki Neural Terminal v6.0...
echo.

REM Launch
python loki_neural_terminal.py

if errorlevel 1 (
    echo.
    echo ========================================
    echo ERROR: Application crashed
    echo Check logs/loki_neural_*.log
    echo ========================================
    echo.
    pause
)

exit /b 0
