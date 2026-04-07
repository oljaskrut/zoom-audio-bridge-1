@echo off
setlocal
title Zoom Audio Bridge - Setup

set PYTHON_VERSION=3.12.8
set PYTHON_DIR=python
set PYTHON=%PYTHON_DIR%\tools\python.exe

echo ============================================
echo   Zoom Audio Bridge - Setup
echo ============================================
echo.

if exist %PYTHON% (
    echo [OK] Python %PYTHON_VERSION% is already installed.
    echo.
    goto install_deps
)

echo [1/3] Downloading Python %PYTHON_VERSION% ...
echo      This may take a minute, please wait...
echo.
curl -L -o python.nupkg https://www.nuget.org/api/v2/package/python/%PYTHON_VERSION%
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Failed to download Python.
    echo         Check your internet connection and try again.
    goto done
)

echo [2/3] Extracting Python...
mkdir %PYTHON_DIR% 2>nul
tar -xf python.nupkg -C %PYTHON_DIR%
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Failed to extract Python.
    goto done
)
del python.nupkg
echo      Done.
echo.

:install_deps
echo [3/3] Installing dependencies...
echo      This may take a minute, please wait...
echo.
%PYTHON% -m pip install --no-warn-script-location -q -r requirements.txt
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
