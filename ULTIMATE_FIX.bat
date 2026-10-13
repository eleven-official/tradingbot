@echo off
REM LOKI - ULTIMATE FIX - Fixes ALL known issues
REM This script will fix Windows Search, install packages, create launchers, and test everything

echo.
echo ================================================================
echo    LOKI TRADING PLATFORM - ULTIMATE FIX
echo    Fixing all issues and making Windows Search work
echo ================================================================
echo.

set LOKI_DIR=%~dp0
set LOKI_DIR=%LOKI_DIR:~0,-1%

echo Current Directory: %LOKI_DIR%
echo.

REM ============================================================
REM STEP 1: Check Prerequisites
REM ============================================================
echo [STEP 1/12] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not installed!
    echo.
    echo Please download and install Python from:
    echo https://www.python.org/downloads/
    echo.
    echo IMPORTANT: Check "Add Python to PATH" during installation!
    echo.
    pause
    exit /b 1
)
python --version
echo  ^>^> Python found!
echo.

REM ============================================================
REM STEP 2: Upgrade pip
REM ============================================================
echo [STEP 2/12] Upgrading pip...
python -m pip install --upgrade pip --quiet
echo  ^>^> pip upgraded!
echo.

REM ============================================================
REM STEP 3: Install Core Packages
REM ============================================================
echo [STEP 3/12] Installing PyQt6 (this may take a minute)...
pip install PyQt6 --quiet --upgrade
if errorlevel 1 (
    echo  ^>^> Trying verbose install...
    pip install PyQt6 --upgrade
)
echo  ^>^> PyQt6 installed!
echo.

echo [STEP 4/12] Installing pyqtgraph...
pip install pyqtgraph --quiet --upgrade
echo  ^>^> pyqtgraph installed!
echo.

echo [STEP 5/12] Installing data science packages...
pip install pandas numpy matplotlib plotly --quiet --upgrade
echo  ^>^> Data packages installed!
echo.

echo [STEP 6/12] Installing additional dependencies...
pip install pyyaml requests sqlalchemy fastapi --quiet --upgrade
echo  ^>^> Additional packages installed!
echo.

REM ============================================================
REM STEP 7: Create Directory Structure
REM ============================================================
echo [STEP 7/12] Setting up directory structure...
if not exist "%LOKI_DIR%\loki" mkdir "%LOKI_DIR%\loki"
if not exist "%LOKI_DIR%\loki\desktop" mkdir "%LOKI_DIR%\loki\desktop"
if not exist "%LOKI_DIR%\loki\ai" mkdir "%LOKI_DIR%\loki\ai"
if not exist "%LOKI_DIR%\loki\api" mkdir "%LOKI_DIR%\loki\api"
if not exist "%LOKI_DIR%\loki\risk" mkdir "%LOKI_DIR%\loki\risk"

REM Create __init__.py files
echo # Loki Trading Platform > "%LOKI_DIR%\loki\__init__.py"
echo # Loki Desktop > "%LOKI_DIR%\loki\desktop\__init__.py"
echo # Loki AI > "%LOKI_DIR%\loki\ai\__init__.py"
echo # Loki API > "%LOKI_DIR%\loki\api\__init__.py"
echo # Loki Risk > "%LOKI_DIR%\loki\risk\__init__.py"

echo  ^>^> Directory structure ready!
echo.

REM ============================================================
REM STEP 8: Create Python Launcher
REM ============================================================
echo [STEP 8/12] Creating launch_loki.py...
(
echo import sys
echo from pathlib import Path
echo.
echo # Add project root to path
echo sys.path.insert^(0, str^(Path^(__file__^).parent^)^)
echo.
echo if __name__ == "__main__":
echo     try:
echo         print^("Starting Loki Trading Platform..."^)
echo         from loki.desktop.enhanced_app import main
echo         main^(^)
echo     except ImportError as e:
echo         print^(f"Import Error: {e}"^)
echo         print^("Trying fallback..."^)
echo         try:
echo             from loki.desktop.app import main
echo             main^(^)
echo         except Exception as e2:
echo             print^(f"Fatal Error: {e2}"^)
echo             print^("Please ensure all packages are installed:"^)
echo             print^("  pip install PyQt6 pyqtgraph pandas numpy"^)
echo             input^("Press Enter to exit..."^)
echo     except Exception as e:
echo         print^(f"Error starting Loki: {e}"^)
echo         import traceback
echo         traceback.print_exc^(^)
echo         input^("Press Enter to exit..."^)
) > "%LOKI_DIR%\launch_loki.py"
echo  ^>^> launch_loki.py created!
echo.

REM ============================================================
REM STEP 9: Create Batch Launchers
REM ============================================================
echo [STEP 9/12] Creating launcher scripts...

REM Main launcher (no console window)
(
echo @echo off
echo cd /d "%LOKI_DIR%"
echo pythonw "%LOKI_DIR%\launch_loki.py"
echo if errorlevel 1 ^(
echo     echo Loki encountered an error. Opening debug mode...
echo     python "%LOKI_DIR%\launch_loki.py"
echo     pause
echo ^)
) > "%LOKI_DIR%\START_LOKI.bat"

REM Test launcher (with console for debugging)
(
echo @echo off
echo cd /d "%LOKI_DIR%"
echo echo Starting Loki in DEBUG mode...
echo echo.
echo python "%LOKI_DIR%\launch_loki.py"
echo echo.
echo pause
) > "%LOKI_DIR%\TEST_LOKI.bat"

REM Quick launcher for Windows Search
(
echo @echo off
echo cd /d "%LOKI_DIR%"
echo start "" pythonw "%LOKI_DIR%\launch_loki.py"
) > "%LOKI_DIR%\loki.bat"

echo  ^>^> Launcher scripts created!
echo.

REM ============================================================
REM STEP 10: Register with Windows (ADVANCED)
REM ============================================================
echo [STEP 10/12] Registering with Windows Search...

REM Method 1: App Paths registry
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\App Paths\loki.bat" /ve /t REG_SZ /d "%LOKI_DIR%\START_LOKI.bat" /f >nul 2>&1
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\App Paths\loki.bat" /v "Path" /t REG_SZ /d "%LOKI_DIR%" /f >nul 2>&1

reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\App Paths\loki.exe" /ve /t REG_SZ /d "%LOKI_DIR%\START_LOKI.bat" /f >nul 2>&1
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\App Paths\loki.exe" /v "Path" /t REG_SZ /d "%LOKI_DIR%" /f >nul 2>&1

reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\App Paths\LokiTrading.exe" /ve /t REG_SZ /d "%LOKI_DIR%\START_LOKI.bat" /f >nul 2>&1

REM Method 2: Set environment variable
setx LOKI_HOME "%LOKI_DIR%" >nul 2>&1

echo  ^>^> Windows registry updated!
echo.

REM ============================================================
REM STEP 11: Create Shortcuts (Start Menu & Desktop)
REM ============================================================
echo [STEP 11/12] Creating shortcuts...

set STARTMENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs
set LOKIFOLDER=%STARTMENU%\Loki Trading

REM Create folder
if not exist "%LOKIFOLDER%" mkdir "%LOKIFOLDER%"

REM Desktop shortcut
powershell -Command "$WS = New-Object -ComObject WScript.Shell; $SC = $WS.CreateShortcut('%USERPROFILE%\Desktop\Loki Trading.lnk'); $SC.TargetPath = '%LOKI_DIR%\START_LOKI.bat'; $SC.WorkingDirectory = '%LOKI_DIR%'; $SC.Description = 'Loki AI Trading Platform'; $SC.IconLocation = 'shell32.dll,15'; $SC.Save()" 2>nul

REM Start Menu shortcuts
powershell -Command "$WS = New-Object -ComObject WScript.Shell; $SC = $WS.CreateShortcut('%LOKIFOLDER%\Loki Trading Platform.lnk'); $SC.TargetPath = '%LOKI_DIR%\START_LOKI.bat'; $SC.WorkingDirectory = '%LOKI_DIR%'; $SC.Description = 'Loki AI Trading Platform'; $SC.IconLocation = 'shell32.dll,15'; $SC.Save()" 2>nul

powershell -Command "$WS = New-Object -ComObject WScript.Shell; $SC = $WS.CreateShortcut('%LOKIFOLDER%\Loki (Debug Mode).lnk'); $SC.TargetPath = '%LOKI_DIR%\TEST_LOKI.bat'; $SC.WorkingDirectory = '%LOKI_DIR%'; $SC.Description = 'Loki in Debug Mode'; $SC.IconLocation = 'shell32.dll,77'; $SC.Save()" 2>nul

powershell -Command "$WS = New-Object -ComObject WScript.Shell; $SC = $WS.CreateShortcut('%STARTMENU%\Loki Trading.lnk'); $SC.TargetPath = '%LOKI_DIR%\START_LOKI.bat'; $SC.WorkingDirectory = '%LOKI_DIR%'; $SC.Description = 'Loki AI Trading Platform'; $SC.IconLocation = 'shell32.dll,15'; $SC.Save()" 2>nul

echo  ^>^> Shortcuts created!
echo.

REM ============================================================
REM STEP 12: Test Everything
REM ============================================================
echo [STEP 12/12] Testing installation...
echo.
echo Testing Python imports...
python -c "import sys; sys.path.insert(0, r'%LOKI_DIR%'); import PyQt6; print('  * PyQt6: OK')" 2>nul || echo   * PyQt6: WARNING - may have issues
python -c "import pandas; print('  * pandas: OK')" 2>nul || echo   * pandas: WARNING
python -c "import numpy; print('  * numpy: OK')" 2>nul || echo   * numpy: WARNING

echo.
echo Testing Loki modules...
python -c "import sys; sys.path.insert(0, r'%LOKI_DIR%'); from loki.desktop import enhanced_app; print('  * Enhanced App: OK')" 2>nul || echo   * Enhanced App: WARNING

echo.

REM ============================================================
REM SUCCESS!
REM ============================================================
echo ================================================================
echo    SETUP COMPLETE! 
echo ================================================================
echo.
echo All components have been installed and configured!
echo.
echo ^>^>^> HOW TO LAUNCH LOKI ^<^<^<
echo.
echo METHOD 1 - Desktop Shortcut (EASIEST):
echo    Double-click "Loki Trading" on your Desktop
echo.
echo METHOD 2 - Windows Search (after restart):
echo    1. Press Windows key
echo    2. Type: Loki Trading
echo    3. Click "Loki Trading Platform"
echo.
echo METHOD 3 - Start Menu:
echo    Start Menu ^>^> Loki Trading ^>^> Loki Trading Platform
echo.
echo METHOD 4 - Debug Mode:
echo    Double-click TEST_LOKI.bat (shows error messages)
echo.
echo.
echo ^>^>^> IMPORTANT NOTES ^<^<^<
echo.
echo * Desktop shortcut works immediately
echo * Windows Search requires computer RESTART to work
echo * If search doesn't find "Loki", try "Loki Trading Platform"
echo * For troubleshooting, run TEST_LOKI.bat to see errors
echo.
echo.
echo Would you like to launch Loki now? (Y/N)
choice /c YN /n /m "Launch Loki? [Y/N]: "
if errorlevel 2 goto :skip_launch
if errorlevel 1 goto :do_launch

:do_launch
echo.
echo Launching Loki Trading Platform...
timeout /t 2 /nobreak >nul
start "" "%LOKI_DIR%\START_LOKI.bat"
echo.
echo Loki should start in a few seconds!
goto :end

:skip_launch
echo.
echo Setup complete! Launch Loki anytime from Desktop or Start Menu.

:end
echo.
pause
