@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Streaming Dashboard - Python Desktop

set "PYTHONUTF8=1"
set "VPY=.venv\Scripts\python.exe"

if exist "%VPY%" goto check_venv
if exist ".venv" goto broken_venv

call :find_python
if not defined PY goto no_python

echo Preparing the project Python environment...
%PY% -m venv .venv
if errorlevel 1 goto setup_failed
if not exist "%VPY%" goto setup_failed

:check_venv
"%VPY%" -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>nul
if errorlevel 1 goto broken_venv

fc /b requirements.txt ".venv\desktop-requirements.installed" >nul 2>nul
if not errorlevel 1 (
    "%VPY%" -c "import PySide6" >nul 2>nul
    if not errorlevel 1 goto have_packages
)

echo.
echo Installing the desktop app dependencies. This may take several minutes.
echo.
"%VPY%" -m pip install --disable-pip-version-check -r requirements.txt PySide6
if errorlevel 1 goto pip_failed
copy /y requirements.txt ".venv\desktop-requirements.installed" >nul
if errorlevel 1 goto setup_failed

:have_packages
echo ============================================================
echo   Streaming Dashboard - Python Desktop
echo   Close the app window to exit.
echo ============================================================
echo.
"%VPY%" desktop_app.py %*
if errorlevel 1 (
    echo.
    echo The Python desktop app failed to start. See the error above.
    pause
    exit /b 1
)
exit /b 0

:find_python
set "PY="
for %%V in (3.13 3.12 3.14 3.11 3.10) do (
    if not defined PY (
        py -%%V -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>nul
        if not errorlevel 1 set "PY=py -%%V"
    )
)
if defined PY exit /b 0

python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>nul
if not errorlevel 1 set "PY=python"
if defined PY exit /b 0

for %%V in (313 312 314 311 310) do (
    if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" (
        "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>nul
        if not errorlevel 1 set PY="%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
    )
)
exit /b 0

:no_python
echo Python 3.10 or later was not found. Install Python, then run this launcher again.
echo Download Python from https://www.python.org/downloads/
pause
exit /b 1

:broken_venv
echo The project .venv is missing a working Python 3.10+ interpreter.
echo Repair or recreate .venv, then run this launcher again.
pause
exit /b 1

:pip_failed
echo.
echo Dependency installation failed. Check your internet connection and try again.
pause
exit /b 1

:setup_failed
echo.
echo Python environment setup failed. See the error above.
pause
exit /b 1
