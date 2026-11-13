@echo off
REM Windows Task Scheduler helper. Point a Daily task at this file.
cd /d "%~dp0.."
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
python -m app.run_daily >> data\run.log 2>&1
