@echo off
setlocal
cd /d "%~dp0"
call scripts\select_python.bat
"%XINPILOT_PYTHON%" -B scripts\build_renderer.py
set "BUILD_RESULT=%ERRORLEVEL%"
if not "%BUILD_RESULT%"=="0" pause
exit /b %BUILD_RESULT%
