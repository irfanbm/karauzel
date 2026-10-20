@echo off
setlocal
title Karauzel Admin
cd /d "%~dp0"
set "PORT=4173"
if not "%~1"=="" set "PORT=%~1"
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY ( echo Python 3 was not found. & pause & exit /b 1 )
start "Karauzel admin browser" http://127.0.0.1:%PORT%/admin-dashboard
%PY% -m carouso serve --port %PORT% --open --open-path /admin-dashboard
endlocal
