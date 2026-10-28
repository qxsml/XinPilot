@echo off
setlocal
cd /d "%~dp0"

set "SMILES_PYTHONW=%LOCALAPPDATA%\miniforge3\envs\ai-agent\pythonw.exe"
if exist "%SMILES_PYTHONW%" (
    start "Aromatic SMILES Converter" "%SMILES_PYTHONW%" "%~dp0aromatic_smiles_converter.py"
    exit /b 0
)

set "SMILES_PYTHONW=%LOCALAPPDATA%\miniforge3\pythonw.exe"
if exist "%SMILES_PYTHONW%" (
    start "Aromatic SMILES Converter" "%SMILES_PYTHONW%" "%~dp0aromatic_smiles_converter.py"
    exit /b 0
)

where pythonw.exe >nul 2>nul
if not errorlevel 1 (
    start "Aromatic SMILES Converter" pythonw.exe "%~dp0aromatic_smiles_converter.py"
    exit /b 0
)

echo Python with RDKit was not found.
echo Run this tool from the XinPilot Python environment.
pause
exit /b 1
