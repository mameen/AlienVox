@echo off
setlocal enabledelayedexpansion

rem AlienVox ML add-on launcher.
rem Installs the large ML dependency layer on top of an existing base install.

set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%" || (echo Could not find install directory & exit /b 1)

echo.
echo   AlienVox - ML Voices Add-on
echo.

python "%SCRIPT_DIR%build_install.py" ml
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%
