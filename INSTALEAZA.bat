@echo off
setlocal
title Instalare Jarvis
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install.ps1"
set "result=%ERRORLEVEL%"
echo.
pause
exit /b %result%
