@echo off
setlocal enabledelayedexpansion

rem Builds the AlienVox portable zip: a onedir PyInstaller freeze, no
rem installer, no registry entries -- extract the zip anywhere and run
rem AlienVox.exe. Base tier only (SAPI5, no ML) -- see
rem install\windows\alienvox.spec for why.
rem
rem Everything transient (build venv, PyInstaller work/dist, the final
rem zip) lives under install\.venv-base-build\ -- one folder already
rem covered by .gitignore's ".venv-base-build/" rule, so nothing here
rem needs its own separate ignore rule.
rem
rem Run from anywhere; paths below are relative to this script.

rem SCRIPT_DIR = ...\python_app\install\windows\portable\ -- three levels
rem below python_app, hence \..\..\.. below.
set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%..\..\.." || (echo Could not find python_app directory & exit /b 1)
set "APP_DIR=%CD%"
set "BUILD_ROOT=%APP_DIR%\install\.venv-base-build"
set "BUILD_VENV=%BUILD_ROOT%"
set "OUT_DIR=%BUILD_ROOT%\build\portable"

echo.
echo   AlienVox - Build Portable (base tier, SAPI5 only)
echo.

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

echo Zipping portable package...
set "ZIP_PATH=%OUT_DIR%\AlienVox-portable-win64.zip"
if exist "%ZIP_PATH%" del "%ZIP_PATH%"
rem PyInstaller/antivirus can briefly hold a handle on freshly-written
rem files right after the build finishes -- retry a few times rather
rem than failing on a transient lock.
set "ZIP_TRIES=0"
:zip_retry
powershell -NoProfile -NonInteractive -Command "Compress-Archive -Path '%OUT_DIR%\dist\AlienVox\*' -DestinationPath '%ZIP_PATH%' -Force" >nul 2>nul
if exist "%ZIP_PATH%" goto zip_done
set /a ZIP_TRIES+=1
if %ZIP_TRIES% GEQ 5 (echo ERROR: zip step failed after 5 attempts. & popd & exit /b 1)
timeout /t 2 /nobreak >nul
goto zip_retry
:zip_done

echo.
echo   Done: install\.venv-base-build\build\portable\AlienVox-portable-win64.zip
echo   Extract anywhere and run AlienVox.exe -- no installer, no registry entries.
echo   ML voices are not included in this build -- see install\windows\README.md.
echo.
popd
