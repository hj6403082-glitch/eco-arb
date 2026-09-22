@echo off
REM Runs every check CI runs, on this machine. See scripts\verify.py.
setlocal
if exist "%~dp0.venv\Scripts\python.exe" (
  set "ECO_PY=%~dp0.venv\Scripts\python.exe"
) else if exist "%~dp0backend\.venv\Scripts\python.exe" (
  set "ECO_PY=%~dp0backend\.venv\Scripts\python.exe"
) else (
  echo No virtual environment found. Run start.ps1 once to provision it.
  exit /b 1
)
"%ECO_PY%" "%~dp0scripts\verify.py" %*
