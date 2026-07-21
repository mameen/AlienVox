@echo off
setlocal enabledelayedexpansion

rem Builds the AlienVox Windows installer: PyInstaller freeze (own copy,
rem separate from the portable build's) + Inno Setup compile into a
rem single AlienVoxSetup-<version>.exe with Start Menu shortcuts and an
rem uninstaller.
rem
rem Everything transient (build venv, PyInstaller work/dist, the
rem compiled installer) lives under install\.venv-base-build\ -- one
rem folder already covered by .gitignore's ".venv-base-build/" rule.
rem The build venv itself is shared with the portable build (same
rem install\.venv-base-build\Scripts\python.exe); only the frozen
rem dist/work output is kept separate (build\exe\ vs build\portable\),
rem so building one doesn't clobber the other's output.
rem
rem Requires the Inno Setup Compiler (ISCC.exe) on PATH or in one of the
rem usual install locations -- get it free from
rem https://jrsoftware.org/isinfo.php. Not bundled with this repo.

rem SCRIPT_DIR = ...\python_app\install\windows\exe\ -- three levels
rem below python_app.
set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%..\..\.." || (echo Could not find python_app directory & exit /b 1)
set "APP_DIR=%CD%"
set "BUILD_ROOT=%APP_DIR%\install\.venv-base-build"
set "BUILD_VENV=%BUILD_ROOT%"
set "OUT_DIR=%BUILD_ROOT%\build\exe"

echo.
echo   AlienVox - Build Installer (base tier, SAPI5 only)
echo.

if not exist "%BUILD_VENV%\Scripts\python.exe" (
    echo Creating a clean base-only build venv...
    echo kept separate from the dev .venv so torch/ML packages can never leak in
    python -m venv "%BUILD_VENV%"
    if errorlevel 1 (echo ERROR: venv creation failed. & popd & exit /b 1)
    "%BUILD_VENV%\Scripts\python.exe" -m pip install --upgrade pip -q
    "%BUILD_VENV%\Scripts\python.exe" -m pip install -r "install\requirements-base.txt" -q
    if errorlevel 1 (echo ERROR: base dependency install failed. & popd & exit /b 1)
    "%BUILD_VENV%\Scripts\python.exe" -m pip install pyinstaller -q
    if errorlevel 1 (echo ERROR: pyinstaller install failed. & popd & exit /b 1)
) else (
    echo Reusing existing build venv: %BUILD_VENV%
)

if not exist "%OUT_DIR%" mkdir "%OUT_DIR%"

echo Freezing with PyInstaller...
"%BUILD_VENV%\Scripts\pyinstaller.exe" "install\windows\alienvox.spec" ^
    --distpath "%OUT_DIR%\dist" ^
    --workpath "%OUT_DIR%\work" ^
    --noconfirm
if errorlevel 1 (echo ERROR: PyInstaller build failed. & popd & exit /b 1)

echo Copying version.yaml alongside the frozen app...
copy /Y "version.yaml" "%OUT_DIR%\dist\AlienVox\version.yaml" >nul

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
echo   Done: install\.venv-base-build\build\exe\AlienVoxSetup-%APP_VERSION%.exe
echo.
popd
