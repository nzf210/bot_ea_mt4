from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from datetime import datetime, timezone
import json
import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(__file__)
load_dotenv(os.path.join(BASE_DIR, ".env"))

APP_TOKEN = os.getenv("BRIDGE_API_TOKEN", "change-me-token")
RECEIVER_PORT = int(os.getenv("MARKET_RECEIVER_PORT", "8010"))
SNAPSHOT_STORE = os.getenv("MARKET_SNAPSHOT_STORE", os.path.join(BASE_DIR, "latest_market_snapshot.json"))
ALLOWED_SYMBOLS = {s.strip().upper() for s in os.getenv("AI4TRADE_ALLOWED_SYMBOLS", "XAUUSD,GBPUSD,EURUSD").split(",") if s.strip()}
SYMBOL_ALIASES = {
    "GOLD": "XAUUSD",
}

app = FastAPI(title="Market Snapshot Receiver")

class OHLC(BaseModel):
    open: float
    high: float
    low: float
    close: float

class Snapshot(BaseModel):
    symbol: str
    timeframe: str = "M1"
    bid: float
    ask: float
    spread_points: int
    ohlc: OHLC
    volume: float = 0

class SnapshotBatch(BaseModel):
    timestamp_utc: str
    snapshots: List[Snapshot]


def _check_token(auth_header: Optional[str]):
    if not APP_TOKEN or APP_TOKEN == "change-me-token":
        raise HTTPException(status_code=500, detail="Bridge API Token not configured safely on server")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = auth_header.split(" ", 1)[1].strip()
    if token != APP_TOKEN:
        raise HTTPException(status_code=403, detail="invalid token")

@app.get("/")
def health():
    return {"ok": True, "service": "market-snapshot-receiver", "port": RECEIVER_PORT}

@app.post("/market/snapshot")
def receive_snapshot(batch: SnapshotBatch, authorization: Optional[str] = Header(default=None)):
    _check_token(authorization)
    try:
        datetime.fromisoformat(batch.timestamp_utc.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(status_code=400, detail="invalid timestamp_utc")

    filtered = []
    for snap in batch.snapshots:
        raw_symbol = snap.symbol.upper()
        symbol = SYMBOL_ALIASES.get(raw_symbol, raw_symbol)
        if symbol not in ALLOWED_SYMBOLS:
            continue
        item = snap.model_dump()
        item["symbol"] = symbol
        item["raw_symbol"] = raw_symbol
        filtered.append(item)

    payload = {
        "timestamp_utc": batch.timestamp_utc,
        "snapshots": filtered,
        "received_at": datetime.now(timezone.utc).isoformat(),
    }

    with open(SNAPSHOT_STORE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    return {"ok": True, "stored": len(filtered), "symbols": [x["symbol"] for x in filtered]}

@app.get("/market/snapshot/latest")
def latest_snapshot(authorization: Optional[str] = Header(default=None)):
    _check_token(authorization)
    if not os.path.exists(SNAPSHOT_STORE):
        return {"ok": True, "snapshot": None}
    with open(SNAPSHOT_STORE, "r", encoding="utf-8") as f:
        return {"ok": True, "snapshot": json.load(f)}
