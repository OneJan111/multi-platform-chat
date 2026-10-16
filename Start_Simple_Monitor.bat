@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Live Chat Monitor - keep this window open

set "PYTHONUTF8=1"
set "PYTHON=python"
if exist ".venv\Scripts\python.exe" set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not defined SIMPLE_MONITOR_PORT set "SIMPLE_MONITOR_PORT=8501"

"%PYTHON%" -c "import streamlit" >nul 2>nul
if errorlevel 1 (
    echo Python or Streamlit is missing. Complete the setup in README.md first.
    echo Install dependencies with: python -m pip install -r requirements.txt
    pause
    exit /b 1
)

echo ============================================================
echo   Live Chat Monitor
echo   Keep this window open while using the monitor.
echo   Press Ctrl+C to stop.
echo   Browser address: http://localhost:%SIMPLE_MONITOR_PORT%
echo ============================================================
echo.
"%PYTHON%" -m streamlit run simple_app.py --server.port "%SIMPLE_MONITOR_PORT%" --server.headless false --browser.gatherUsageStats false %*
if errorlevel 1 (
    echo.
    echo The monitor failed to start. See the error above.
    pause
    exit /b 1
)
exit /b 0
