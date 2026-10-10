@echo off
cd /d "%~dp0"
if exist "..\runtime\python.exe" (
  echo Dependencies are included in the installer. Use App updates for software changes.
  pause
  exit /b
)
py -m pip install -r requirements.txt
pause
