@echo off
REM LOKI Neural Trading Terminal - Windows Search Integration
REM This creates registry entries and shortcuts to make "Loki" searchable from Windows Start Menu

echo.
echo ╔══════════════════════════════════════════════════════════════════╗
echo ║                LOKI NEURAL TRADING TERMINAL                      ║
echo ║                    Windows Search Setup                          ║
echo ╚══════════════════════════════════════════════════════════════════╝
echo.

REM Check if running as administrator
net session >nul 2>&1
if %errorLevel% == 0 (
    echo ✅ Running with administrator privileges
) else (
    echo ❌ This script requires administrator privileges
    echo Please right-click and "Run as administrator"
    pause
    exit /b 1
)

echo Setting up Windows Search integration for "Loki"...
echo.

REM Create Start Menu folder
set "START_MENU=%ProgramData%\Microsoft\Windows\Start Menu\Programs\Loki Neural Terminal"
if not exist "%START_MENU%" (
    mkdir "%START_MENU%"
    echo ✅ Created Start Menu folder
)

REM Create desktop shortcut
set "DESKTOP=%PUBLIC%\Desktop"
set "CURRENT_DIR=%~dp0"

REM Create main Loki shortcut
powershell -Command "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%START_MENU%\Loki Neural Terminal.lnk'); $Shortcut.TargetPath = '%CURRENT_DIR%LOKI_NEURAL_TERMINAL.py'; $Shortcut.WorkingDirectory = '%CURRENT_DIR%'; $Shortcut.Description = 'Advanced AI-Powered Trading Terminal'; $Shortcut.IconLocation = 'shell32.dll,137'; $Shortcut.Save()"

REM Create desktop shortcut
powershell -Command "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%DESKTOP%\Loki Neural Terminal.lnk'); $Shortcut.TargetPath = '%CURRENT_DIR%LOKI_NEURAL_TERMINAL.py'; $Shortcut.WorkingDirectory = '%CURRENT_DIR%'; $Shortcut.Description = 'Advanced AI-Powered Trading Terminal'; $Shortcut.IconLocation = 'shell32.dll,137'; $Shortcut.Save()"

REM Create additional searchable shortcuts with different keywords
powershell -Command "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%START_MENU%\Loki Trading Bot.lnk'); $Shortcut.TargetPath = '%CURRENT_DIR%LOKI_NEURAL_TERMINAL.py'; $Shortcut.WorkingDirectory = '%CURRENT_DIR%'; $Shortcut.Description = 'Loki AI Trading Bot'; $Shortcut.Save()"

powershell -Command "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%START_MENU%\Loki AI Terminal.lnk'); $Shortcut.TargetPath = '%CURRENT_DIR%LOKI_NEURAL_TERMINAL.py'; $Shortcut.WorkingDirectory = '%CURRENT_DIR%'; $Shortcut.Description = 'Loki Artificial Intelligence Trading Terminal'; $Shortcut.Save()"

powershell -Command "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%START_MENU%\Loki Dashboard.lnk'); $Shortcut.TargetPath = '%CURRENT_DIR%loki_desktop.py'; $Shortcut.WorkingDirectory = '%CURRENT_DIR%'; $Shortcut.Description = 'Loki Trading Dashboard'; $Shortcut.Save()"

REM Register application for better Windows search
reg add "HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\loki.exe" /ve /t REG_SZ /d "%CURRENT_DIR%LOKI_NEURAL_TERMINAL.py" /f >nul 2>&1
reg add "HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\loki.exe" /v "Path" /t REG_SZ /d "%CURRENT_DIR%" /f >nul 2>&1

REM Add to Windows Search index
reg add "HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows Search\Applications\loki" /v "DisplayName" /t REG_SZ /d "Loki Neural Trading Terminal" /f >nul 2>&1
reg add "HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows Search\Applications\loki" /v "ApplicationName" /t REG_SZ /d "loki.exe" /f >nul 2>&1

REM Create batch launcher for direct execution
echo @echo off > "%CURRENT_DIR%loki.bat"
echo cd /d "%CURRENT_DIR%" >> "%CURRENT_DIR%loki.bat"
echo python LOKI_NEURAL_TERMINAL.py >> "%CURRENT_DIR%loki.bat"

REM Add to system PATH temporarily for this session
set "PATH=%PATH%;%CURRENT_DIR%"

echo.
echo ✅ Windows Search integration completed!
echo.
echo 🔍 You can now search for "Loki" in Windows Start Menu and it will appear:
echo    • "Loki Neural Terminal" - Main application
echo    • "Loki Trading Bot" - Direct bot access  
echo    • "Loki AI Terminal" - AI interface
echo    • "Loki Dashboard" - Desktop dashboard
echo.
echo 🖥️  Desktop shortcut created for quick access
echo.
echo 📝 To test: Press Win key and type "Loki" - the app should appear!
echo.

REM Force Windows to refresh the search index
echo Refreshing Windows search index...
powershell -Command "Get-WmiObject -Class Win32_Process -Filter \"name='SearchIndexer.exe'\" | ForEach-Object { $_.Terminate() }" >nul 2>&1
timeout /t 2 >nul
net start "Windows Search" >nul 2>&1

echo.
echo 🎯 Setup complete! Press Win key and search "Loki" to test.
echo.
pause