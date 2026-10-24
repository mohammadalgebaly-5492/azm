@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
title AZM - Project Management Platform

where python >nul 2>nul
if errorlevel 1 (
  echo Python is not installed.
  echo Download it from https://www.python.org/downloads/ and tick "Add python.exe to PATH" during setup.
  pause
  exit /b 1
)

if exist ".git" (
  where git >nul 2>nul
  if not errorlevel 1 (
    echo Checking for updates...
    git pull --ff-only
  )
)

if not exist ".venv" (
  echo First run: preparing the environment...
  python -m venv .venv
)
call ".venv\Scripts\activate.bat"
pip install -q --disable-pip-version-check -r requirements.txt

set CC_COOKIE_SECURE=0
set CC_DATABASE=%~dp0data\azm.sqlite3

echo.
echo AZM is running at http://127.0.0.1:5000
echo Keep this window open while you use the platform. Close it to stop.
echo.
start "" /b cmd /c "timeout /t 3 >nul & start http://127.0.0.1:5000"
python -m flask --app wsgi run --port 5000
pause
