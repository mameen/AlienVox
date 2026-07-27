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

echo Ensuring required installer assets are present...
python "install\build_install.py"
if errorlevel 1 (echo ERROR: installer asset preparation failed. & popd & exit /b 1)

if not exist "%BUILD_VENV%\Scripts\python.exe" (
    echo Creating a clean base-only build venv...
    echo kept separate from the dev .venv so torch/ML packages can never leak in
    python -m venv "%BUILD_VENV%"
    if errorlevel 1 (echo ERROR: venv creation failed. & popd & exit /b 1)
    "%BUILD_VENV%\Scripts\python.exe" -m pip install --upgrade pip -q
) else (
    echo Reusing existing build venv: %BUILD_VENV%
)

echo Syncing base build dependencies...
"%BUILD_VENV%\Scripts\python.exe" -m pip install -r "install\requirements-base.txt" -q
if errorlevel 1 (echo ERROR: base dependency install failed. & popd & exit /b 1)
"%BUILD_VENV%\Scripts\python.exe" -m pip install pyinstaller -q
if errorlevel 1 (echo ERROR: pyinstaller install failed. & popd & exit /b 1)

if not exist "%OUT_DIR%" mkdir "%OUT_DIR%"

echo Generating installer catalog from bundled source data...
"%BUILD_VENV%\Scripts\python.exe" "install\windows\exe\generate_installer_catalog.py"
if errorlevel 1 (echo ERROR: installer catalog generation failed. & popd & exit /b 1)

echo Freezing with PyInstaller...
"%BUILD_VENV%\Scripts\pyinstaller.exe" "install\windows\alienvox.spec" ^
    --distpath "%OUT_DIR%\dist" ^
    --workpath "%OUT_DIR%\work" ^
    --noconfirm
if errorlevel 1 (echo ERROR: PyInstaller build failed. & popd & exit /b 1)

echo Staging Qt ICU runtime dependencies...
set "ICU_SOURCE_DIR="
if exist "%CONDA_PREFIX%\Library\bin\icuuc73.dll" set "ICU_SOURCE_DIR=%CONDA_PREFIX%\Library\bin"
if exist "C:\devtools\anaconda3\Library\bin\icuuc73.dll" set "ICU_SOURCE_DIR=C:\devtools\anaconda3\Library\bin"
if "%ICU_SOURCE_DIR%"=="" (
    echo WARNING: Qt ICU DLLs were not found on this machine.
    echo WARNING: frozen Qt may still fail to load on a VM without them.
) else (
    echo Using ICU source directory: %ICU_SOURCE_DIR%
    for %%F in ("%ICU_SOURCE_DIR%\icu*.dll") do (
        copy /Y "%%~fF" "%OUT_DIR%\dist\AlienVox\_internal\PySide6\%%~nxF" >nul
    )
    if exist "%ICU_SOURCE_DIR%\icu.dll" (
        copy /Y "%ICU_SOURCE_DIR%\icu.dll" "%OUT_DIR%\dist\AlienVox\_internal\PySide6\icu.dll" >nul
    )
)

echo Overlaying the full PySide6 runtime payload from the build venv...
set "PYSIDE6_SOURCE=%BUILD_VENV%\Lib\site-packages\PySide6"
if not exist "%PYSIDE6_SOURCE%" (
    echo WARNING: %PYSIDE6_SOURCE% not found; frozen Qt may still be incomplete.
) else (
    if not exist "%OUT_DIR%\dist\AlienVox\_internal\PySide6" mkdir "%OUT_DIR%\dist\AlienVox\_internal\PySide6"
    robocopy "%PYSIDE6_SOURCE%" "%OUT_DIR%\dist\AlienVox\_internal\PySide6" /E /COPY:DAT /DCOPY:DAT /R:1 /W:1 /NFL /NDL /NJH /NJS >nul
    set "ROBO_STATUS=!errorlevel!"
    if !ROBO_STATUS! GEQ 8 (
        echo ERROR: copying the PySide6 payload failed with robocopy exit code !ROBO_STATUS!.
        popd
        exit /b 1
    )
)

echo Mirroring shiboken6 into the layout PySide6 expects...
set "SHIBOKEN_SOURCE=%BUILD_VENV%\Lib\site-packages\shiboken6"
if not exist "%SHIBOKEN_SOURCE%" (
    echo WARNING: %SHIBOKEN_SOURCE% not found; PySide6 may still fail to import.
) else (
    if not exist "%OUT_DIR%\dist\AlienVox\shiboken6\libshiboken" mkdir "%OUT_DIR%\dist\AlienVox\shiboken6\libshiboken"
    robocopy "%SHIBOKEN_SOURCE%" "%OUT_DIR%\dist\AlienVox\shiboken6\libshiboken" /E /COPY:DAT /DCOPY:DAT /R:1 /W:1 /NFL /NDL /NJH /NJS >nul
    set "ROBO_STATUS=!errorlevel!"
    if !ROBO_STATUS! GEQ 8 (
        echo ERROR: copying the shiboken6 payload failed with robocopy exit code !ROBO_STATUS!.
        popd
        exit /b 1
    )
)

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
