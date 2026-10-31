@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -B run.py
) else (
    python -B run.py
)
if errorlevel 1 pause

