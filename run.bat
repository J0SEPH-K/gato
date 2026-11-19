@echo off
rem Starts GATO as administrator (input + capture need it). Game must already be running.
cd /d "%~dp0"
net session >nul 2>&1
if %errorlevel% neq 0 (
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" run_gato.py
) else (
  start "" pythonw.exe run_gato.py
)
