# XAUUSD MT4 Bridge

Paket ini berisi:

1. `webhook_server.py` - FastAPI webhook untuk menerima dan menyimpan sinyal XAUUSD
2. `mt4_ai_bridge.mq4` - EA MT4 yang polling sinyal dan membuka order
3. `signal_example.json` - contoh payload sinyal

## 1. Jalankan webhook server

### Install dependency
```bash
pip install fastapi uvicorn pydantic
```

### Run server
```bash
cd xau_mt4_bridge
export BRIDGE_API_TOKEN="ganti-token-aman"
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
   - `BridgeToken` = token yang sama
5. Tambahkan URL ke MT4:
   - `Tools > Options > Expert Advisors > Allow WebRequest for listed URL`
   - tambahkan `http://IP_SERVER:8000`

## 4. Cara kerja

- Webhook menerima sinyal JSON
- EA MT4 polling `/signal/latest`
- Jika symbol cocok, spread aman, belum ada posisi, dan harga masuk entry zone, EA akan `OrderSend`

## 5. Guard bawaan

- hanya untuk `XAUUSD`
- maksimal 1 posisi aktif
- filter spread
- risk-based lot sizing
- max daily loss guard

## 6. Catatan penting

- Parser JSON di MQL4 ini versi ringan, cocok untuk schema sederhana ini
- Untuk production, sebaiknya tambahkan:
  - validasi news filter nyata
  - partial TP management
  - trailing stop
  - execution report balik ke webhook
  - VPS/local bridge yang aman via private network
# bot_ea_mt4
