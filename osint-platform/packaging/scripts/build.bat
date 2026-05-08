@echo off
REM ============================================================================
REM OSINT Platform - Windows packaging build orchestrator
REM ----------------------------------------------------------------------------
REM Run from packaging\scripts\ on a Windows machine that has installed:
REM   - Python 3.11.x (in PATH as `python`)
REM   - Node.js 20 LTS (in PATH as `npm`)
REM   - 7-Zip (optional, for portable .7z output)
REM   - Inno Setup 6 (optional, only if you want the .exe installer)
REM
REM Required pre-staged inputs in packaging\vendor\:
REM   vendor\elasticsearch\        (extract elasticsearch-8.15.x-windows-x86_64.zip
REM                                 *with-JDK* variant; bin\, jdk\, lib\, etc.)
REM   vendor\snap_v1.tar.zst       (zstd-compressed ES filesystem snapshot)
REM
REM End state on success:
REM   packaging\dist\OSINT\OSINT.exe   (run this to launch the app)
REM ============================================================================

setlocal EnableExtensions EnableDelayedExpansion

set SCRIPT_DIR=%~dp0
set PKG_DIR=%SCRIPT_DIR%..
set REPO_DIR=%PKG_DIR%\..
set FRONTEND_DIR=%REPO_DIR%\frontend
set BACKEND_DIR=%REPO_DIR%\backend
set VENDOR_DIR=%PKG_DIR%\vendor
set DIST_DIR=%PKG_DIR%\dist\OSINT
set BUILDVENV=%PKG_DIR%\.buildvenv

pushd "%PKG_DIR%" || (echo Could not enter %PKG_DIR% & exit /b 1)

echo.
echo ============================================================
echo [0/7] Pre-flight checks
echo ============================================================

where python >nul 2>nul || (echo ERROR: python not found in PATH & exit /b 1)
where npm    >nul 2>nul || (echo ERROR: npm not found in PATH    & exit /b 1)

if not exist "%VENDOR_DIR%\elasticsearch\bin\elasticsearch.bat" (
    echo ERROR: Elasticsearch not staged.
    echo   Expected: %VENDOR_DIR%\elasticsearch\bin\elasticsearch.bat
    echo   Action:   download elasticsearch-8.15.x-windows-x86_64.zip
    echo             ^(the WITH-JDK variant^) and extract to vendor\elasticsearch
    exit /b 1
)
if not exist "%VENDOR_DIR%\elasticsearch\jdk\bin\java.exe" (
    echo ERROR: bundled JDK missing under vendor\elasticsearch\jdk\
    echo   You probably grabbed the -no-jdk variant. Use the WITH-JDK ZIP.
    exit /b 1
)
if not exist "%VENDOR_DIR%\snap_v1.tar.zst" (
    echo WARN: vendor\snap_v1.tar.zst not present.
    echo       App will install with empty index. To bundle data,
    echo       run scripts\make_snapshot.sh on the dev box first.
)

echo.
echo ============================================================
echo [1/7] Building Next.js static export
echo ============================================================

pushd "%FRONTEND_DIR%" || exit /b 1
if not exist node_modules (
    call npm ci || (popd & exit /b 1)
)
set NEXT_OUTPUT_EXPORT=1
set NEXT_PUBLIC_API_BASE=
call npm run build || (popd & exit /b 1)
if not exist out\index.html (
    echo ERROR: Next.js export did not produce out\index.html
    popd
    exit /b 1
)

REM Replace backend\app\static with the export. Backup once.
if exist "%BACKEND_DIR%\app\static" (
    if not exist "%BACKEND_DIR%\app\.static.backup" (
        echo Backing up original static -^> app\.static.backup
        xcopy /E /I /Y /Q "%BACKEND_DIR%\app\static" "%BACKEND_DIR%\app\.static.backup" >nul
    )
    rmdir /S /Q "%BACKEND_DIR%\app\static"
)
mkdir "%BACKEND_DIR%\app\static"
xcopy /E /I /Y /Q out "%BACKEND_DIR%\app\static" >nul
popd

echo.
echo ============================================================
echo [2/7] Build venv + dependencies
echo ============================================================

if not exist "%BUILDVENV%" (
    python -m venv "%BUILDVENV%" || exit /b 1
)
call "%BUILDVENV%\Scripts\activate.bat" || exit /b 1
python -m pip install --upgrade pip wheel setuptools || exit /b 1
python -m pip install -r "%BACKEND_DIR%\requirements.txt" || exit /b 1
python -m pip install pyinstaller==6.10.0 zstandard==0.22.0 || exit /b 1

echo.
echo ============================================================
echo [3/7] PyInstaller build (one-folder, windowed)
echo ============================================================

if exist build  rmdir /S /Q build
if exist dist   rmdir /S /Q dist

pyinstaller --noconfirm --clean osint.spec || exit /b 1

if not exist "%DIST_DIR%\OSINT.exe" (
    echo ERROR: PyInstaller did not produce dist\OSINT\OSINT.exe
    exit /b 1
)

echo.
echo ============================================================
echo [4/7] Stage Elasticsearch alongside the .exe
echo ============================================================

xcopy /E /I /Y /Q "%VENDOR_DIR%\elasticsearch" "%DIST_DIR%\elasticsearch" >nul || exit /b 1
copy /Y "%PKG_DIR%\es-config\elasticsearch.yml" "%DIST_DIR%\elasticsearch\config\elasticsearch.yml" >nul || exit /b 1
copy /Y "%PKG_DIR%\es-config\jvm.options"       "%DIST_DIR%\elasticsearch\config\jvm.options"       >nul || exit /b 1

REM Strip ES sample/docs/logs we never need at runtime.
if exist "%DIST_DIR%\elasticsearch\modules\x-pack-ml" rmdir /S /Q "%DIST_DIR%\elasticsearch\modules\x-pack-ml"
if exist "%DIST_DIR%\elasticsearch\modules\x-pack-watcher" rmdir /S /Q "%DIST_DIR%\elasticsearch\modules\x-pack-watcher"
if exist "%DIST_DIR%\elasticsearch\logs"  rmdir /S /Q "%DIST_DIR%\elasticsearch\logs"

echo.
echo ============================================================
echo [5/7] Stage snapshot archive
echo ============================================================

mkdir "%DIST_DIR%\es-snapshot" 2>nul
if exist "%VENDOR_DIR%\snap_v1.tar.zst" (
    copy /Y "%VENDOR_DIR%\snap_v1.tar.zst" "%DIST_DIR%\es-snapshot\snap_v1.tar.zst" >nul || exit /b 1
    for %%I in ("%DIST_DIR%\es-snapshot\snap_v1.tar.zst") do (
        echo   snapshot: %%~zI bytes
    )
) else (
    echo   no snapshot bundled (first launch will start with empty index)
)

echo.
echo ============================================================
echo [6/7] Stage license / placeholder portable flag
echo ============================================================

if exist "%PKG_DIR%\assets\osint.ico" copy /Y "%PKG_DIR%\assets\osint.ico" "%DIST_DIR%\OSINT.ico" >nul

REM Drop a "portable.flag" template the user can rename to enable portable mode.
echo Rename this file to "portable.flag" to keep userdata next to OSINT.exe instead of in %%LOCALAPPDATA%%\OSINT > "%DIST_DIR%\portable.flag.template"

echo.
echo ============================================================
echo [7/7] Optional installer / portable archive
echo ============================================================

where iscc >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo Building Inno Setup installer...
    iscc /Qp "%PKG_DIR%\installer\osint.iss" || echo WARN: Inno Setup compile failed
) else (
    echo Inno Setup ^(iscc^) not on PATH - skipping installer build.
)

where 7z >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo Building portable 7z archive...
    if exist "%PKG_DIR%\dist\OSINT-Portable.7z" del "%PKG_DIR%\dist\OSINT-Portable.7z"
    7z a -mx=9 -ms=on "%PKG_DIR%\dist\OSINT-Portable.7z" "%DIST_DIR%\*" >nul || echo WARN: 7z pack failed
) else (
    echo 7z not on PATH - skipping portable archive.
)

echo.
echo ============================================================
echo BUILD OK
echo   Launch:    "%DIST_DIR%\OSINT.exe"
echo   Installer: %PKG_DIR%\installer\Output\*-Setup-*.exe
echo   Portable:  %PKG_DIR%\dist\OSINT-Portable.7z
echo ============================================================

popd
endlocal
