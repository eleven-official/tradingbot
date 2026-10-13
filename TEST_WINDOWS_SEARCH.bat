@echo off
REM Test Windows Search Registration for Loki

echo.
echo ========================================================
echo    TESTING WINDOWS SEARCH REGISTRATION
echo ========================================================
echo.

set LOKI_DIR=%~dp0
set LOKI_DIR=%LOKI_DIR:~0,-1%

echo Checking registry entries...
echo.

echo [Test 1] Checking App Paths for loki.bat...
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\App Paths\loki.bat" 2>nul
if errorlevel 1 (
    echo  X NOT FOUND
    set FAIL1=1
) else (
    echo  + FOUND
    set FAIL1=0
)
echo.

echo [Test 2] Checking App Paths for loki...
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\App Paths\loki" 2>nul
if errorlevel 1 (
    echo  X NOT FOUND
    set FAIL2=1
) else (
    echo  + FOUND
    set FAIL2=0
)
echo.

echo [Test 3] Checking Desktop shortcut...
if exist "%USERPROFILE%\Desktop\Loki Trading.lnk" (
    echo  + FOUND: Loki Trading.lnk
    set FAIL3=0
) else (
    echo  X NOT FOUND
    set FAIL3=1
)
echo.

echo [Test 4] Checking Start Menu shortcuts...
set STARTMENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs
if exist "%STARTMENU%\Loki Trading.lnk" (
    echo  + FOUND: Start Menu shortcut
    set FAIL4=0
) else (
    if exist "%STARTMENU%\Loki Trading\Loki Trading Platform.lnk" (
        echo  + FOUND: Start Menu folder shortcut
        set FAIL4=0
    ) else (
        echo  X NOT FOUND
        set FAIL4=1
    )
)
echo.

echo [Test 5] Checking launcher files...
if exist "%LOKI_DIR%\START_LOKI.bat" (
    echo  + FOUND: START_LOKI.bat
) else (
    echo  X MISSING: START_LOKI.bat
)

if exist "%LOKI_DIR%\TEST_LOKI.bat" (
    echo  + FOUND: TEST_LOKI.bat
) else (
    echo  X MISSING: TEST_LOKI.bat
)

if exist "%LOKI_DIR%\launch_loki.py" (
    echo  + FOUND: launch_loki.py
) else (
    echo  X MISSING: launch_loki.py
)
echo.

echo [Test 6] Checking Python imports...
python -c "import sys; sys.path.insert(0, r'%LOKI_DIR%'); import PyQt6" 2>nul
if errorlevel 1 (
    echo  X PyQt6 NOT installed or not working
    set FAIL6=1
) else (
    echo  + PyQt6 works
    set FAIL6=0
)

python -c "import sys; sys.path.insert(0, r'%LOKI_DIR%'); from loki.desktop import enhanced_app" 2>nul
if errorlevel 1 (
    echo  X Loki modules NOT found
    set FAIL7=1
) else (
    echo  + Loki modules load correctly
    set FAIL7=0
)
echo.

echo ========================================================
echo    TEST RESULTS
echo ========================================================
echo.

set /a "TOTAL_FAILS=%FAIL1% + %FAIL2% + %FAIL3% + %FAIL4% + %FAIL6% + %FAIL7%"

if %TOTAL_FAILS%==0 (
    echo  ALL TESTS PASSED!
    echo.
    echo  Loki is properly configured!
    echo.
    echo  HOW TO USE WINDOWS SEARCH:
    echo  1. Press Windows key
    echo  2. Type: Loki Trading
    echo  3. Click "Loki Trading Platform"
    echo.
    echo  NOTE: If search doesn't find it yet:
    echo  - Restart your computer ^(Windows needs to update search index^)
    echo  - OR wait 5-10 minutes for automatic indexing
    echo  - OR use Desktop shortcut ^(works immediately^)
) else (
    echo  %TOTAL_FAILS% TESTS FAILED
    echo.
    echo  RECOMMENDED ACTION:
    echo  Run ULTIMATE_FIX.bat to fix all issues
)

echo.
echo ========================================================
echo.

echo Would you like to:
echo  [1] Launch Loki now
echo  [2] Run ULTIMATE_FIX.bat to repair
echo  [3] Exit
echo.

choice /c 123 /n /m "Choose [1,2,3]: "

if errorlevel 3 goto :end
if errorlevel 2 goto :run_fix
if errorlevel 1 goto :launch

:launch
echo.
echo Launching Loki...
start "" "%LOKI_DIR%\START_LOKI.bat"
goto :end

:run_fix
echo.
echo Running ULTIMATE_FIX.bat...
call "%LOKI_DIR%\ULTIMATE_FIX.bat"
goto :end

:end
echo.
pause
