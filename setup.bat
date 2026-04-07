@echo off
setlocal

set PYTHON_VERSION=3.12.8
set PYTHON_DIR=python
set PYTHON=%PYTHON_DIR%\python.exe

if exist %PYTHON% (
    echo Python already set up.
    goto install_deps
)

echo Downloading embeddable Python %PYTHON_VERSION%...
curl -L -o python.zip https://www.python.org/ftp/python/%PYTHON_VERSION%/python-%PYTHON_VERSION%-embed-amd64.zip
mkdir %PYTHON_DIR%
tar -xf python.zip -C %PYTHON_DIR%
del python.zip

:: Enable pip in embeddable Python (uncomment "import site" in ._pth file)
for %%f in (%PYTHON_DIR%\python*._pth) do (
    powershell -Command "(Get-Content '%%f') -replace '#import site','import site' | Set-Content '%%f'"
)

:: Install pip
curl -L -o %PYTHON_DIR%\get-pip.py https://bootstrap.pypa.io/get-pip.py
%PYTHON% %PYTHON_DIR%\get-pip.py --no-warn-script-location
del %PYTHON_DIR%\get-pip.py

:install_deps
echo Installing dependencies...
%PYTHON% -m pip install --no-warn-script-location -r requirements.txt

echo.
echo Setup complete. Run start.bat to launch.
