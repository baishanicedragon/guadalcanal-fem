@echo off
chcp 65001 >nul 2>nul
cd /d "%~dp0"
set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY (
  if exist "C:\Users\cookie\.workbuddy\binaries\python\versions\3.13.12\python.exe" (
    set "PY=C:\Users\cookie\.workbuddy\binaries\python\versions\3.13.12\python.exe"
  )
)
if not defined PY (
  echo [ERR] python interpreter not found.
  echo        Install Python 3, or keep WorkBuddy managed python path.
  pause
  exit /b 1
)
set "SCN=guadao"
if not "%~1"=="" set "SCN=%~1"
echo WW2 surface sim - CLI mode  scenario=%SCN%
"%PY%" main.py --cli --scenario "%SCN%"
pause
