@echo off
cd /d "%~dp0"
if exist "..\runtime\pythonw.exe" (
  start "" "..\runtime\pythonw.exe" -E -s launcher.py
  exit /b
)
py launcher.py
if errorlevel 1 pause
