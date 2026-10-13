@echo off
echo ========================================
echo Australian Crypto Trading Bot Installer
echo ========================================
echo.

echo [1/4] Checking Python installation...
python --version
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8 or higher from https://python.org
    pause
    exit /b 1
)

echo.
echo [2/4] Installing required packages...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)

echo.
echo [3/4] Creating configuration files...
if not exist config.yaml (
    echo Creating config.yaml from example...
    copy config.example.yaml config.yaml
)

if not exist .env (
    echo Creating .env file...
    echo CRYPTO_API_KEY=your_api_key_here > .env
    echo CRYPTO_API_SECRET=your_api_secret_here >> .env
    echo GOOGLE_API_KEY=your_google_api_key_here >> .env
    echo NEWS_API_KEY=your_news_api_key_here >> .env
    echo IMPORTANT: Edit .env file with your actual API keys
)

echo.
echo [4/4] Creating output directories...
if not exist output mkdir output
if not exist state mkdir state

echo.
echo ========================================
echo Installation Complete!
echo ========================================
echo.
echo Next Steps:
echo 1. Edit .env file with your API keys
echo 2. Edit config.yaml with your preferences
echo 3. Run: python desktop_app.py
echo.
echo For detailed instructions, see FINAL_GUIDE.md
echo.
pause