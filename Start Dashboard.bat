@echo off
rem One-click start for Windows: installs what is needed the first time, then opens the dashboard.
setlocal EnableExtensions
cd /d "%~dp0"
title Live Chat Dashboard - keep this window open
if not defined DASHBOARD_PORT set "DASHBOARD_PORT=8501"
set "URL=http://localhost:%DASHBOARD_PORT%"
set "VPY=.venv\Scripts\python.exe"
set "DASHBOARD_BAT=%~f0"
set "DASHBOARD_DIR=%~dp0"

echo ============================================================
echo   Live Chat Dashboard
echo.
echo   Keep this window open while you use the dashboard.
echo   To stop the dashboard, close this window.
echo ============================================================
echo.

rem Already running? Just open it again.
netstat -ano | findstr /r /c:":%DASHBOARD_PORT% .*LISTENING" >nul
if not errorlevel 1 goto already_running

rem 1. Python
if exist "%VPY%" "%VPY%" -c "import sys" >nul 2>nul
if exist "%VPY%" if not errorlevel 1 goto have_venv
if exist ".venv" (
    echo Repairing the .venv folder...
    rmdir /s /q ".venv"
)
call :find_python
if not defined PY call :install_python
if not defined PY goto no_python
echo First-time setup: preparing Python. This takes a minute...
%PY% -m venv .venv
if errorlevel 1 goto fail
if not exist "%VPY%" goto fail

:have_venv
rem 2. Packages - only when requirements.txt changed since the last install
fc /b requirements.txt ".venv\requirements.installed" >nul 2>nul
if not errorlevel 1 goto have_packages
echo.
echo Installing the parts the dashboard needs. The first time this takes 3-10 minutes.
echo Lots of text will scroll by - that is normal. Please wait...
echo.
"%VPY%" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto pip_fail
copy /y requirements.txt ".venv\requirements.installed" >nul

:have_packages
rem 3. Settings file - from the template, with its placeholder passwords left empty
if not exist ".env" if exist "env.template" powershell -NoProfile -ExecutionPolicy Bypass -Command "(Get-Content -Encoding UTF8 env.template) -replace '^([A-Z_]+)=your[-_].*$', '$1=' | Set-Content -Encoding UTF8 .env"

rem 4. Desktop shortcut, once
if exist ".venv\shortcut.done" goto run
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s = (New-Object -ComObject WScript.Shell).CreateShortcut([IO.Path]::Combine([Environment]::GetFolderPath('Desktop'), 'Live Chat Dashboard.lnk')); $s.TargetPath = $env:DASHBOARD_BAT; $s.WorkingDirectory = $env:DASHBOARD_DIR; $s.Save()" >nul 2>nul
if not errorlevel 1 echo A "Live Chat Dashboard" shortcut was added to your desktop.
echo done> ".venv\shortcut.done"

:run
echo.
echo Starting... your browser will open in a moment.
echo If it doesn't, open this address in your browser: %URL%
echo.
rem Opens the browser as soon as the dashboard answers.
start "" /b powershell -NoProfile -ExecutionPolicy Bypass -Command "for ($i = 0; $i -lt 180; $i++) { try { (New-Object Net.Sockets.TcpClient('127.0.0.1', %DASHBOARD_PORT%)).Close(); Start-Process '%URL%'; break } catch { Start-Sleep 1 } }"
"%VPY%" -m streamlit run app.py --server.port %DASHBOARD_PORT% --server.headless true --browser.gatherUsageStats false
echo.
echo The dashboard has stopped. You can close this window.
pause
exit /b 0

:already_running
echo The dashboard is already running. Opening it in your browser...
start "" "%URL%"
timeout /t 5 >nul 2>nul
exit /b 0

:find_python
set "PY="
for %%V in (3.13 3.12 3.14 3.11 3.10) do (
    if not defined PY (
        py -%%V -c "import sys" >nul 2>nul
        if not errorlevel 1 set "PY=py -%%V"
    )
)
if defined PY exit /b 0
python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>nul
if not errorlevel 1 set "PY=python"
if defined PY exit /b 0
for %%V in (313 312 314 311 310) do (
    if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" set PY="%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
)
exit /b 0

:install_python
where winget >nul 2>nul
if errorlevel 1 exit /b 0
echo Python is not installed yet. Installing Python 3.12 - this happens only once.
echo If Windows asks "Do you want to allow this app to make changes", click Yes.
echo.
winget install --id Python.Python.3.12 --exact --scope user --silent --accept-package-agreements --accept-source-agreements
call :find_python
exit /b 0

:no_python
echo.
echo Python could not be installed automatically. Please install it yourself:
echo   1. A web page will open. Click the yellow "Download Python" button and run the file.
echo   2. IMPORTANT: on the first screen, tick "Add python.exe to PATH", then click "Install Now".
echo   3. When it says "Setup was successful", double-click "Start Dashboard" again.
start "" "https://www.python.org/downloads/"
pause
exit /b 1

:pip_fail
echo.
echo Installing the parts failed. Check your internet connection, then double-click
echo "Start Dashboard" again. It continues where it stopped.
pause
exit /b 1

:fail
echo.
echo Setting up Python failed. Delete the ".venv" folder next to this file and try again.
pause
exit /b 1
