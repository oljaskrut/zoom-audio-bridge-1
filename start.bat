@echo off
setlocal
title Zoom Audio Bridge

set PYTHON=python\tools\python.exe

if not exist %PYTHON% (
    echo [ERROR] Python not found.
    echo         Run setup.bat first.
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
%PYTHON% app.py
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Application exited with an error.
)

echo.
pause
