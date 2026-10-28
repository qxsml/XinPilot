@echo off
rem Called from a root launcher after changing to the project directory.
rem Explicit environment override wins; local settings are private to this machine.
if not defined XINPILOT_PYTHON if defined RXNPILOT_PYTHON set "XINPILOT_PYTHON=%RXNPILOT_PYTHON%"
if not defined XINPILOT_PYTHON if defined SYNTRACK_PYTHON set "XINPILOT_PYTHON=%SYNTRACK_PYTHON%"
if not defined XINPILOT_PYTHON if exist "xinpilot.local.bat" call "xinpilot.local.bat"
if not defined XINPILOT_PYTHON if exist ".venv\Scripts\python.exe" set "XINPILOT_PYTHON=%CD%\.venv\Scripts\python.exe"
if not defined XINPILOT_PYTHON set "XINPILOT_PYTHON=python"
exit /b 0
