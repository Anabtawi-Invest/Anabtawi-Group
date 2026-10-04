@echo off
REM Builds dist\AnabtawiPOSBackup.exe (run on a Windows PC with Python 3.11+ installed).
cd /d "%~dp0"
python -m venv .venv || goto :error
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip || goto :error
python -m pip install -r requirements.txt || goto :error
python -c "from sqlcipher3 import dbapi2" || goto :error
pyinstaller --onefile --console --name AnabtawiPOSBackup --hidden-import sqlcipher3 --collect-all sqlcipher3 pos_backup_helper.py || goto :error
echo.
echo Built: %~dp0dist\AnabtawiPOSBackup.exe
goto :eof

:error
echo Build failed.
exit /b 1
