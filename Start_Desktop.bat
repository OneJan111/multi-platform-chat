@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Streaming Dashboard - Python Desktop

set "PYTHONUTF8=1"
set "PYTHON=python"
if exist ".venv\Scripts\python.exe" set "PYTHON=%~dp0.venv\Scripts\python.exe"

"%PYTHON%" -c "import sys" >nul 2>nul
if errorlevel 1 (
    echo Python was not found. Install Python 3.10 or later and try again.
    pause
    exit /b 1
)

"%PYTHON%" -c "import PySide6" >nul 2>nul
if errorlevel 1 (
    echo PySide6 is required for the Python desktop app.
    echo Install it with:
    echo   "%PYTHON%" -m pip install PySide6
    pause
    exit /b 1
)

echo ============================================================
echo   Streaming Dashboard - Python Desktop
echo   Close the app window to exit.
echo ============================================================
echo.
"%PYTHON%" desktop_app.py
if errorlevel 1 (
    echo.
    echo The Python desktop app failed to start. See the error above.
    pause
    exit /b 1
)
exit /b 0
