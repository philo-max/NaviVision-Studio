@echo off
title NaviVision Studio - Launcher

echo ==========================================================
echo       NaviVision Studio (OpenDevelop) Vision Platform
echo ==========================================================
echo [INFO] Starting Web IDE Server at http://127.0.0.1:8080 ...
echo [INFO] Opening default browser...
echo.

if exist "%~dp0NaviVision_Studio" (
    cd /d "%~dp0NaviVision_Studio"
) else (
    cd /d "%~dp0"
)

REM Verify Python environment
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python was not found in PATH!
    echo Please ensure Python 3.10+ is installed and added to system PATH.
    pause
    exit /b 1
)

REM Launch browser
start http://127.0.0.1:8080

REM Start FastAPI application
python app.py

pause
