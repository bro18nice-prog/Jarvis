@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Ruleaza mai intai INSTALEAZA.bat.
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" app\panou.py
