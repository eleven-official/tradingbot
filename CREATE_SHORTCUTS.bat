@echo off
REM Create Windows Desktop and Start Menu shortcuts for LOKI Terminal

title LOKI Terminal - Creating Windows Shortcuts
color 0A

echo.
echo  ╔═══════════════════════════════════════════════════════════╗
echo  ║           🔗 CREATING WINDOWS SHORTCUTS FOR LOKI          ║
echo  ╚═══════════════════════════════════════════════════════════╝
echo.

REM Get current directory
set "CURRENT_DIR=%~dp0"
set "CURRENT_DIR=%CURRENT_DIR:~0,-1%"

REM Desktop shortcut
echo 🖥️  Creating desktop shortcut...
powershell -command "& { $WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%USERPROFILE%\Desktop\LOKI Neural Terminal.lnk'); $Shortcut.TargetPath = '%CURRENT_DIR%\LOKI_TERMINAL.bat'; $Shortcut.WorkingDirectory = '%CURRENT_DIR%'; $Shortcut.Description = 'LOKI Neural Trading Terminal - Professional Algorithmic Trading Platform'; $Shortcut.IconLocation = 'C:\Windows\System32\shell32.dll,43'; $Shortcut.Save() }"

if %ERRORLEVEL% EQU 0 (
    echo ✅ Desktop shortcut created successfully
) else (
    echo ❌ Failed to create desktop shortcut
)

REM Start Menu shortcut directory
set "START_MENU_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\LOKI Trading"

REM Create Start Menu directory
echo 📁 Creating Start Menu folder...
if not exist "%START_MENU_DIR%" (
    mkdir "%START_MENU_DIR%"
)

REM Start Menu shortcut
echo 📋 Creating Start Menu shortcut...
powershell -command "& { $WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%START_MENU_DIR%\LOKI Neural Terminal.lnk'); $Shortcut.TargetPath = '%CURRENT_DIR%\LOKI_TERMINAL.bat'; $Shortcut.WorkingDirectory = '%CURRENT_DIR%'; $Shortcut.Description = 'LOKI Neural Trading Terminal'; $Shortcut.IconLocation = 'C:\Windows\System32\shell32.dll,43'; $Shortcut.Save() }"

if %ERRORLEVEL% EQU 0 (
    echo ✅ Start Menu shortcut created successfully
) else (
    echo ❌ Failed to create Start Menu shortcut
)

REM Create documentation shortcut
echo 📚 Creating documentation shortcut...
powershell -command "& { $WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%START_MENU_DIR%\LOKI Documentation.lnk'); $Shortcut.TargetPath = '%CURRENT_DIR%\README_ENHANCED.md'; $Shortcut.WorkingDirectory = '%CURRENT_DIR%'; $Shortcut.Description = 'LOKI Terminal Documentation'; $Shortcut.IconLocation = 'C:\Windows\System32\shell32.dll,23'; $Shortcut.Save() }"

REM Create uninstall shortcut
echo 🗑️  Creating uninstall shortcut...
powershell -command "& { $WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%START_MENU_DIR%\Uninstall LOKI.lnk'); $Shortcut.TargetPath = '%CURRENT_DIR%\UNINSTALL.bat'; $Shortcut.WorkingDirectory = '%CURRENT_DIR%'; $Shortcut.Description = 'Uninstall LOKI Terminal'; $Shortcut.IconLocation = 'C:\Windows\System32\shell32.dll,31'; $Shortcut.Save() }"

echo.
echo ✅ Windows shortcuts created successfully!
echo.
echo 📍 You can now find LOKI Terminal in:
echo    • Desktop shortcut
echo    • Start Menu → LOKI Trading
echo    • Windows Search: type "LOKI"
echo.
echo 🚀 To launch: Double-click desktop shortcut or search "LOKI" in Windows
echo.

pause