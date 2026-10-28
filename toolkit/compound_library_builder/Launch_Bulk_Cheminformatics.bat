@echo off
setlocal
cd /d "%~dp0"

set "BULK_PYTHONW=%LOCALAPPDATA%\miniforge3\envs\ai-agent\pythonw.exe"
if exist "%BULK_PYTHONW%" (
    start "Bulk Cheminformatics" "%BULK_PYTHONW%" "%~dp0bulk_gui.py"
    exit /b 0
)

set "BULK_PYTHONW=%LOCALAPPDATA%\miniforge3\pythonw.exe"
if exist "%BULK_PYTHONW%" (
    start "Bulk Cheminformatics" "%BULK_PYTHONW%" "%~dp0bulk_gui.py"
    exit /b 0
)

where pythonw.exe >nul 2>nul
if not errorlevel 1 (
    start "Bulk Cheminformatics" pythonw.exe "%~dp0bulk_gui.py"
    exit /b 0
)

echo Python with RDKit and openpyxl was not found.
echo Run this from the ai-agent environment: python bulk_gui.py
pause
exit /b 1
