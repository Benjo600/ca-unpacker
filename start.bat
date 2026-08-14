@echo off
setlocal
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
set "LOG=%~dp0start-log.txt"

echo %date% %time% launch >> "%LOG%"

if not exist "%PY%" (
  echo First-time setup. This can take a minute...
  where python >nul 2>nul
  if errorlevel 1 (
    echo Python was not found. Install Python 3 from python.org and tick "Add python.exe to PATH".
    pause
    exit /b 1
  )
  python -m venv .venv
  if errorlevel 1 (
    echo Could not create a virtual environment.
    pause
    exit /b 1
  )
  "%PY%" -m pip install --upgrade pip
  "%PY%" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Could not install the app libraries. See start-log.txt
    pause
    exit /b 1
  )
)

echo Opening CA Unpacker...
"%PY%" -m apps.desktop
if errorlevel 1 (
  echo The app closed with an error. See start-log.txt
  "%PY%" -m apps.desktop >> "%LOG%" 2>&1
  type "%LOG%"
  pause
)
