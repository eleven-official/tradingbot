@echo off
REM LOKI Terminal Uninstaller
REM Removes shortcuts and optionally deletes application files

title LOKI Terminal - Uninstaller
color 0C

echo.
echo  ╔═══════════════════════════════════════════════════════════╗
echo  ║              🗑️  LOKI TERMINAL UNINSTALLER               ║
echo  ╚═══════════════════════════════════════════════════════════╝
echo.

echo ⚠️  This will remove LOKI Terminal shortcuts and optionally delete files.
echo.
set /p CONFIRM=Are you sure you want to uninstall? (y/N): 

if /i not "%CONFIRM%"=="y" (
    echo ❌ Uninstall cancelled.
    pause
    exit /b 0
)

echo.
echo 🗑️  Removing shortcuts...

REM Remove desktop shortcut
if exist "%USERPROFILE%\Desktop\LOKI Neural Terminal.lnk" (
    del "%USERPROFILE%\Desktop\LOKI Neural Terminal.lnk"
    echo ✅ Desktop shortcut removed
)

REM Remove Start Menu folder
set "START_MENU_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\LOKI Trading"
if exist "%START_MENU_DIR%" (
    rmdir /s /q "%START_MENU_DIR%"
    echo ✅ Start Menu shortcuts removed
)

echo.
echo 🗂️  Shortcuts removed successfully.
echo.
set /p DELETE_FILES=Do you want to delete application files too? (y/N): 

if /i "%DELETE_FILES%"=="y" (
    echo.
    echo ⚠️  WARNING: This will delete ALL LOKI files in this directory!
    set /p FINAL_CONFIRM=Type YES to confirm deletion: 
    
    if "!FINAL_CONFIRM!"=="YES" (
        echo 🗑️  Deleting application files...
        cd ..
        rmdir /s /q "tradingbot"
        echo ✅ Application files deleted
    ) else (
        echo ❌ File deletion cancelled - only shortcuts were removed
    )
) else (
    echo 📁 Application files kept - only shortcuts were removed
)

echo.
echo ✅ Uninstall complete!
echo.
pause