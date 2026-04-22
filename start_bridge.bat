@echo off
setlocal
cd /d %~dp0

if not exist .env (
  echo [ERROR] File .env tidak ditemukan.
  echo Copy .env.production.example menjadi .env lalu isi token dan setting.
  pause
  exit /b 1
)

echo [INFO] Menjalankan startup precheck...
python -c "from dotenv import load_dotenv; import os; from pathlib import Path; load_dotenv('.env'); token=os.getenv('BRIDGE_API_TOKEN',''); ok=len(token) >= 16 and token != 'change-me-token'; print('[OK] Token aman' if ok else '[ERROR] BRIDGE_API_TOKEN belum aman'); raise SystemExit(0 if ok else 1)"
if errorlevel 1 (
  echo [ERROR] Precheck gagal. Perbaiki file .env dulu.
  pause
  exit /b 1
)

echo [INFO] Starting XAU MT4 Bridge...
python -m uvicorn webhook_server:app --host 0.0.0.0 --port 8000

if errorlevel 1 (
  echo.
  echo [ERROR] Bridge gagal jalan.
  echo Pastikan dependency sudah diinstall: pip install -r requirements.txt
)

pause
