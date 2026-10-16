@echo off
cd /d "%~dp0"
if exist "..\runtime\python.exe" (
  "..\runtime\python.exe" -E -s launcher.py
) else (
  py launcher.py
)
pause
