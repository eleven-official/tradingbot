@echo off
REM ========================================
REM Loki Trading Bot Launcher
REM Production-Ready Trading System
REM ========================================

echo.
echo ========================================
echo    LOKI TRADING BOT
echo    Professional Trading System
echo ========================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ from python.org
    pause
    exit /b 1
)

REM Display Python version
echo [*] Checking Python version...
python --version

REM Check if required packages are installed
echo [*] Checking dependencies...
python -c "import alpaca; import yfinance; import PyQt6; import pyqtgraph" >nul 2>&1
if errorlevel 1 (
    echo.
    echo WARNING: Some dependencies are missing!
    echo Installing required packages...
    echo.
    pip install alpaca-py yfinance PyQt6 pyqtgraph pandas numpy scikit-learn ta-lib
    if errorlevel 1 (
        echo.
        echo ERROR: Failed to install dependencies
        echo Please manually run: pip install -r requirements.txt
        pause
        exit /b 1
    )
)

REM Check if .env file exists
if not exist ".env" (
    if not exist ".env.alpaca" (
        echo.
        echo WARNING: No .env or .env.alpaca file found!
        echo Please create .env with your Alpaca API credentials:
        echo   ALPACA_API_KEY=your_key_here
        echo   ALPACA_SECRET_KEY=your_secret_here
        echo   ALPACA_BASE_URL=https://paper-api.alpaca.markets
        echo.
        pause
    )
)

echo [*] Starting Loki Trading Bot...
echo.

REM Launch the main application
python -m loki.ui.main_app

REM Check exit code
if errorlevel 1 (
    echo.
    echo ========================================
    echo ERROR: Application crashed or exited with error
    echo Check the logs for details
    echo ========================================
    echo.
    pause
) else (
    echo.
    echo ========================================
    echo Loki Trading Bot closed successfully
    echo ========================================
    echo.
)

exit /b 0
