@echo off
REM LOKI - Run Complete Diagnostics

echo.
echo ========================================================
echo    LOKI DIAGNOSTICS - Testing All Components
echo ========================================================
echo.

cd /d "%~dp0"

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found!
    echo Please install Python from: https://www.python.org/downloads/
    pause
    exit /b 1
)

REM Run the diagnostic script
python DIAGNOSE_AND_FIX.py

exit /b 0
