@echo off
REM LOKI - Launch Enhanced Trading Platform
REM All-in-one launcher with advanced features

echo.
echo ================================================================
echo    🚀 LOKI ENHANCED TRADING PLATFORM
echo    Revolutionary AI Trading with Advanced Analytics
echo ================================================================
echo.

set LOKI_DIR=%~dp0
set LOKI_DIR=%LOKI_DIR:~0,-1%

cd /d "%LOKI_DIR%"

echo Select which module to launch:
echo.
echo [1] Ultra-Modern Dashboard (Complete Trading Interface)
echo [2] Advanced Charting (TradingView-Style Charts)
echo [3] AI Explanation Panel (Live Reasoning Visualization)
echo [4] Performance Analytics (Equity, Drawdown, Sharpe)
echo [5] Portfolio Optimization (Efficient Frontier, Allocation)
echo [6] Test All Modules
echo [7] Exit
echo.

choice /c 1234567 /n /m "Choose [1-7]: "

if errorlevel 7 goto :end
if errorlevel 6 goto :test_all
if errorlevel 5 goto :launch_optimization
if errorlevel 4 goto :launch_analytics
if errorlevel 3 goto :launch_explanation
if errorlevel 2 goto :launch_charting
if errorlevel 1 goto :launch_dashboard

:launch_dashboard
echo.
echo 🚀 Launching Ultra-Modern Dashboard...
echo.
python -c "from loki.desktop.ultra_modern_ui import main; main()"
goto :end

:launch_charting
echo.
echo 📈 Launching Advanced Charting...
echo.
python -c "from loki.desktop.advanced_charting import main; main()"
goto :end

:launch_explanation
echo.
echo 🧠 Launching AI Explanation Panel...
echo.
python -c "from loki.desktop.ai_explanation_panel import main; main()"
goto :end

:launch_analytics
echo.
echo 📊 Launching Performance Analytics...
echo.
python -c "from loki.desktop.performance_analytics import main; main()"
goto :end

:launch_optimization
echo.
echo 💎 Launching Portfolio Optimization...
echo.
python -c "from loki.desktop.portfolio_optimization import main; main()"
goto :end

:test_all
echo.
echo 🧪 Testing All Modules...
echo.
echo [1/5] Testing Market Analyzer...
python -c "from loki.ai.advanced_market_analyzer import AdvancedMarketAnalyzer; print('✓ Market Analyzer OK')" 2>nul || echo "✗ Market Analyzer FAILED"

echo [2/5] Testing Strategies...
python -c "from loki.ai.sophisticated_strategies import StrategyManager; print('✓ Strategies OK')" 2>nul || echo "✗ Strategies FAILED"

echo [3/5] Testing Notifications...
python -c "from loki.core.smart_notifications import SmartNotificationSystem; print('✓ Notifications OK')" 2>nul || echo "✗ Notifications FAILED"

echo [4/5] Testing UI Modules...
python -c "from loki.desktop.ultra_modern_ui import LokiUltraModernUI; print('✓ Ultra-Modern UI OK')" 2>nul || echo "✗ UI FAILED"

echo [5/5] Testing Charts...
python -c "from loki.desktop.advanced_charting import TradingViewChart; print('✓ Advanced Charting OK')" 2>nul || echo "✗ Charting FAILED"

echo.
echo ✓ All tests complete!
echo.
pause
goto :end

:end
echo.
echo Thank you for using Loki Trading Platform!
echo.
