# XAUUSD MT4 Bridge

Paket ini berisi:

1. `webhook_server.py` - FastAPI webhook untuk menerima dan menyimpan sinyal XAUUSD
2. `mt4_ai_bridge.mq4` - EA MT4 yang polling sinyal dan membuka order
3. `signal_example.json` - contoh payload sinyal

## 1. Jalankan webhook server

### Install dependency
```bash
pip install fastapi uvicorn pydantic httpx python-dotenv
```

### Setup .env
```bash
cd xau_mt4_bridge
cp .env.example .env
```

Untuk production, kamu juga bisa mulai dari:
```bash
cp .env.production.example .env
```

Lalu edit `.env`:
```env
BRIDGE_API_TOKEN=ganti-token-aman
NEWS_REFRESH_SEC=3600
DEFAULT_NEWS_BLOCK_MINUTES=30
```

### Run server
```bash
cd xau_mt4_bridge
uvicorn webhook_server:app --host 0.0.0.0 --port 8000
```

## 2. Publish sinyal ke webhook

```bash
curl -X POST "http://127.0.0.1:8000/signal" \
  -H "Authorization: Bearer ganti-token-aman" \
  -H "Content-Type: application/json" \
  --data @signal_example.json
```

Cek sinyal terakhir:
```bash
curl "http://127.0.0.1:8000/signal/latest" \
  -H "Authorization: Bearer ganti-token-aman"
```

## 3. Pasang EA ke MT4

1. Copy `mt4_ai_bridge.mq4` ke folder:
   - `MQL4/Experts/`
2. Restart MT4 atau refresh Navigator
3. Attach EA ke chart `XAUUSD`
4. Isi input:
   - `BridgeBaseUrl` = `http://IP_SERVER:8000`
   - `BridgeToken` = token yang sama dari file `.env`
   - pastikan token di EA sama persis dengan `BRIDGE_API_TOKEN`
5. Tambahkan URL ke MT4:
   - `Tools > Options > Expert Advisors > Allow WebRequest for listed URL`
   - tambahkan `http://IP_SERVER:8000`

## 4. Cara kerja

Mode 1, manual/external webhook:
- Webhook menerima sinyal JSON
- EA MT4 polling `/signal/latest`
- Jika symbol cocok, spread aman, belum ada posisi, dan harga masuk entry zone, EA akan `OrderSend`

Mode 2, adapter `ai4trade.ai`:
- Bridge polling `https://ai4trade.ai/api/signals/feed`
- signal dari `ai4trade.ai` di-mapping ke format internal MT4 bridge
- hasil mapping disimpan ke `latest_signal.json`
- EA MT4 tetap polling `/signal/latest` seperti biasa

## 5. Guard bawaan

- hanya untuk `XAUUSD`
- maksimal 1 posisi aktif per symbol + magic number
- filter spread
- risk-based lot sizing
- max daily loss guard
- auto news filter untuk berita High Impact USD

## 6. Integrasi ai4trade.ai

Bridge mendukung adapter dasar untuk `ai4trade.ai`.

Tambahkan ke `.env`:
```env
AI4TRADE_TOKEN=token-agent-ai4trade
AI4TRADE_AGENT_ID=3065
AI4TRADE_REQUIRE_AGENT_MATCH=true
AI4TRADE_ALLOWED_SYMBOLS=XAUUSD,GBPUSD,EURUSD
AI4TRADE_FEED_URL=https://ai4trade.ai/api/signals/feed
AI4TRADE_POLL_SEC=30
```

Catatan:
- schema native `ai4trade.ai` tidak sama dengan schema internal bridge
- adapter akan mencoba mapping signal feed ke format MT4 bridge
- kamu bisa pilih strict mode dengan `AI4TRADE_REQUIRE_AGENT_MATCH=true`
- kamu bisa whitelist pair lewat `AI4TRADE_ALLOWED_SYMBOLS=XAUUSD,GBPUSD,EURUSD`
- raw payload terakhir akan disimpan ke file agar mudah debug
- tersedia dry-run log untuk menjelaskan kenapa signal dipilih atau ditolak
- heuristik level harga sekarang mendukung XAUUSD dan pair forex utama, tapi tetap belum sebaik signal execution-ready asli

Lihat juga: `ai4trade_adapter.md`

Endpoint debug tambahan:
- `GET /ai4trade/status`
- `GET /ai4trade/raw`
- `GET /ai4trade/dry-run`

## 7. Publish signal ke ai4trade.ai

Sekarang tersedia script publisher untuk agent kamu:
- `publish_signal.py`
- `publish_signal_example.json`

Contoh publish:
```bash
python publish_signal.py publish_signal_example.json
```

Script ini akan:
- baca file JSON signal lokal
- ubah ke schema `POST /api/signals/realtime`
- publish memakai `AI4TRADE_TOKEN`

Env yang dipakai publisher:
```env
AI4TRADE_PUBLISH_URL=https://ai4trade.ai/api/signals/realtime
AI4TRADE_PUBLISH_MARKET=forex
AI4TRADE_PUBLISH_QUANTITY=0.01
```

## 8. File tambahan production

- `requirements.txt` untuk install dependency cepat
- `start_bridge.bat` untuk start bridge di Windows RDP
- `.env.production.example` sebagai template setting production
- startup precheck untuk validasi token sebelum server jalan
- endpoint `/health/ready` untuk cek readiness bridge
- `ai4trade_adapter.md` untuk catatan integrasi ai4trade

## 9. News filter gratis

Bridge akan mengambil kalender news gratis dari Forex Factory JSON feed:
- `https://nfs.faireconomy.media/ff_calendar_thisweek.json`

Perilaku default:
- refresh cache news setiap 1 jam
- block trading 30 menit sebelum/sesudah berita High Impact USD
- endpoint `/signal/latest` akan mengembalikan `news_blocked: true` dan mengubah status signal menjadi `BLOCKED_BY_NEWS`

Pengaturan memakai file `.env`.
Contoh tersedia di `.env.example`.

### Security Note
For production on Windows RDP:
1. **Always** set `BRIDGE_API_TOKEN` to a strong random string, minimal 16 karakter.
2. In MT4 EA Inputs, match this token exactly.
3. If the server is on a public IP, use a firewall to allow only your RDP IP.
4. `start_bridge.bat` akan menolak start jika token masih default atau terlalu pendek.

### Windows RDP Deployment
1. Install [Python 3.10+](https://www.python.org/downloads/windows/) on the RDP if running the server there.
2. Install dependency:
   ```powershell
   pip install -r requirements.txt
   ```
3. Buka folder project, copy `.env.production.example` menjadi `.env`.
4. Edit `.env` dan isi minimal:
   ```env
   BRIDGE_API_TOKEN=your-secure-token
   DEFAULT_NEWS_BLOCK_MINUTES=45
   NEWS_REFRESH_SEC=1800
   ```
5. Jalankan bridge dengan:
   ```powershell
   start_bridge.bat
   ```
6. Follow the MT4 setup in step 3 above.
7. Di MT4, pastikan `Allow WebRequest` mencakup base URL bridge.
8. Untuk cek news filter manual:
   - `GET /news/status`
9. Untuk cek readiness bridge:
   - `GET /health/ready`
   - butuh Bearer token
