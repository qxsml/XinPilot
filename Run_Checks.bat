@echo off
setlocal
cd /d "%~dp0"
call scripts\select_python.bat
"%XINPILOT_PYTHON%" -B scripts\run_checks.py %*
if errorlevel 1 pause
