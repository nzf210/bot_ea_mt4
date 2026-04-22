# XAU MT4 Bridge Deploy Checklist (Windows RDP + MT4)

## 1. Siapkan file
- Copy folder `xau_mt4_bridge` ke Windows RDP
- Copy `mt4_ai_bridge.mq4` ke folder `MQL4/Experts/`
- Copy `.env.production.example` menjadi `.env`

## 2. Isi konfigurasi `.env`
Minimal isi:
```env
BRIDGE_API_TOKEN=ganti-dengan-token-random-panjang
DEFAULT_NEWS_BLOCK_MINUTES=45
NEWS_REFRESH_SEC=1800
```
Saran:
- token minimal 16 karakter
- jangan pakai `change-me-token`

## 3. Install dependency Python
Buka PowerShell di folder project:
```powershell
pip install -r requirements.txt
```

## 4. Jalankan bridge
```powershell
start_bridge.bat
```
Pastikan precheck lolos.

## 5. Verifikasi bridge
Cek health umum:
```powershell
curl http://127.0.0.1:8000/
```

Cek readiness:
```powershell
curl http://127.0.0.1:8000/health/ready -H "Authorization: Bearer TOKEN_KAMU"
```

Cek news filter:
```powershell
curl http://127.0.0.1:8000/news/status -H "Authorization: Bearer TOKEN_KAMU"
```

## 6. Setup MT4
Di MT4:
- attach `mt4_ai_bridge` ke chart `XAUUSD`
- isi `BridgeBaseUrl = http://IP_RDP:8000`
- isi `BridgeToken = TOKEN_KAMU`
- pastikan token sama persis dengan `.env`

Aktifkan WebRequest:
- `Tools > Options > Expert Advisors`
- centang `Allow WebRequest for listed URL`
- tambahkan `http://IP_RDP:8000`

## 7. Compile EA
- buka `mt4_ai_bridge.mq4` di MetaEditor
- tekan `F7`
- pastikan tidak ada error compile

## 8. Uji end-to-end
Kirim sample signal:
```powershell
curl -X POST "http://127.0.0.1:8000/signal" -H "Authorization: Bearer TOKEN_KAMU" -H "Content-Type: application/json" --data @signal_example.json
```

Cek latest signal:
```powershell
curl http://127.0.0.1:8000/signal/latest -H "Authorization: Bearer TOKEN_KAMU"
```

Pantau:
- journal MT4
- `journal.log`
- status news block

## 9. Hardening production
- gunakan Windows Firewall, batasi akses ke port 8000
- kalau bisa, allow hanya IP tertentu
- jangan expose token di chat/log publik
- simpan backup `.env` secara aman

## 10. Sebelum live
- test di demo account dulu
- pastikan lot sizing sesuai broker XAUUSD
- cek spread real broker
- cek EA tidak conflict dengan EA lain
- pastikan news filter bekerja saat jam rilis USD High Impact
- review `journal.log` dan `execution_report`

## 11. Go live
Kalau semua lolos:
- jalankan bridge
- buka MT4
- aktifkan AutoTrading
- monitor trade pertama secara manual
