@echo off
REM Loki Trading Platform - Auto-Start Setup
REM Makes Loki launch automatically when you unlock your computer
REM Run as Administrator

echo ========================================
echo LOKI AUTO-START CONFIGURATION
echo ========================================
echo.

REM Check for admin privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: Run as Administrator!
    echo Right-click and select "Run as Administrator"
    pause
    exit /b 1
)

set LOKI_DIR=%~dp0
set LOKI_DIR=%LOKI_DIR:~0,-1%

echo [1/4] Creating startup launcher...

REM Create optimized startup script
echo @echo off > "%LOKI_DIR%\loki_startup.bat"
echo REM Loki Auto-Start Script >> "%LOKI_DIR%\loki_startup.bat"
echo cd /d "%LOKI_DIR%" >> "%LOKI_DIR%\loki_startup.bat"
echo. >> "%LOKI_DIR%\loki_startup.bat"
echo REM Wait for Windows to fully load >> "%LOKI_DIR%\loki_startup.bat"
echo timeout /t 10 /nobreak ^>nul >> "%LOKI_DIR%\loki_startup.bat"
echo. >> "%LOKI_DIR%\loki_startup.bat"
echo REM Start Loki Desktop App >> "%LOKI_DIR%\loki_startup.bat"
echo start "" pythonw -m loki.desktop.app >> "%LOKI_DIR%\loki_startup.bat"

echo [2/4] Adding to Windows Startup...

REM Add to Windows Startup folder
set STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
copy /Y "%LOKI_DIR%\loki_startup.bat" "%STARTUP_FOLDER%\Loki-Trading.bat"

echo [3/4] Creating Task Scheduler entry...

REM Create scheduled task for login
schtasks /create /tn "Loki Trading Platform" /tr "\"%LOKI_DIR%\loki_startup.bat\"" /sc onlogon /rl highest /f

echo [4/4] Configuring Windows Search...

REM Register with Windows Search
reg add "HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\App Paths\loki.exe" /ve /t REG_SZ /d "%LOKI_DIR%\loki_launcher.bat" /f
reg add "HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\App Paths\loki.exe" /v "Path" /t REG_SZ /d "%LOKI_DIR%" /f

REM Create launchers if they don't exist
if not exist "%LOKI_DIR%\loki_launcher.bat" (
    echo @echo off > "%LOKI_DIR%\loki_launcher.bat"
    echo cd /d "%LOKI_DIR%" >> "%LOKI_DIR%\loki_launcher.bat"
    echo pythonw -m loki.desktop.app >> "%LOKI_DIR%\loki_launcher.bat"
)

REM Create Start Menu shortcuts
set START_MENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Loki Trading Platform
if not exist "%START_MENU%" mkdir "%START_MENU%"

powershell -Command "$WS = New-Object -ComObject WScript.Shell; $SC = $WS.CreateShortcut('%START_MENU%\Loki Trading.lnk'); $SC.TargetPath = '%LOKI_DIR%\loki_launcher.bat'; $SC.WorkingDirectory = '%LOKI_DIR%'; $SC.Description = 'Loki AI Trading Platform'; $SC.Save()"

REM Create Desktop shortcut
powershell -Command "$WS = New-Object -ComObject WScript.Shell; $SC = $WS.CreateShortcut('%USERPROFILE%\Desktop\Loki Trading.lnk'); $SC.TargetPath = '%LOKI_DIR%\loki_launcher.bat'; $SC.WorkingDirectory = '%LOKI_DIR%'; $SC.Description = 'Loki AI Trading Platform'; $SC.Save()"

echo.
echo ========================================
echo SETUP COMPLETE!
echo ========================================
echo.
echo ✅ Loki will now start automatically when you login!
echo ✅ Search "Loki" in Windows to launch anytime
echo ✅ Desktop shortcut created
echo ✅ Start Menu shortcut added
echo.
echo To test now, restart your computer or run:
echo    %LOKI_DIR%\loki_launcher.bat
echo.
echo To disable auto-start later, run:
echo    schtasks /delete /tn "Loki Trading Platform"
echo.
pause
