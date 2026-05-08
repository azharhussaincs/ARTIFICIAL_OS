@echo off
REM Windows variant of make_snapshot.sh — for the case where the dev ES
REM is also running on the Windows build machine.
REM Output: packaging\vendor\snap_v1.tar.zst

setlocal EnableExtensions EnableDelayedExpansion

if "%ES_URL%"==""    set ES_URL=http://localhost:9200
if "%ES_INDEX%"==""  set ES_INDEX=tc_index
if "%SNAPSHOT_REPO_DIR%"=="" set SNAPSHOT_REPO_DIR=%TEMP%\osint_es_snapshot

set HERE=%~dp0
set PKG_DIR=%HERE%..
set VENDOR_DIR=%PKG_DIR%\vendor

where curl >nul 2>nul || (echo ERROR: curl not on PATH & exit /b 1)
where tar  >nul 2>nul || (echo ERROR: tar not on PATH ^(install Git-for-Windows or Win10 1803+^) & exit /b 1)

if not exist "%SNAPSHOT_REPO_DIR%" mkdir "%SNAPSHOT_REPO_DIR%"
if not exist "%VENDOR_DIR%"        mkdir "%VENDOR_DIR%"

echo [1/4] Verifying ES at %ES_URL% ...
curl -fsS "%ES_URL%/_cluster/health?pretty" >nul || exit /b 1

echo [2/4] Registering snapshot repo ...
curl -fsS -X PUT "%ES_URL%/_snapshot/local_repo" -H "Content-Type: application/json" ^
  -d "{\"type\":\"fs\",\"settings\":{\"location\":\"%SNAPSHOT_REPO_DIR:\=/%\",\"compress\":true}}" >nul || exit /b 1

echo [3/4] Taking snapshot snap_v1 ...
curl -fsS -X PUT "%ES_URL%/_snapshot/local_repo/snap_v1?wait_for_completion=true" ^
  -H "Content-Type: application/json" ^
  -d "{\"indices\":\"%ES_INDEX%\",\"include_global_state\":false,\"ignore_unavailable\":true}" || exit /b 1

echo.
echo [4/4] Compressing -^> %VENDOR_DIR%\snap_v1.tar.zst ...
REM tar on Win10+ supports zstd via --zstd if libarchive build supports it;
REM if not, fall back to plain tar + 7z.
tar --zstd -cf "%VENDOR_DIR%\snap_v1.tar.zst" -C "%SNAPSHOT_REPO_DIR%" .
if errorlevel 1 (
    echo tar --zstd failed; falling back to tar + 7z ...
    where 7z >nul 2>nul || (echo ERROR: 7z not on PATH for fallback & exit /b 1)
    tar -cf "%TEMP%\snap_v1.tar" -C "%SNAPSHOT_REPO_DIR%" . || exit /b 1
    7z a -t7z -m0=zstd -mx=19 "%VENDOR_DIR%\snap_v1.tar.zst" "%TEMP%\snap_v1.tar" || exit /b 1
    del "%TEMP%\snap_v1.tar"
)

echo OK: %VENDOR_DIR%\snap_v1.tar.zst
endlocal
