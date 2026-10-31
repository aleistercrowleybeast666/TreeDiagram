@echo off
cd /d "%~dp0"
python -B run.py
if errorlevel 1 pause

