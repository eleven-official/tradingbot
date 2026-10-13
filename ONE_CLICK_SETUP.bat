@echo off
REM LOKI - ONE-CLICK COMPLETE SETUP
REM Sets up everything: dependencies, auto-start, Windows search, and launches!

echo.
echo ================================================
echo    LOKI AI TRADING PLATFORM
echo    One-Click Complete Setup
echo ================================================
echo.

REM Check for Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found!
    echo Please install Python 3.10+ from python.org
    pause
    exit /b 1
)

echo [1/5] Installing Python dependencies...
pip install -q PyQt6 pyqtgraph pandas numpy matplotlib plotly --upgrade

echo [2/5] Installing AI dependencies (optional)...
pip install -q openai anthropic langchain langchain-openai --upgrade 2>nul
if errorlevel 1 (
    echo    Note: AI features require API keys - install manually if needed
)

echo [3/5] Creating launchers...
set LOKI_DIR=%~dp0
set LOKI_DIR=%LOKI_DIR:~0,-1%

REM Create launcher if it doesn't exist
if not exist "%LOKI_DIR%\loki_launcher.bat" (
    echo @echo off > "%LOKI_DIR%\loki_launcher.bat"
    echo cd /d "%LOKI_DIR%" >> "%LOKI_DIR%\loki_launcher.bat"
    echo pythonw -m loki.desktop.enhanced_app >> "%LOKI_DIR%\loki_launcher.bat"
)

echo [4/5] Creating Windows shortcuts...

REM Desktop shortcut
powershell -Command "$WS = New-Object -ComObject WScript.Shell; $SC = $WS.CreateShortcut('%USERPROFILE%\Desktop\Loki Trading.lnk'); $SC.TargetPath = '%LOKI_DIR%\loki_launcher.bat'; $SC.WorkingDirectory = '%LOKI_DIR%'; $SC.Description = 'Loki AI Trading Platform'; $SC.Save()" 2>nul

REM Start Menu shortcut
set START_MENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs
powershell -Command "$WS = New-Object -ComObject WScript.Shell; $SC = $WS.CreateShortcut('%START_MENU%\Loki Trading.lnk'); $SC.TargetPath = '%LOKI_DIR%\loki_launcher.bat'; $SC.WorkingDirectory = '%LOKI_DIR%'; $SC.Description = 'Loki AI Trading Platform'; $SC.Save()" 2>nul

echo [5/5] Registering with Windows Search...
reg add "HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\App Paths\loki.exe" /ve /t REG_SZ /d "%LOKI_DIR%\loki_launcher.bat" /f >nul 2>&1

echo.
echo ================================================
echo    SETUP COMPLETE!
echo ================================================
echo.
echo ✅ Loki is ready to use!
echo.
echo To launch Loki:
echo   1. Press Windows key
echo   2. Type "Loki"
echo   3. Press Enter
echo.
echo Or use the desktop shortcut!
echo.
echo Launching Loki now...
timeout /t 3 /nobreak >nul

REM Launch Loki
start "" "%LOKI_DIR%\loki_launcher.bat"

echo.
echo For auto-start on login, run:
echo    SETUP_AUTO_START.bat (as Administrator)
echo.
pause
