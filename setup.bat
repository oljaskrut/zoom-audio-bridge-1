@echo off
setlocal
title Zoom Audio Bridge - Setup

echo ============================================
echo   Zoom Audio Bridge - Setup
echo ============================================
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed.
    echo         Install Python 3.11+ from https://www.python.org/downloads/
    echo         Make sure to check "Add to PATH" during installation.
    goto done
)

echo [OK] Found Python:
python --version
echo.

echo Installing dependencies...
echo This may take a minute, please wait...
echo.
python -m pip install --no-warn-script-location -q -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Failed to install dependencies.
    echo         Check the error messages above.
    goto done
)

echo.
echo ============================================
echo   Setup complete!
echo   Run start.bat to launch the application.
echo ============================================

:done
echo.
pause
