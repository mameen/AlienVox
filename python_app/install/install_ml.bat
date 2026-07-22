@echo off
setlocal enabledelayedexpansion

rem AlienVox ML add-on installer - adds torch/transformers/TTS engine
rem packages on top of an existing base install (install.bat).
rem This is a large download (multi-GB of wheels); model *weights* are
rem separate and download later, per model, from inside the app.
rem
rem Installs from the root requirements.txt (same file setup.py uses) -
rem NOT a separate install/requirements-ml.txt, which used to duplicate
rem it and had already started drifting out of sync. requirements-base.txt
rem stays separate on purpose: the Windows packaged-build scripts
rem (install/windows/) require a venv that genuinely doesn't have ML
rem packages installed, so it can't be folded the same way.

set "SCRIPT_DIR=%~dp0"
set "APP_DIR=%SCRIPT_DIR%.."
pushd "%APP_DIR%" || (echo Could not find python_app directory & exit /b 1)

echo.
echo   AlienVox - ML Voices Add-on
echo   (torch, transformers, TTS engine packages - large download)
echo.

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: No .venv found. Run install\install.bat first.
    popd
    exit /b 1
)

echo Installing ML dependencies - this can take a while and download several GB...
".venv\Scripts\python.exe" -m pip install -r "requirements.txt"
if errorlevel 1 (
    echo ERROR: pip install failed - see output above.
    popd
    exit /b 1
)

echo.
echo   Done. ML voice packages are installed.
echo   Model weights still download on demand - pick a model in the app
echo   (Settings tab for a stack, "Install Model") or run:
echo.
echo       python run.py download
echo.
echo   AlienVox is a product of AlienTech.Software - https://alientech.software/
echo.
popd
