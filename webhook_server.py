from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timezone
import json
import os
import uuid
import httpx
import asyncio
from contextlib import asynccontextmanager
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(__file__)
load_dotenv(os.path.join(BASE_DIR, ".env"))

STARTUP_STATUS = {
    "ready": False,
    "checks": [],
    "checked_at": None,
}

APP_TOKEN = os.getenv("BRIDGE_API_TOKEN", "change-me-token")
SIGNAL_STORE = os.getenv("SIGNAL_STORE", os.path.join(BASE_DIR, "latest_signal.json"))
JOURNAL_STORE = os.getenv("JOURNAL_STORE", os.path.join(BASE_DIR, "journal.log"))
NEWS_CACHE_FILE = os.getenv("NEWS_CACHE_FILE", os.path.join(BASE_DIR, "news_cache.json"))
NEWS_CACHE = {
    "latest": [],
    "updated_at": None,
}
NEWS_URL = os.getenv("NEWS_CALENDAR_URL", "https://nfs.faireconomy.media/ff_calendar_thisweek.json")
NEWS_REFRESH_SEC = int(os.getenv("NEWS_REFRESH_SEC", "3600"))
DEFAULT_NEWS_BLOCK_MINUTES = int(os.getenv("DEFAULT_NEWS_BLOCK_MINUTES", "30"))

@asynccontextmanager
async def lifespan(app: FastAPI):
    await refresh_news_cache()
    _run_startup_checks()
    task = asyncio.create_task(update_news_loop())
    try:
        yield
    finally:
        task.cancel()

app = FastAPI(title="XAUUSD MT4 Bridge", lifespan=lifespan)

def _save_news_cache_to_file():
    try:
        with open(NEWS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(NEWS_CACHE, f, indent=2)
    except Exception as e:
        print(f"Error saving news cache: {e}")

def _load_news_cache_from_file():
    if not os.path.exists(NEWS_CACHE_FILE):
        return
    try:
        with open(NEWS_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                NEWS_CACHE["latest"] = data.get("latest", [])
                NEWS_CACHE["updated_at"] = data.get("updated_at")
    except Exception as e:
        print(f"Error loading news cache: {e}")

async def refresh_news_cache():
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(NEWS_URL, timeout=10)
            response.raise_for_status()
            news_data = response.json()
            usd_high = [
                n for n in news_data
                if n.get("country") == "USD" and n.get("impact") == "High"
            ]
            NEWS_CACHE["latest"] = usd_high
            NEWS_CACHE["updated_at"] = datetime.now(timezone.utc).isoformat()
            _save_news_cache_to_file()
    except Exception as e:
        print(f"Error fetching news: {e}")
        _load_news_cache_from_file()

async def update_news_loop():
    while True:
        await refresh_news_cache()
        _run_startup_checks()
        await asyncio.sleep(NEWS_REFRESH_SEC)

def get_active_news_event(block_minutes: int = DEFAULT_NEWS_BLOCK_MINUTES):
    events = NEWS_CACHE.get("latest", [])
    now = datetime.now(timezone.utc)
    for event in events:
        try:
            event_time = datetime.fromisoformat(event["date"].replace("Z", "+00:00"))
            diff = abs((now - event_time).total_seconds()) / 60.0
            if diff <= block_minutes:
                return {
                    "title": event.get("title", "Unknown Event"),
                    "country": event.get("country", "USD"),
                    "impact": event.get("impact", "High"),
                    "date": event.get("date"),
                    "minutes_from_event": round(diff, 2),
                }
        except Exception:
            continue
    return None

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
    if not APP_TOKEN or APP_TOKEN == "change-me-token":
        raise HTTPException(status_code=500, detail="Bridge API Token not configured safely on server")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = auth_header.split(" ", 1)[1].strip()
    if token != APP_TOKEN:
        raise HTTPException(status_code=403, detail="invalid token")


def _append_journal(event: dict):
    os.makedirs(os.path.dirname(JOURNAL_STORE), exist_ok=True)
    with open(JOURNAL_STORE, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")

def _run_startup_checks():
    checks = []

    env_exists = os.path.exists(os.path.join(BASE_DIR, ".env"))
    checks.append({
        "name": "env_file_present",
        "ok": env_exists,
        "detail": os.path.join(BASE_DIR, ".env"),
    })

    strong_token = bool(APP_TOKEN and APP_TOKEN != "change-me-token" and len(APP_TOKEN) >= 16)
    checks.append({
        "name": "bridge_token_safe",
        "ok": strong_token,
        "detail": "BRIDGE_API_TOKEN must be set and not default",
    })

    news_ready = bool(NEWS_CACHE.get("updated_at") or os.path.exists(NEWS_CACHE_FILE))
    checks.append({
        "name": "news_source_or_cache_ready",
        "ok": news_ready,
        "detail": NEWS_CACHE.get("updated_at") or NEWS_CACHE_FILE,
    })

    signal_dir = os.path.dirname(SIGNAL_STORE) or BASE_DIR
    journal_dir = os.path.dirname(JOURNAL_STORE) or BASE_DIR
    signal_writable = os.path.isdir(signal_dir) and os.access(signal_dir, os.W_OK)
    journal_writable = os.path.isdir(journal_dir) and os.access(journal_dir, os.W_OK)
    checks.append({
        "name": "signal_store_writable",
        "ok": signal_writable,
        "detail": signal_dir,
    })
    checks.append({
        "name": "journal_store_writable",
        "ok": journal_writable,
        "detail": journal_dir,
    })

    startup_ready = all(item["ok"] for item in checks)
    STARTUP_STATUS["ready"] = startup_ready
    STARTUP_STATUS["checks"] = checks
    STARTUP_STATUS["checked_at"] = datetime.now(timezone.utc).isoformat()
    return STARTUP_STATUS


@app.get("/")
def health():
    return {
        "ok": True,
        "service": "xauusd-mt4-bridge",
        "ready": STARTUP_STATUS.get("ready", False),
        "checked_at": STARTUP_STATUS.get("checked_at"),
    }

@app.get("/health/ready")
def health_ready(authorization: Optional[str] = Header(default=None)):
    _check_token(authorization)
    return {
        "ok": True,
        "startup": STARTUP_STATUS,
    }

@app.get("/news/status")
def news_status(authorization: Optional[str] = Header(default=None)):
    _check_token(authorization)
    active_news = get_active_news_event(DEFAULT_NEWS_BLOCK_MINUTES)
    return {
        "ok": True,
        "news_blocked": active_news is not None,
        "active_news": active_news,
        "news_updated_at": NEWS_CACHE.get("updated_at"),
        "cached_events": len(NEWS_CACHE.get("latest", [])),
    }


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
    
    active_news = get_active_news_event(DEFAULT_NEWS_BLOCK_MINUTES)
    news_blocked = active_news is not None

    if not os.path.exists(SIGNAL_STORE):
        return {
            "ok": True,
            "signal": None,
            "news_blocked": news_blocked,
            "active_news": active_news,
            "news_updated_at": NEWS_CACHE.get("updated_at"),
        }

    with open(SIGNAL_STORE, "r", encoding="utf-8") as f:
        data = json.load(f)
        block_minutes = data.get("market_context", {}).get("news_block_minutes", DEFAULT_NEWS_BLOCK_MINUTES)
        active_news = get_active_news_event(block_minutes)
        news_blocked = active_news is not None
        if news_blocked:
            data["status"] = "BLOCKED_BY_NEWS"
        return {
            "ok": True,
            "signal": data,
            "news_blocked": news_blocked,
            "active_news": active_news,
            "news_updated_at": NEWS_CACHE.get("updated_at"),
        }


@app.post("/execution/report")
def execution_report(payload: dict, authorization: Optional[str] = Header(default=None)):
    _check_token(authorization)
    payload["type"] = "execution_report"
    payload["at"] = datetime.now(timezone.utc).isoformat()
    _append_journal(payload)
    return {"ok": True}
