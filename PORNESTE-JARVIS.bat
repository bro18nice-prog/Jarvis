@echo off
setlocal
title JARVIS
cd /d "%~dp0"
set "HF_HOME=%~dp0models\hf"
set "TEMP=%~dp0tools\tmp"
set "TMP=%~dp0tools\tmp"
set "PYTHONIOENCODING=utf-8"
if not exist "tools\tmp" mkdir "tools\tmp"
if not exist ".venv\Scripts\python.exe" (
  echo Ruleaza mai intai INSTALEAZA.bat.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" app\jarvis.py
