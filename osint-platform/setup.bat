@echo off
REM ============================================================
REM OSINT Platform - local setup (Windows / cmd.exe)
REM ------------------------------------------------------------
REM Idempotent: safe to re-run. Never overwrites existing .env
REM or venv. Never starts/stops system services.
REM ============================================================
setlocal enabledelayedexpansion

set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%frontend"
set "VENV=%BACKEND%\.venv"

echo OSINT Platform - setup script
echo ------------------------------------------------------------

REM ---------- 1. system dependencies ----------
echo [1/6] Checking system dependencies...
where python >nul 2>nul || (echo Missing: python ^(>=3.10^) - install from https://www.python.org/downloads/  & exit /b 1)
where node   >nul 2>nul || (echo Missing: node ^(>=18^) - install from https://nodejs.org/                    & exit /b 1)
where npm    >nul 2>nul || (echo Missing: npm                                                                  & exit /b 1)
where curl   >nul 2>nul || (echo Missing: curl - bundled with Windows 10^+^                                    & exit /b 1)
for /f "delims=" %%v in ('python --version')   do echo   python: %%v
for /f "delims=" %%v in ('node --version')     do echo   node:   %%v
for /f "delims=" %%v in ('npm --version')      do echo   npm:    %%v
echo ------------------------------------------------------------

REM ---------- 2. backend virtualenv ----------
echo [2/6] Backend virtualenv at backend\.venv
if exist "%VENV%\Scripts\activate.bat" (
    echo   existing venv detected - keeping it
) else (
    python -m venv "%VENV%" || (echo Failed to create venv & exit /b 1)
    echo   created
)
call "%VENV%\Scripts\activate.bat"
python -m pip install --upgrade pip --quiet
echo ------------------------------------------------------------

REM ---------- 3. backend dependencies ----------
echo [3/6] Installing backend Python dependencies
python -m pip install -r "%BACKEND%\requirements.txt" || exit /b 1
echo ------------------------------------------------------------

REM ---------- 4. backend .env ----------
echo [4/6] Backend environment file
if exist "%BACKEND%\.env" (
    echo   backend\.env already exists - leaving untouched
) else (
    copy "%BACKEND%\.env.example" "%BACKEND%\.env" >nul
    echo   created backend\.env from .env.example
    echo   WARNING: Open backend\.env and set ES_PASSWORD if you plan to use Elasticsearch.
)
echo ------------------------------------------------------------

REM ---------- 5. frontend ----------
echo [5/6] Installing frontend dependencies
pushd "%FRONTEND%" || exit /b 1
if exist "node_modules" (
    echo   node_modules present - running npm ci
    call npm ci --no-audit --no-fund
) else (
    call npm install --no-audit --no-fund
)
popd
echo ------------------------------------------------------------

REM ---------- 6. optional Elasticsearch probe ----------
echo [6/6] Optional Elasticsearch reachability probe
set "ES_URL=https://localhost:9200"
curl -sk -m 3 -o NUL -w "%%{http_code}" "%ES_URL%" > "%TEMP%\es_code.txt" 2>nul
set /p ES_CODE=<"%TEMP%\es_code.txt"
del "%TEMP%\es_code.txt" 2>nul
if "%ES_CODE%"=="200" (
    echo   OK - Elasticsearch reachable at %ES_URL%
) else if "%ES_CODE%"=="401" (
    echo   OK - Elasticsearch reachable at %ES_URL% ^(auth required, configure ES_PASSWORD^)
) else (
    echo   No Elasticsearch detected at %ES_URL%.
    echo   The platform runs WITHOUT ES - leave ES_ENABLED=false in backend\.env.
    echo   To enable: install Elasticsearch 8.x or 9.x, set ES_ENABLED=true and ES_PASSWORD.
)
echo ------------------------------------------------------------

echo.
echo Setup complete.
echo.
echo Start the BACKEND in one terminal:
echo   call "%VENV%\Scripts\activate.bat"
echo   cd backend ^&^& uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
echo.
echo Start the FRONTEND in another terminal:
echo   cd frontend ^&^& npm run dev    REM http://localhost:3000
echo.
echo Or use Docker for the whole stack:
echo   docker compose up --build     REM API:8000, Web:3000, Postgres:5432
echo.
echo Static dashboard:  http://localhost:8000/
echo API docs:          http://localhost:8000/docs

endlocal
