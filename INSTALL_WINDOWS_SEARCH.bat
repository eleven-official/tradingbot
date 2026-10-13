@echo off
REM Loki Trading Platform - Windows Search Integration
REM Makes Loki searchable from Windows Start Menu
REM Run as Administrator for full integration

echo ========================================
echo LOKI TRADING PLATFORM
echo Windows Search Integration Installer
echo ========================================
echo.

REM Check for admin privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: This script requires Administrator privileges!
    echo Please right-click and select "Run as Administrator"
    echo.
    pause
    exit /b 1
)

echo [1/5] Creating Loki application shortcuts...

REM Get current directory
set LOKI_DIR=%~dp0
set LOKI_DIR=%LOKI_DIR:~0,-1%

REM Create Start Menu folder
set START_MENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Loki Trading Platform
if not exist "%START_MENU%" mkdir "%START_MENU%"

echo [2/5] Registering with Windows...

REM Register application path for Windows Search
reg add "HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\App Paths\loki.exe" /ve /t REG_SZ /d "%LOKI_DIR%\loki_launcher.bat" /f
reg add "HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\App Paths\loki.exe" /v "Path" /t REG_SZ /d "%LOKI_DIR%" /f

echo [3/5] Creating launcher scripts...

REM Create Python launcher for Loki Desktop
echo @echo off > "%LOKI_DIR%\loki_launcher.bat"
echo cd /d "%LOKI_DIR%" >> "%LOKI_DIR%\loki_launcher.bat"
echo python -m loki.desktop.app >> "%LOKI_DIR%\loki_launcher.bat"

REM Create API server launcher
echo @echo off > "%LOKI_DIR%\loki_api_launcher.bat"
echo cd /d "%LOKI_DIR%" >> "%LOKI_DIR%\loki_api_launcher.bat"
echo uvicorn loki.api.server:app --host 0.0.0.0 --port 8000 >> "%LOKI_DIR%\loki_api_launcher.bat"

REM Create AI Agent launcher
echo @echo off > "%LOKI_DIR%\loki_ai_launcher.bat"
echo cd /d "%LOKI_DIR%" >> "%LOKI_DIR%\loki_ai_launcher.bat"
echo python -m loki.ai.autonomous_agent >> "%LOKI_DIR%\loki_ai_launcher.bat"

echo [4/5] Creating Start Menu shortcuts...

REM Create shortcuts with PowerShell
powershell -Command "$WS = New-Object -ComObject WScript.Shell; $SC = $WS.CreateShortcut('%START_MENU%\Loki Trading Platform.lnk'); $SC.TargetPath = '%LOKI_DIR%\loki_launcher.bat'; $SC.WorkingDirectory = '%LOKI_DIR%'; $SC.Description = 'Loki AI Trading Platform - Desktop App'; $SC.Save()"

powershell -Command "$WS = New-Object -ComObject WScript.Shell; $SC = $WS.CreateShortcut('%START_MENU%\Loki API Server.lnk'); $SC.TargetPath = '%LOKI_DIR%\loki_api_launcher.bat'; $SC.WorkingDirectory = '%LOKI_DIR%'; $SC.Description = 'Loki API Server'; $SC.Save()"

powershell -Command "$WS = New-Object -ComObject WScript.Shell; $SC = $WS.CreateShortcut('%START_MENU%\Loki AI Agent.lnk'); $SC.TargetPath = '%LOKI_DIR%\loki_ai_launcher.bat'; $SC.WorkingDirectory = '%LOKI_DIR%'; $SC.Description = 'Loki Autonomous AI Trading Agent'; $SC.Save()"

powershell -Command "$WS = New-Object -ComObject WScript.Shell; $SC = $WS.CreateShortcut('%START_MENU%\Loki Documentation.lnk'); $SC.TargetPath = '%LOKI_DIR%\MASTER_README.md'; $SC.WorkingDirectory = '%LOKI_DIR%'; $SC.Description = 'Loki Documentation'; $SC.Save()"

REM Create desktop shortcut
powershell -Command "$WS = New-Object -ComObject WScript.Shell; $SC = $WS.CreateShortcut('%USERPROFILE%\Desktop\Loki Trading.lnk'); $SC.TargetPath = '%LOKI_DIR%\loki_launcher.bat'; $SC.WorkingDirectory = '%LOKI_DIR%'; $SC.Description = 'Loki AI Trading Platform'; $SC.Save()"

echo [5/5] Finalizing installation...

REM Add to Windows Search index
reg add "HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Search\JumpListData" /v "Loki" /t REG_SZ /d "%START_MENU%\Loki Trading Platform.lnk" /f

REM Refresh icon cache
ie4uinit.exe -show

echo.
echo ========================================
echo INSTALLATION COMPLETE!
echo ========================================
echo.
echo Loki is now installed and searchable!
echo.
echo To launch Loki:
echo   1. Press Windows key
echo   2. Type "Loki"
echo   3. Press Enter
echo.
echo Or use these commands:
echo   - Desktop App:    %LOKI_DIR%\loki_launcher.bat
echo   - API Server:     %LOKI_DIR%\loki_api_launcher.bat
echo   - AI Agent:       %LOKI_DIR%\loki_ai_launcher.bat
echo.
echo Check Start Menu ^> Loki Trading Platform for all options
echo.
pause
