@echo off
REM ========================================================================
REM LOKI v7.0 Enterprise - Windows Shortcuts Creator
REM Creates desktop and Start Menu shortcuts for LOKI
REM ========================================================================

echo.
echo ╔══════════════════════════════════════════════════════════════════╗
echo ║                  LOKI v7.0 ENTERPRISE                            ║
echo ║              Windows Shortcuts Installation                       ║
echo ╚══════════════════════════════════════════════════════════════════╝
echo.

REM Get current directory
set "CURRENT_DIR=%~dp0"
set "USER_START_MENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs"
set "DESKTOP=%USERPROFILE%\Desktop"

echo Creating LOKI shortcuts for Windows...
echo.

REM Create LOKI folder in Start Menu
if not exist "%USER_START_MENU%\LOKI" (
    mkdir "%USER_START_MENU%\LOKI"
)

REM Create main LOKI shortcuts
echo [1/5] Creating main LOKI shortcut...
powershell -Command "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%USER_START_MENU%\LOKI\LOKI.lnk'); $Shortcut.TargetPath = 'python'; $Shortcut.Arguments = '%CURRENT_DIR%LOKI_NEURAL_TERMINAL.py'; $Shortcut.WorkingDirectory = '%CURRENT_DIR%'; $Shortcut.Description = 'LOKI v7.0 - Enterprise Trading Platform'; $Shortcut.Save()"

echo [2/5] Creating LOKI Trading shortcut...
powershell -Command "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%USER_START_MENU%\LOKI\LOKI Trading.lnk'); $Shortcut.TargetPath = 'python'; $Shortcut.Arguments = '%CURRENT_DIR%LOKI_NEURAL_TERMINAL.py'; $Shortcut.WorkingDirectory = '%CURRENT_DIR%'; $Shortcut.Description = 'LOKI v7.0 Enterprise'; $Shortcut.Save()"

echo [3/5] Creating LOKI AI Platform shortcut...
powershell -Command "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%USER_START_MENU%\LOKI\LOKI AI Platform.lnk'); $Shortcut.TargetPath = 'python'; $Shortcut.Arguments = '%CURRENT_DIR%LOKI_NEURAL_TERMINAL.py'; $Shortcut.WorkingDirectory = '%CURRENT_DIR%'; $Shortcut.Description = 'LOKI v7.0 - AI Trading Platform'; $Shortcut.Save()"

REM Create desktop shortcut
echo [4/5] Creating desktop shortcut...
powershell -Command "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%DESKTOP%\LOKI.lnk'); $Shortcut.TargetPath = 'python'; $Shortcut.Arguments = '%CURRENT_DIR%LOKI_NEURAL_TERMINAL.py'; $Shortcut.WorkingDirectory = '%CURRENT_DIR%'; $Shortcut.Description = 'LOKI v7.0 - Enterprise Trading Platform'; $Shortcut.Save()"

REM Create direct shortcut in Start Menu root for better search
echo [5/5] Creating Windows Search shortcut...
powershell -Command "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%USER_START_MENU%\LOKI.lnk'); $Shortcut.TargetPath = 'python'; $Shortcut.Arguments = '%CURRENT_DIR%LOKI_NEURAL_TERMINAL.py'; $Shortcut.WorkingDirectory = '%CURRENT_DIR%'; $Shortcut.Description = 'LOKI v7.0 Enterprise - Auto-updating Platform'; $Shortcut.Save()"

echo.
echo ╔══════════════════════════════════════════════════════════════════╗
echo ║                    ✅ INSTALLATION COMPLETE!                     ║
echo ╚══════════════════════════════════════════════════════════════════╝
echo.
echo 📍 LOKI v7.0 is now available in:
echo    • Desktop shortcut: "LOKI"
echo    • Start Menu → LOKI folder
echo    • Windows Search: type "LOKI"
echo.
echo 🚀 To launch:
echo    • Click desktop "LOKI" icon
echo    • Press Win key + type "LOKI"
echo    • Click any Start Menu shortcut
echo.
echo 🎯 All shortcuts auto-update to latest version!
echo.
pause
