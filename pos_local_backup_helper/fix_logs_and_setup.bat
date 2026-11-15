@echo off
:: Run this by right-click -> Run as administrator
cd /d "%~dp0"

echo.
echo === Fix logs folder ===
if exist "C:\ProgramData\AnabtawiPOS\logs" (
  attrib -r -s -h "C:\ProgramData\AnabtawiPOS\logs" >nul 2>&1
  rmdir /s /q "C:\ProgramData\AnabtawiPOS\logs" >nul 2>&1
  del /f /q "C:\ProgramData\AnabtawiPOS\logs" >nul 2>&1
)
mkdir "C:\ProgramData\AnabtawiPOS" >nul 2>&1
mkdir "C:\ProgramData\AnabtawiPOS\logs" >nul 2>&1
echo Logs folder ready.

echo.
echo === Setup (answer the questions) ===
".\.venv\Scripts\python.exe" pos_backup_helper.py setup
if errorlevel 1 (
  echo.
  echo Setup failed or was cancelled. If it said already configured, that is OK.
  pause
)

echo.
echo === Starting helper (leave this window open) ===
".\.venv\Scripts\python.exe" pos_backup_helper.py run
pause
