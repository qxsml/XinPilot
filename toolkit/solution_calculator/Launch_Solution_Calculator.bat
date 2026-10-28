@echo off
setlocal
cd /d "%~dp0"

set "SOLUTION_PYTHONW=%LOCALAPPDATA%\miniforge3\envs\ai-agent\pythonw.exe"
if exist "%SOLUTION_PYTHONW%" (
    start "Solution & Stock Calculator" "%SOLUTION_PYTHONW%" "%~dp0solution_calculator.py" %*
    exit /b 0
)

set "SOLUTION_PYTHONW=%LOCALAPPDATA%\miniforge3\pythonw.exe"
if exist "%SOLUTION_PYTHONW%" (
    start "Solution & Stock Calculator" "%SOLUTION_PYTHONW%" "%~dp0solution_calculator.py" %*
    exit /b 0
)

where pythonw.exe >nul 2>nul
if not errorlevel 1 (
    start "Solution & Stock Calculator" pythonw.exe "%~dp0solution_calculator.py" %*
    exit /b 0
)

echo Python was not found.
echo Run this tool from the XinPilot Python environment.
pause
exit /b 1
