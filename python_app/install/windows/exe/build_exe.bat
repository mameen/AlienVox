@echo off
setlocal enabledelayedexpansion

rem Builds the AlienVox Windows installer: PyInstaller freeze (same base
rem tier as the portable build) + Inno Setup compile into a single
rem AlienVoxSetup-<version>.exe with Start Menu shortcuts and an
rem uninstaller.
rem
rem Requires the Inno Setup Compiler (ISCC.exe) on PATH or in one of the
rem usual install locations -- get it free from
rem https://jrsoftware.org/isinfo.php. Not bundled with this repo.

rem SCRIPT_DIR = ...\python_app\install\windows\exe\ -- three levels
rem below python_app.
set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%..\..\.." || (echo Could not find python_app directory & exit /b 1)
set "APP_DIR=%CD%"

echo.
echo   AlienVox - Build Installer (base tier, SAPI5 only)
echo.

rem Step 1: reuse the portable build script to produce
rem install\windows\dist\AlienVox\ -- same PyInstaller freeze, this
rem script just adds the Inno Setup wrapper around it.
call "install\windows\portable\build_portable.bat"
if errorlevel 1 (echo ERROR: portable build step failed. & popd & exit /b 1)

echo Locating Inno Setup Compiler...
set "ISCC="
where iscc >nul 2>nul
if not errorlevel 1 (
    for /f "delims=" %%I in ('where iscc') do set "ISCC=%%I"
) else (
    if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
    if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
)
if "%ISCC%"=="" (
    echo ERROR: Inno Setup Compiler not found.
    echo Install it free from https://jrsoftware.org/isinfo.php then re-run this script.
    popd
    exit /b 1
)
echo Found: %ISCC%

echo Reading version from version.yaml...
set "APP_VERSION=0.0.0"
for /f "tokens=2 delims=: " %%V in ('findstr /b "version:" version.yaml') do set "APP_VERSION=%%~V"
set "APP_VERSION=%APP_VERSION:"=%"

echo Compiling installer (version %APP_VERSION%)...
"%ISCC%" /DMyAppVersion=%APP_VERSION% "install\windows\exe\alienvox_setup.iss"
if errorlevel 1 (echo ERROR: Inno Setup compile failed. & popd & exit /b 1)

echo.
echo   Done: install\windows\exe\AlienVoxSetup-%APP_VERSION%.exe
echo.
popd
