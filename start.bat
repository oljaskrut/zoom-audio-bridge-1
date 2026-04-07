@echo off
setlocal
title Zoom Audio Bridge

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python not found.
    echo         Install Python 3.11+ from https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

if not exist .env (
    echo [ERROR] .env file not found.
    echo         Copy .env.example to .env and set your server URL.
    echo.
    pause
    exit /b 1
)

echo Starting Zoom Audio Bridge...
echo.
python app.py
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Application exited with an error.
)

echo.
pause
