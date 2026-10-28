@echo off
setlocal
cd /d "%~dp0"
echo This installs Python packages from the internet into this folder's .venv.
if exist ".venv\Scripts\python.exe" goto install
py -3.12 -m venv .venv
if errorlevel 1 goto failed
:install
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo Setup complete. Launch with Launch_XinPilot.bat.
echo A private xinpilot.local.bat or XINPILOT_PYTHON override takes priority if configured.
pause
exit /b 0
:failed
echo Setup failed. See docs\setup.md. Python 3.12 with Tk and WebView2 are required.
pause
exit /b 1
