@echo off
REM LOKI Neural Trading Terminal Launcher
REM Professional Windows batch launcher

title LOKI Neural Trading Terminal
color 0B

echo.
echo  ╔══════════════════════════════════════════════════════════════╗
echo  ║                🚀 LOKI NEURAL TRADING TERMINAL               ║
echo  ║                   Professional Edition v4.0                  ║
echo  ╚══════════════════════════════════════════════════════════════╝
echo.

REM Change to script directory
cd /d "%~dp0"

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python not found! Please install Python 3.8+ from python.org
    echo.
    pause
    exit /b 1
)

REM Display Python version
for /f "tokens=*" %%i in ('python --version') do set PYTHON_VERSION=%%i
echo ✅ Found %PYTHON_VERSION%

REM Launch the application
echo 🚀 Starting LOKI Neural Trading Terminal...
echo.

python LOKI_NEURAL_TERMINAL.py

if errorlevel 1 (
    echo.
    echo ❌ Application failed to start. Check error messages above.
    echo.
    echo 💡 Try running: python -m pip install customtkinter pandas numpy matplotlib
    echo.
    pause
) else (
    echo.
    echo ✅ LOKI Terminal closed successfully.
)

pause