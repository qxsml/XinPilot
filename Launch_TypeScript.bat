@echo off
setlocal
cd /d "%~dp0"
call scripts\select_python.bat
"%XINPILOT_PYTHON%" -B -m desktop.live_app
if errorlevel 1 pause
