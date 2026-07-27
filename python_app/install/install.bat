@echo off
setlocal enabledelayedexpansion

rem AlienVox install launcher.
rem Base install = app shell + built-in voices.
rem Advanced install = base install + ML dependencies + bundled preview assets.

set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%" || (echo Could not find install directory & exit /b 1)

echo.
echo   AlienVox - Install
echo.
echo   [B]asic   = app shell + Windows voices
echo   [A]dvanced = base install + ML dependencies + preview assets
echo.

choice /c BA /n /m "Choose install mode: [B]asic or [A]dvanced? "
if errorlevel 2 goto ADVANCED_INSTALL
if errorlevel 1 goto BASIC_INSTALL

:BASIC_INSTALL
python "%SCRIPT_DIR%build_install.py" basic
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%

:ADVANCED_INSTALL
python "%SCRIPT_DIR%build_install.py" advanced
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%
