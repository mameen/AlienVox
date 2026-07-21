@echo off
setlocal enabledelayedexpansion

rem AlienVox base installer - Windows, SAPI5 only, no ML/torch.
rem Run from anywhere: this script locates the repo root relative to itself.

set "SCRIPT_DIR=%~dp0"
set "APP_DIR=%SCRIPT_DIR%.."
pushd "%APP_DIR%" || (echo Could not find python_app directory & exit /b 1)

echo.
echo   AlienVox - Base Install
echo   (SAPI5 speech only - no ML voices, no torch, no large downloads)
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python not found on PATH. Install Python 3.11+ from python.org first.
    popd
    exit /b 1
)

if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: venv creation failed.
        popd
        exit /b 1
    )
) else (
    echo Virtual environment already exists - reusing .venv
)

echo Installing base dependencies (PySide6, pynput, pywin32, ...)...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r "install\requirements-base.txt"
if errorlevel 1 (
    echo ERROR: pip install failed - see output above.
    popd
    exit /b 1
)

echo.
echo   Done. AlienVox is ready to run with Windows SAPI5 voices.
echo.
echo   Start it:      python run.py app
echo   Add ML voices: install\install_ml.bat   (optional, large download)
echo.
echo   AlienVox is a product of AlienTech.Software - https://alientech.software/
echo.
popd
