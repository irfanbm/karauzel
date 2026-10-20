@echo off
setlocal
title Karauzel
cd /d "%~dp0"

set "PORT=4173"
if not "%~1"=="" set "PORT=%~1"

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo Python 3 was not found.
    echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
    pause
    exit /b 1
)

rem Stop an older Carouso still holding the port, so the browser never talks to stale code.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$c = Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1;" ^
  "if ($c) { $p = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $c.OwningProcess);" ^
  "  if ($p.CommandLine -match 'carouso') { Stop-Process -Id $c.OwningProcess -Force; Start-Sleep -Milliseconds 500; Write-Host 'Stopped an older Carouso server.' } }"

echo Starting Karauzel on http://127.0.0.1:%PORT%
%PY% -m carouso serve --port %PORT% --open
if errorlevel 1 (
    echo.
    echo Carouso stopped with an error.
    pause
)
endlocal
