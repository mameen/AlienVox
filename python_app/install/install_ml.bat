@echo off
setlocal enabledelayedexpansion

rem AlienVox ML add-on installer.
rem Install shared ML requirements and the MOSS runtime in the app's venv.

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "APP_DIR=%%~fI"
set "PYTHON_EXE="

rem Match run.py: prefer the app-local venv, then the shared repository venv.
if exist "%APP_DIR%\.venv\Scripts\python.exe" set "PYTHON_EXE=%APP_DIR%\.venv\Scripts\python.exe"
if not defined PYTHON_EXE if exist "%APP_DIR%\..\.venv\Scripts\python.exe" set "PYTHON_EXE=%APP_DIR%\..\.venv\Scripts\python.exe"
if not defined PYTHON_EXE set "PYTHON_EXE=python"

pushd "%APP_DIR%" || (echo Could not find application directory & exit /b 1)

echo.
echo   AlienVox - ML Voices Add-on
echo.

"%PYTHON_EXE%" -m pip install -r "%APP_DIR%\requirements.txt"
if errorlevel 1 goto INSTALL_FAILED

rem Misaki's Japanese Kokoro voices need the UniDic data files as well as the pip packages.
"%PYTHON_EXE%" -c "import pathlib,unidic,sys; sys.exit(0 if (pathlib.Path(unidic.DICDIR)/'mecabrc').is_file() else 1)"
if errorlevel 1 (
  "%PYTHON_EXE%" -m unidic download
  if errorlevel 1 goto INSTALL_FAILED
)

rem Keep upstream Torch/Transformers pins out of the shared environment.
"%PYTHON_EXE%" -m pip install --no-deps -r "%APP_DIR%\requirements-moss.txt"
if errorlevel 1 goto INSTALL_FAILED

"%PYTHON_EXE%" -m pip install --no-deps -r "%APP_DIR%\requirements-pockettts.txt"
if errorlevel 1 goto INSTALL_FAILED

echo.
echo ML requirements and the MOSS runtime are installed.
popd
exit /b 0

:INSTALL_FAILED
set "RC=%ERRORLEVEL%"
echo.
echo ML installation failed with exit code %RC%.
popd
exit /b %RC%
