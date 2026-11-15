@echo off
:: Run this by right-click -> Run as administrator
cd /d "%~dp0"
".\.venv\Scripts\python.exe" pos_backup_helper.py run
pause
