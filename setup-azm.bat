@echo off
chcp 65001 >nul
title AZM - Setup
set "APPDIR=%USERPROFILE%\azm-app"
set "OLD=%~dp0"

where git >nul 2>nul
if errorlevel 1 (
  echo Git is not installed.
  echo Install it from https://git-scm.com/download/win with the default options, then run this file again.
  pause
  exit /b 1
)

if exist "%APPDIR%\.git" (
  echo AZM is already installed in %APPDIR%
  goto shortcut
)

echo Downloading AZM from GitHub...
echo If a GitHub sign-in window appears, sign in and approve.
git clone https://github.com/mohammadalgebaly-5492/azm.git "%APPDIR%"
if errorlevel 1 (
  echo Download failed. Make sure you signed in to GitHub, then run this file again.
  pause
  exit /b 1
)

if exist "%OLD%data\azm.sqlite3" (
  mkdir "%APPDIR%\data" 2>nul
  copy /y "%OLD%data\*" "%APPDIR%\data\" >nul
  echo Your existing data was copied to the new installation.
)

:shortcut
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\AZM.lnk');$s.TargetPath='%APPDIR%\start-windows.bat';$s.WorkingDirectory='%APPDIR%';$s.Save()"
echo A shortcut named AZM was added to your desktop. Use it from now on.
echo.
cd /d "%APPDIR%"
call start-windows.bat
