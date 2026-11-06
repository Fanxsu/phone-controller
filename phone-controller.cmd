@echo off
setlocal
set PYTHONUTF8=1

where python >nul 2>nul
if not errorlevel 1 (
    python "%~dp0phone_controller.py" %*
    exit /b %errorlevel%
)

where py >nul 2>nul
if not errorlevel 1 (
    py -3 "%~dp0phone_controller.py" %*
    exit /b %errorlevel%
)

echo phone-controller: Python 3 not found. Install Python 3.9+ and retry. 1>&2
exit /b 1
