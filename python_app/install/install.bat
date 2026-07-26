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

choice /c BA /n /m "Choose install mode: [B]asic or [A]dvanced? "
if errorlevel 2 goto ADVANCED_INSTALL
if errorlevel 1 goto BASIC_INSTALL

:BASIC_INSTALL

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
echo   Preview samples are installed as assets so offline samples can play.
echo.
echo   Start it:      python run.py app
echo   Add ML voices: install\install_ml.bat   (optional, large download)
echo.
echo   AlienVox is a product of AlienTech.Software - https://alientech.software/
echo.
popd
exit /b 0

:ADVANCED_INSTALL
echo.
echo   Advanced install selected.
echo   This may take a while and can fail if downloads or model installs do.
echo   You can always install ML voices later from inside the app.
echo.

call "%~dp0install_ml.bat"
if errorlevel 1 (
    popd
    exit /b 1
)

echo.
echo Generating bundled preview samples...
"%APP_DIR%\.venv\Scripts\python.exe" setup.py --generate-audio --sample-format mp3
if errorlevel 1 (
    echo WARNING: preview audio generation failed.
)

echo.
echo   Advanced install complete.
echo   Base app, ML voices, and preview assets are ready.
echo.
popd
