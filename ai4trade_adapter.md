# AI4Trade Adapter Notes

Bridge ini sekarang bisa menarik sinyal dari `ai4trade.ai` lalu mengubahnya menjadi format internal MT4 bridge.

## Cara kerja

1. Poll `AI4TRADE_FEED_URL` tiap `AI4TRADE_POLL_SEC` detik
2. Ambil daftar signal terbaru
3. Filter hanya signal yang relevan:
   - `agent_id` cocok jika `AI4TRADE_AGENT_ID` diisi
   - market forex/xau/gold/xauusd
   - symbol `XAUUSD`
   - side/action BUY atau SELL
4. Mapping ke format internal bridge
5. Simpan ke `latest_signal.json`
6. EA MT4 polling `/signal/latest`

## Catatan penting

Schema `ai4trade.ai` bukan schema execution-ready penuh untuk MT4, jadi adapter memakai asumsi:
- `entry_price` / `price` dipakai sebagai basis entry zone
- SL/TP dibuat heuristik sederhana
- timeframe diset default `M15`
- content dipakai sebagai invalidation note

Kalau nanti ada schema signal XAU yang lebih spesifik dari `ai4trade.ai`, adapter ini sebaiknya diperbarui.
