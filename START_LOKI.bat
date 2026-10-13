@echo off
REM ========================================
REM LOKI NEURAL TERMINAL - QUICK START
REM ========================================

cls
echo.
echo =======================================
echo   LOKI NEURAL TERMINAL v6.0
echo   Starting AI Trading Platform...
echo =======================================
echo.

REM Run directly
python loki_neural_terminal.py

if errorlevel 1 (
    echo.
    echo =======================================
    echo   ERROR: Could not start
    echo   Check error message above
    echo =======================================
    echo.
    pause
)
