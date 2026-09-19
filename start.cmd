@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto frontend
where py >nul 2>nul
if not errorlevel 1 (
  py -3 -m venv .venv
) else (
  python -m venv .venv
)
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r backend\requirements.txt
if errorlevel 1 goto failed
:frontend
if exist "frontend\dist\index.html" goto launch
call npm.cmd ci --prefix frontend
if errorlevel 1 goto failed
call npm.cmd run build --prefix frontend
if errorlevel 1 goto failed
:launch
set ECO_ARB_DEMO_MODE=scenario
echo.
echo Open http://127.0.0.1:8000 in your browser after Application startup complete.
echo Keep this window open. Press Ctrl+C to stop the server.
".venv\Scripts\python.exe" -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --no-access-log
if errorlevel 1 goto failed
exit /b 0
:failed
echo.
echo Startup failed. Check the error above. Python 3.10+ is required.
echo Node.js 22.12+ is required only if the frontend build is missing.
pause
exit /b 1
