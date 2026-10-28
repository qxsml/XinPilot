@echo off
setlocal
cd /d "%~dp0"
call scripts\select_python.bat
"%XINPILOT_PYTHON%" -B integrated_full_software.py
if errorlevel 1 pause
