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
  pause
  exit /b 1
)
set "SCN=tarawa"
if not "%~1"=="" set "SCN=%~1"
echo WW2 surface sim - headless mode  scenario=%SCN%
"%PY%" main.py --headless --scenario "%SCN%" --ticks 80 --report
pause
