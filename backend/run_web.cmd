@echo off
REM ============================================================
REM  TRIDENT web bridge launcher (Windows)
REM  Starts the backend engine + API and serves the frontend UI
REM  (../frontend/index.html) on http://localhost:8765
REM  Prefers the repo .venv if present, else uses python on PATH.
REM  Usage:  run_web.cmd            (default port 8765)
REM          run_web.cmd --port 9000
REM ============================================================
setlocal
cd /d "%~dp0"
if exist "..\.venv\Scripts\python.exe" (
  "..\.venv\Scripts\python.exe" -m src.web.server %*
) else if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m src.web.server %*
) else (
  python -m src.web.server %*
)
endlocal
