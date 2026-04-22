from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timezone
import json
import os
import uuid

APP_TOKEN = os.getenv("BRIDGE_API_TOKEN", "change-me-token")
SIGNAL_STORE = os.getenv("SIGNAL_STORE", os.path.join(os.path.dirname(__file__), "latest_signal.json"))
JOURNAL_STORE = os.getenv("JOURNAL_STORE", os.path.join(os.path.dirname(__file__), "journal.log"))

app = FastAPI(title="XAUUSD MT4 Bridge")

class EntryZone(BaseModel):
    min: float
    max: float

class TakeProfit(BaseModel):
    label: str
    price: float
    close_pct: float = Field(gt=0, le=1)

class MarketContext(BaseModel):
    spread_max_points: int = 35
    session: str = "LONDON_NY_OVERLAP"
    news_block_minutes: int = 30

class Signal(BaseModel):
    signal_id: str
    timestamp_utc: str
    symbol: str
    timeframe: str
    side: str
    entry_zone: EntryZone
    stop_loss: float
    take_profit: List[TakeProfit]
    confidence: float = Field(ge=0, le=1)
    invalidation: Optional[str] = ""
    max_signal_age_sec: int = 180
    market_context: MarketContext = MarketContext()


def _check_token(auth_header: Optional[str]):
    if APP_TOKEN == "change-me-token":
        return
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = auth_header.split(" ", 1)[1].strip()
    if token != APP_TOKEN:
        raise HTTPException(status_code=403, detail="invalid token")


def _append_journal(event: dict):
    os.makedirs(os.path.dirname(JOURNAL_STORE), exist_ok=True)
    with open(JOURNAL_STORE, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


@app.get("/")
def health():
    return {"ok": True, "service": "xauusd-mt4-bridge"}


@app.post("/signal")
def publish_signal(signal: Signal, authorization: Optional[str] = Header(default=None)):
    _check_token(authorization)

    if signal.symbol.upper() != "XAUUSD":
        raise HTTPException(status_code=400, detail="only XAUUSD supported")
    if signal.side.upper() not in {"BUY", "SELL"}:
        raise HTTPException(status_code=400, detail="side must be BUY or SELL")
    if len(signal.take_profit) == 0:
        raise HTTPException(status_code=400, detail="take_profit required")

    now = datetime.now(timezone.utc)
    try:
        ts = datetime.fromisoformat(signal.timestamp_utc.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(status_code=400, detail="invalid timestamp_utc")

    age = (now - ts).total_seconds()
    if age > signal.max_signal_age_sec:
        raise HTTPException(status_code=400, detail="signal too old")

    payload = signal.model_dump()
    payload["side"] = payload["side"].upper()
    payload["symbol"] = payload["symbol"].upper()
    payload["received_at"] = now.isoformat()
    payload["status"] = "READY"

    os.makedirs(os.path.dirname(SIGNAL_STORE), exist_ok=True)
    with open(SIGNAL_STORE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    _append_journal({
        "event_id": str(uuid.uuid4()),
        "type": "signal_received",
        "at": now.isoformat(),
        "signal_id": signal.signal_id,
        "symbol": signal.symbol,
        "side": signal.side,
        "confidence": signal.confidence,
    })

    return {"ok": True, "stored": True, "signal_id": signal.signal_id}


@app.get("/signal/latest")
def latest_signal(authorization: Optional[str] = Header(default=None)):
    _check_token(authorization)
    if not os.path.exists(SIGNAL_STORE):
        return {"ok": True, "signal": None}
    with open(SIGNAL_STORE, "r", encoding="utf-8") as f:
        return {"ok": True, "signal": json.load(f)}


@app.post("/execution/report")
def execution_report(payload: dict, authorization: Optional[str] = Header(default=None)):
    _check_token(authorization)
    payload["type"] = "execution_report"
    payload["at"] = datetime.now(timezone.utc).isoformat()
    _append_journal(payload)
    return {"ok": True}
