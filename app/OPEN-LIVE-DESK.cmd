@echo off
cd /d "%~dp0"
if exist "..\runtime\pythonw.exe" (
  start "" "..\runtime\pythonw.exe" -E -s desktop_start.py
  exit /b
)
where pyw >nul 2>nul
if not errorlevel 1 (
  start "" pyw desktop_start.py
  exit /b
)
where pythonw >nul 2>nul
if not errorlevel 1 (
  start "" pythonw desktop_start.py
  exit /b
)
echo Python windowless launcher is missing. Run INSTALL-REQUIREMENTS.cmd first.
pause
