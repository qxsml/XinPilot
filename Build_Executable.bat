@echo off
setlocal
cd /d "%~dp0"
call scripts\select_python.bat
if not exist artifacts mkdir artifacts
"%XINPILOT_PYTHON%" -m PyInstaller --noconfirm --distpath release --workpath artifacts/build-typescript packaging/TypeScript.spec
if errorlevel 1 pause
