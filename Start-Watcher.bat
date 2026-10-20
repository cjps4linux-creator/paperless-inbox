@echo off
setlocal
set PYTHONPATH=

rem Resolve the project directory from this script's own location.
set "APP_DIR=%~dp0"

rem Prefer a project-local virtualenv, then an environment override,
rem then a system Python on PATH.
set "PYTHON="
if exist "%APP_DIR%.venv\Scripts\python.exe" set "PYTHON=%APP_DIR%.venv\Scripts\python.exe"
if not defined PYTHON if defined HERMES_PYTHON set "PYTHON=%HERMES_PYTHON%"
if not defined PYTHON for %%P in (python.exe python) do if not defined PYTHON set "PYTHON=%%~$PATH:P"

if not defined PYTHON (
  echo [launcher] No Python interpreter found.
  echo [launcher] Create a virtualenv at "%APP_DIR%.venv" or set HERMES_PYTHON.
  pause
  exit /b 1
)

cd /d "%APP_DIR%"
"%PYTHON%" watcher.py

pause
endlocal
