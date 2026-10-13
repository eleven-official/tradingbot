@echo off
REM ================================================================
REM  LOKI Neural Trading Terminal v5.0 - One-Click Launcher
REM ================================================================
setlocal enabledelayedexpansion

cd /d "%~dp0"

REM Set UTF-8 encoding for clean console output
chcp 65001 >nul 2>&1
set PYTHONIOENCODING=utf-8

echo.
echo ================================================================
echo    ⚡ LOKI PRO v7.0 - Professional Trading Terminal
echo    Complete Interface Redesign + Real Market Data
echo ================================================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.10 or higher from https://python.org
    echo.
    pause
    exit /b 1
)

REM Check if loki_desktop.py exists
if not exist "loki_desktop.py" (
    echo [ERROR] loki_desktop.py not found in current directory.
    echo Please ensure you are running this from the tradingbot folder.
    echo.
    pause
    exit /b 1
)

REM Check required packages
echo Checking required packages...
python -c "import customtkinter" >nul 2>&1
if errorlevel 1 (
    echo [WARNING] customtkinter not found. Installing...
    pip install customtkinter
    if errorlevel 1 (
        echo [ERROR] Failed to install customtkinter.
        echo Please run: pip install customtkinter matplotlib pandas numpy
        echo.
        pause
        exit /b 1
    )
)

python -c "import matplotlib" >nul 2>&1
if errorlevel 1 (
    echo [WARNING] matplotlib not found. Installing...
    pip install matplotlib
)

python -c "import pandas" >nul 2>&1
if errorlevel 1 (
    echo [WARNING] pandas not found. Installing...
    pip install pandas
)

python -c "import numpy" >nul 2>&1
if errorlevel 1 (
    echo [WARNING] numpy not found. Installing...
    pip install numpy
)

python -c "import mplfinance" >nul 2>&1
if errorlevel 1 (
    echo [WARNING] mplfinance not found. Installing...
    pip install mplfinance
)

python -c "import ccxt" >nul 2>&1
if errorlevel 1 (
    echo [WARNING] ccxt not found. Installing...
    pip install ccxt
)

echo All dependencies verified.
echo.
echo Starting Loki Desktop Terminal...
echo.

REM Start the application
python -X utf8 loki_desktop.py

if errorlevel 1 (
    echo.
    echo [ERROR] Application exited with an error.
    echo Check loki_terminal.log for details.
    echo.
    echo Common issues:
    echo 1. Missing dependencies - run: pip install customtkinter matplotlib pandas numpy
    echo 2. Python version too old - requires Python 3.10+
    echo 3. Corrupted state files - delete the 'state' folder and restart
    echo.
    pause
    exit /b 1
)

echo.
echo Loki Desktop Terminal closed normally.
echo.
timeout /t 2 >nul
