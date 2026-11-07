@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3.13 -m venv .venv
  if errorlevel 1 goto fail
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto fail
set FISCYCLE_MODEL_SOURCE=local
set FISCYCLE_RUNTIME_ENV=development
set YOLO_OFFLINE=true
echo Buka http://127.0.0.1:8001/docs setelah server siap. Ctrl+C untuk berhenti.
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --workers 1
if errorlevel 1 goto fail
exit /b 0
:fail
echo Gagal. Pastikan Python 3.13 64-bit terpasang dan internet tersedia saat instalasi dependensi.
pause
exit /b 1
