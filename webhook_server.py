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

from gemini_decider import decide_trade, normalize_symbol

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
SNAPSHOT_STORE = os.getenv("MARKET_SNAPSHOT_STORE", os.path.join(BASE_DIR, "latest_market_snapshot.json"))
GENERATED_SIGNAL_STORE = os.getenv("AI_GENERATED_SIGNAL_STORE", os.path.join(BASE_DIR, "generated_ai_signal.json"))
AI_SIGNAL_STATE_FILE = os.getenv("AI_SIGNAL_STATE_FILE", os.path.join(BASE_DIR, "ai_signal_state.json"))
AI4TRADE_TOKEN = os.getenv("AI4TRADE_TOKEN", "")
AI4TRADE_AGENT_ID = os.getenv("AI4TRADE_AGENT_ID", "")
AI4TRADE_REQUIRE_AGENT_MATCH = os.getenv("AI4TRADE_REQUIRE_AGENT_MATCH", "true").lower() in {"1", "true", "yes", "on"}
AI4TRADE_ALLOWED_SYMBOLS = {
    s.strip().upper() for s in os.getenv("AI4TRADE_ALLOWED_SYMBOLS", "XAUUSD").split(",") if s.strip()
}
AI4TRADE_FEED_URL = os.getenv("AI4TRADE_FEED_URL", "https://ai4trade.ai/api/signals/feed")
AI4TRADE_POLL_SEC = int(os.getenv("AI4TRADE_POLL_SEC", "30"))
AI4TRADE_MIN_CONFIDENCE = float(os.getenv("AI4TRADE_MIN_CONFIDENCE", "0.5"))
AI4TRADE_RAW_STORE = os.getenv("AI4TRADE_RAW_STORE", os.path.join(BASE_DIR, "ai4trade_last_raw.json"))
AI4TRADE_DRY_RUN = os.getenv("AI4TRADE_DRY_RUN", "true").lower() in {"1", "true", "yes", "on"}
AI4TRADE_DRY_RUN_LOG = os.getenv("AI4TRADE_DRY_RUN_LOG", os.path.join(BASE_DIR, "ai4trade_dry_run.log"))
AI_SIGNAL_PUBLISH_ENABLED = os.getenv("AI_SIGNAL_PUBLISH_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
AI_SIGNAL_IGNORE_PUBLISH_ERRORS = os.getenv("AI_SIGNAL_IGNORE_PUBLISH_ERRORS", "true").lower() in {"1", "true", "yes", "on"}
AI_SIGNAL_PROCESSING_INTERVAL_SEC = float(os.getenv("AI_SIGNAL_PROCESSING_INTERVAL_SEC", "0.1"))
ACTIVE_SIGNAL_TTL_SEC = int(os.getenv("ACTIVE_SIGNAL_TTL_SEC", "120"))
REVERSAL_ON_OPEN_POSITION = os.getenv("REVERSAL_ON_OPEN_POSITION", "false").lower() in {"1", "true", "yes", "on"}
POST_CLOSE_COOLDOWN_SEC = int(os.getenv("POST_CLOSE_COOLDOWN_SEC", "30"))
LOSS_COOLDOWN_SEC = int(os.getenv("LOSS_COOLDOWN_SEC", "180"))
MAX_CONSECUTIVE_LOSSES_PER_SIDE = int(os.getenv("MAX_CONSECUTIVE_LOSSES_PER_SIDE", "2"))
XAU_ENTRY_ZONE_MIN = float(os.getenv("XAU_ENTRY_ZONE_MIN", "0.5"))
XAU_ENTRY_ZONE_MAX = float(os.getenv("XAU_ENTRY_ZONE_MAX", "1.5"))
XAU_ENTRY_ZONE_RANGE_MULT = float(os.getenv("XAU_ENTRY_ZONE_RANGE_MULT", "0.35"))
FOREX_ENTRY_ZONE_MIN = float(os.getenv("FOREX_ENTRY_ZONE_MIN", "0.0005"))
FOREX_ENTRY_ZONE_MAX = float(os.getenv("FOREX_ENTRY_ZONE_MAX", "0.0015"))
FOREX_ENTRY_ZONE_RANGE_MULT = float(os.getenv("FOREX_ENTRY_ZONE_RANGE_MULT", "0.25"))
NEWS_URL = os.getenv("NEWS_CALENDAR_URL", "https://nfs.faireconomy.media/ff_calendar_thisweek.json")
NEWS_REFRESH_SEC = int(os.getenv("NEWS_REFRESH_SEC", "3600"))
DEFAULT_NEWS_BLOCK_MINUTES = int(os.getenv("DEFAULT_NEWS_BLOCK_MINUTES", "30"))

NEWS_CACHE = {
    "latest": [],
    "updated_at": None,
}
AI4TRADE_STATE = {
    "last_fetch_at": None,
    "last_signal_count": 0,
    "last_selected": None,
    "last_error": None,
}
SNAPSHOT_STATE = {
    "last_received_at": None,
    "last_processed_at": None,
    "last_signal_id": None,
    "last_decision": None,
    "last_reason": None,
    "last_decision_source": None,
    "last_no_trade_at": None,
    "last_no_trade_reason": None,
    "last_no_trade_symbol": None,
    "last_snapshot_timeframe": None,
    "last_execution_at": None,
    "last_execution_signal_id": None,
    "last_execution_type": None,
    "last_execution_ticket": None,
    "last_trade_outcome": None,
    "last_loss_side": None,
    "last_loss_at": None,
    "consecutive_losses": {"BUY": 0, "SELL": 0},
    "queue_size": 0,
    "last_error": None,
}
SNAPSHOT_QUEUE: asyncio.Queue = asyncio.Queue()


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


class OHLC(BaseModel):
    open: float
    high: float
    low: float
    close: float


class SnapshotCandle(BaseModel):
    shift: int = 0
    open: float
    high: float
    low: float
    close: float
    volume: float = 0


class Snapshot(BaseModel):
    symbol: str
    timeframe: str = "M1"
    bid: float
    ask: float
    spread_points: int
    ohlc: OHLC
    volume: float = 0
    recent_candles: List[SnapshotCandle] = []


class SnapshotBatch(BaseModel):
    timestamp_utc: str
    snapshots: List[Snapshot]


@asynccontextmanager
async def lifespan(app: FastAPI):
    await refresh_news_cache()
    await refresh_ai4trade_signal_once()
    _run_startup_checks()
    news_task = asyncio.create_task(update_news_loop())
    ai4trade_task = asyncio.create_task(update_ai4trade_loop())
    snapshot_task = asyncio.create_task(snapshot_worker_loop())
    try:
        yield
    finally:
        news_task.cancel()
        ai4trade_task.cancel()
        snapshot_task.cancel()


app = FastAPI(title="XAUUSD MT4 Bridge", lifespan=lifespan)


def _check_token(auth_header: Optional[str]):
    if not APP_TOKEN or APP_TOKEN == "change-me-token":
        raise HTTPException(status_code=500, detail="Bridge API Token not configured safely on server")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = auth_header.split(" ", 1)[1].strip()
    if token != APP_TOKEN:
        raise HTTPException(status_code=403, detail="invalid token")


def _ensure_parent_dir(path: str):
    parent = os.path.dirname(path) or BASE_DIR
    os.makedirs(parent, exist_ok=True)


def _append_journal(event: dict):
    _ensure_parent_dir(JOURNAL_STORE)
    with open(JOURNAL_STORE, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


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


def _save_ai4trade_raw(payload):
    try:
        with open(AI4TRADE_RAW_STORE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except Exception as e:
        print(f"Error saving ai4trade raw payload: {e}")


def _append_ai4trade_dry_run(event: dict):
    try:
        with open(AI4TRADE_DRY_RUN_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
    except Exception as e:
        print(f"Error writing ai4trade dry run log: {e}")


def _save_snapshot_batch(payload: dict):
    _ensure_parent_dir(SNAPSHOT_STORE)
    with open(SNAPSHOT_STORE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def _load_state():
    if not os.path.exists(AI_SIGNAL_STATE_FILE):
        return {"last_keys": {}}
    try:
        with open(AI_SIGNAL_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"last_keys": {}}


def _save_state(state: dict):
    _ensure_parent_dir(AI_SIGNAL_STATE_FILE)
    with open(AI_SIGNAL_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def _store_signal_payload(payload: dict):
    _ensure_parent_dir(SIGNAL_STORE)
    with open(SIGNAL_STORE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def _store_generated_signal(payload: dict):
    _ensure_parent_dir(GENERATED_SIGNAL_STORE)
    with open(GENERATED_SIGNAL_STORE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(value, max_value))


def _snapshot_range(snapshot: dict) -> float:
    ohlc = snapshot.get("ohlc") or {}
    try:
        return max(float(ohlc.get("high", 0)) - float(ohlc.get("low", 0)), 0.0)
    except Exception:
        return 0.0


def _load_current_signal():
    if not os.path.exists(SIGNAL_STORE):
        return None
    try:
        with open(SIGNAL_STORE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _is_signal_fresh(signal: Optional[dict]) -> bool:
    if not signal:
        return False
    ts = signal.get("timestamp_utc")
    if not ts:
        return False
    try:
        signal_dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except Exception:
        return False
    return (datetime.now(timezone.utc) - signal_dt).total_seconds() <= ACTIVE_SIGNAL_TTL_SEC


def _parse_iso_utc(value: Optional[str]):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _check_signal_conflict(current_signal: Optional[dict], normalized_symbol: str, decision: str):
    now = datetime.now(timezone.utc)
    loss_side = SNAPSHOT_STATE.get("last_loss_side")
    last_loss_at = _parse_iso_utc(SNAPSHOT_STATE.get("last_loss_at"))
    consecutive_losses = SNAPSHOT_STATE.get("consecutive_losses", {}).get(decision, 0)
    if loss_side == decision and last_loss_at is not None:
        since_loss = (now - last_loss_at).total_seconds()
        if since_loss < LOSS_COOLDOWN_SEC:
            return "loss_cooldown_active"
    if consecutive_losses >= MAX_CONSECUTIVE_LOSSES_PER_SIDE:
        return "max_consecutive_losses_reached"
    if not _is_signal_fresh(current_signal):
        return None
    current_symbol = current_signal.get("symbol")
    current_side = current_signal.get("side")
    current_status = current_signal.get("status")
    if current_symbol != normalized_symbol:
        return None
    if current_side == decision:
        if current_status == "OPEN":
            return "position_open_same_direction"
        return "active_signal_same_direction"
    if current_status == "OPEN" and not REVERSAL_ON_OPEN_POSITION:
        return "opposite_signal_blocked_open_position"
    if current_status == "CLOSED":
        closed_at = _parse_iso_utc(current_signal.get("closed_at"))
        if closed_at is not None:
            since_close = (now - closed_at).total_seconds()
            if since_close < POST_CLOSE_COOLDOWN_SEC:
                return "post_close_cooldown_active"
    return None


def _build_signal(symbol: str, decision: str, entry: float, timeframe: str, confidence: float, reason: str, snapshot: Optional[dict] = None):
    candle_range = _snapshot_range(snapshot or {})
    if symbol == "XAUUSD":
        zone = _clamp(candle_range * XAU_ENTRY_ZONE_RANGE_MULT, XAU_ENTRY_ZONE_MIN, XAU_ENTRY_ZONE_MAX)
        sl_offset = max(5.0, zone * 4.0)
        tp1_offset = max(8.0, zone * 6.0)
        tp2_offset = max(12.0, zone * 9.0)
        digits = 2
        spread_max_points = 120
    else:
        zone = _clamp(candle_range * FOREX_ENTRY_ZONE_RANGE_MULT, FOREX_ENTRY_ZONE_MIN, FOREX_ENTRY_ZONE_MAX)
        sl_offset = max(0.0030, zone * 4.0)
        tp1_offset = max(0.0050, zone * 6.0)
        tp2_offset = max(0.0080, zone * 9.0)
        digits = 5
        spread_max_points = 35

    sl = entry - sl_offset if decision == "BUY" else entry + sl_offset
    tp1 = entry + tp1_offset if decision == "BUY" else entry - tp1_offset
    tp2 = entry + tp2_offset if decision == "BUY" else entry - tp2_offset

    return {
        "signal_id": f"local-ai-{symbol.lower()}-{int(datetime.now(timezone.utc).timestamp())}",
        "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "symbol": symbol,
        "timeframe": timeframe,
        "side": decision,
        "entry_zone": {"min": round(entry - zone, digits), "max": round(entry + zone, digits)},
        "stop_loss": round(sl, digits),
        "take_profit": [
            {"label": "TP1", "price": round(tp1, digits), "close_pct": 0.5},
            {"label": "TP2", "price": round(tp2, digits), "close_pct": 0.5},
        ],
        "confidence": confidence,
        "invalidation": f"AI loop: {reason}",
        "max_signal_age_sec": 180,
        "market_context": {
            "spread_max_points": spread_max_points,
            "session": "LOCAL_AI_QUEUE",
            "news_block_minutes": DEFAULT_NEWS_BLOCK_MINUTES,
            "entry_zone_size": round(zone, digits),
            "snapshot_range": round(candle_range, digits),
        },
        "received_at": datetime.now(timezone.utc).isoformat(),
        "status": "READY",
        "source": "local_gemini_queue",
    }


def _infer_price_levels(symbol: str, side: str, entry_price: float, content: str):
    symbol = (symbol or "").upper()
    text = (content or "").lower()

    if symbol == "XAUUSD":
        stop_offset = 5.0
        tp_offset = 8.0
        if "scalp" in text:
            stop_offset = 3.0
            tp_offset = 5.0
        elif "swing" in text:
            stop_offset = 8.0
            tp_offset = 12.0
        elif "take-profit" in text or "tp" in text:
            tp_offset = 10.0
    else:
        stop_offset = 0.0030
        tp_offset = 0.0050
        if "scalp" in text:
            stop_offset = 0.0015
            tp_offset = 0.0025
        elif "swing" in text:
            stop_offset = 0.0050
            tp_offset = 0.0080
        elif "take-profit" in text or "tp" in text:
            tp_offset = 0.0060

    stop_loss = entry_price - stop_offset if side == "BUY" else entry_price + stop_offset
    tp1 = entry_price + tp_offset if side == "BUY" else entry_price - tp_offset
    return round(stop_loss, 5 if symbol != "XAUUSD" else 2), round(tp1, 5 if symbol != "XAUUSD" else 2)


def convert_ai4trade_signal(signals: list):
    for item in signals:
        trace = {
            "at": datetime.now(timezone.utc).isoformat(),
            "dry_run": AI4TRADE_DRY_RUN,
            "signal_id": item.get("signal_id") or item.get("id") if isinstance(item, dict) else None,
            "agent_id": item.get("agent_id") if isinstance(item, dict) else None,
            "symbol": item.get("symbol") if isinstance(item, dict) else None,
            "market": item.get("market") if isinstance(item, dict) else None,
            "message_type": item.get("message_type") if isinstance(item, dict) else None,
            "decision": None,
            "reason": None,
        }
        if not isinstance(item, dict):
            trace["decision"] = "reject"
            trace["reason"] = "not_a_dict"
            _append_ai4trade_dry_run(trace)
            continue
        if AI4TRADE_REQUIRE_AGENT_MATCH and AI4TRADE_AGENT_ID and str(item.get("agent_id")) != str(AI4TRADE_AGENT_ID):
            trace["decision"] = "reject"
            trace["reason"] = "agent_id_mismatch"
            _append_ai4trade_dry_run(trace)
            continue
        if item.get("market") not in {"forex", "xau", "gold", "xauusd"}:
            trace["decision"] = "reject"
            trace["reason"] = "unsupported_market"
            _append_ai4trade_dry_run(trace)
            continue
        symbol = normalize_symbol(item.get("symbol") or "")
        if symbol not in AI4TRADE_ALLOWED_SYMBOLS:
            trace["decision"] = "reject"
            trace["reason"] = "unsupported_symbol"
            trace["allowed_symbols"] = sorted(list(AI4TRADE_ALLOWED_SYMBOLS))
            _append_ai4trade_dry_run(trace)
            continue
        side = (item.get("side") or item.get("action") or "").upper()
        if side not in {"BUY", "SELL"}:
            trace["decision"] = "reject"
            trace["reason"] = "missing_or_invalid_side"
            _append_ai4trade_dry_run(trace)
            continue
        entry_price = item.get("entry_price") or item.get("price")
        if entry_price is None:
            trace["decision"] = "reject"
            trace["reason"] = "missing_entry_price"
            _append_ai4trade_dry_run(trace)
            continue
        try:
            entry_price = float(entry_price)
        except Exception:
            trace["decision"] = "reject"
            trace["reason"] = "invalid_entry_price"
            _append_ai4trade_dry_run(trace)
            continue
        signal_id = str(item.get("signal_id") or item.get("id") or "")
        timestamp_utc = item.get("executed_at") or item.get("created_at") or datetime.now(timezone.utc).isoformat()
        content = item.get("content") or ""
        confidence = 0.7 if item.get("message_type") == "operation" else AI4TRADE_MIN_CONFIDENCE
        stop_loss, tp1 = _infer_price_levels(symbol, side, entry_price, content)
        zone_size = (0.3 if confidence < 0.8 else 0.2) if symbol == "XAUUSD" else (0.0005 if confidence < 0.8 else 0.0003)
        converted = {
            "signal_id": f"ai4trade-{signal_id}",
            "timestamp_utc": timestamp_utc.replace("Z", "+00:00").replace("+00:00", "Z"),
            "symbol": symbol,
            "timeframe": "M15",
            "side": side,
            "entry_zone": {
                "min": round(entry_price - zone_size, 2),
                "max": round(entry_price + zone_size, 2),
            },
            "stop_loss": stop_loss,
            "take_profit": [
                {
                    "label": "TP1",
                    "price": tp1,
                    "close_pct": 1.0,
                }
            ],
            "confidence": confidence,
            "invalidation": content[:200],
            "max_signal_age_sec": 180,
            "market_context": {
                "spread_max_points": 35,
                "session": "AI4TRADE_FEED",
                "news_block_minutes": DEFAULT_NEWS_BLOCK_MINUTES,
            },
            "received_at": datetime.now(timezone.utc).isoformat(),
            "status": "READY",
            "source": "ai4trade.ai",
            "source_message_type": item.get("message_type"),
            "source_signal_type": item.get("signal_type"),
        }
        trace["decision"] = "select"
        trace["reason"] = "matched_xau_signal"
        trace["converted"] = converted
        _append_ai4trade_dry_run(trace)
        return converted
    return None


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


async def refresh_ai4trade_signal_once():
    if not AI4TRADE_TOKEN:
        return
    headers = {"Authorization": f"Bearer {AI4TRADE_TOKEN}"}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{AI4TRADE_FEED_URL}?limit=20&sort=new", headers=headers, timeout=15)
            response.raise_for_status()
            payload = response.json()
            _save_ai4trade_raw(payload)
            signals = payload.get("signals", []) if isinstance(payload, dict) else []
            converted = convert_ai4trade_signal(signals)
            AI4TRADE_STATE["last_fetch_at"] = datetime.now(timezone.utc).isoformat()
            AI4TRADE_STATE["last_signal_count"] = len(signals)
            AI4TRADE_STATE["last_selected"] = converted.get("signal_id") if converted else None
            AI4TRADE_STATE["last_error"] = None
            if converted and not AI4TRADE_DRY_RUN:
                _store_signal_payload(converted)
    except Exception as e:
        AI4TRADE_STATE["last_error"] = str(e)
        print(f"Error fetching ai4trade signals: {e}")


async def update_ai4trade_loop():
    while True:
        await refresh_ai4trade_signal_once()
        _run_startup_checks()
        await asyncio.sleep(AI4TRADE_POLL_SEC)


async def snapshot_worker_loop():
    state = _load_state()
    while True:
        payload = await SNAPSHOT_QUEUE.get()
        try:
            for snap in payload.get("snapshots", []):
                result = decide_trade(snap)
                SNAPSHOT_STATE["last_processed_at"] = datetime.now(timezone.utc).isoformat()
                SNAPSHOT_STATE["last_decision"] = result.get("decision")
                SNAPSHOT_STATE["last_reason"] = result.get("reason")
                SNAPSHOT_STATE["last_decision_source"] = result.get("decision_source", "unknown")
                SNAPSHOT_STATE["last_snapshot_timeframe"] = snap.get("timeframe")
                if result.get("decision") not in {"BUY", "SELL"}:
                    SNAPSHOT_STATE["last_no_trade_at"] = datetime.now(timezone.utc).isoformat()
                    SNAPSHOT_STATE["last_no_trade_reason"] = result.get("reason")
                    SNAPSHOT_STATE["last_no_trade_symbol"] = snap.get("symbol")
                    _append_journal({
                        "event_id": str(uuid.uuid4()),
                        "type": "snapshot_rejected",
                        "at": datetime.now(timezone.utc).isoformat(),
                        "symbol": snap.get("symbol"),
                        "timeframe": snap.get("timeframe"),
                        "reason": result.get("reason"),
                        "decision_source": result.get("decision_source", "unknown"),
                    })
                    continue
                normalized_symbol = result.get("symbol", snap["symbol"])
                key = f"{normalized_symbol}:{result['decision']}:{result['entry']}"
                if state.get("last_keys", {}).get(normalized_symbol) == key:
                    continue
                current_signal = _load_current_signal()
                reject_reason = _check_signal_conflict(current_signal, normalized_symbol, result.get("decision"))
                if reject_reason:
                    SNAPSHOT_STATE["last_no_trade_at"] = datetime.now(timezone.utc).isoformat()
                    SNAPSHOT_STATE["last_no_trade_reason"] = reject_reason
                    SNAPSHOT_STATE["last_no_trade_symbol"] = normalized_symbol
                    _append_journal({
                        "event_id": str(uuid.uuid4()),
                        "type": "snapshot_rejected",
                        "at": datetime.now(timezone.utc).isoformat(),
                        "symbol": normalized_symbol,
                        "timeframe": snap.get("timeframe"),
                        "reason": reject_reason,
                        "decision_source": result.get("decision_source", "unknown"),
                    })
                    continue
                signal = _build_signal(normalized_symbol, result["decision"], result["entry"], result["timeframe"], result["confidence"], result["reason"], snap)
                _store_generated_signal(signal)
                _store_signal_payload(signal)
                state.setdefault("last_keys", {})[normalized_symbol] = key
                _save_state(state)
                SNAPSHOT_STATE["last_signal_id"] = signal["signal_id"]
                _append_journal({
                    "event_id": str(uuid.uuid4()),
                    "type": "signal_generated_from_snapshot",
                    "at": datetime.now(timezone.utc).isoformat(),
                    "signal_id": signal["signal_id"],
                    "symbol": signal["symbol"],
                    "side": signal["side"],
                    "confidence": signal["confidence"],
                    "reason": signal["invalidation"],
                    "decision_source": result.get("decision_source", "unknown"),
                })
                if AI_SIGNAL_PUBLISH_ENABLED:
                    await _publish_signal_to_ai4trade(signal)
        except Exception as e:
            SNAPSHOT_STATE["last_error"] = str(e)
            print(f"Snapshot worker error: {e}")
        finally:
            SNAPSHOT_STATE["queue_size"] = SNAPSHOT_QUEUE.qsize()
            SNAPSHOT_QUEUE.task_done()
            if AI_SIGNAL_PROCESSING_INTERVAL_SEC > 0:
                await asyncio.sleep(AI_SIGNAL_PROCESSING_INTERVAL_SEC)


async def _publish_signal_to_ai4trade(signal: dict):
    if not AI4TRADE_TOKEN:
        return
    symbol = str(signal.get("symbol", "")).upper()
    side = str(signal.get("side", signal.get("action", ""))).lower()
    entry_zone = signal.get("entry_zone") or {}
    price = (float(entry_zone.get("min", 0)) + float(entry_zone.get("max", 0))) / 2.0
    content_parts = []
    for key in ["timeframe", "stop_loss", "confidence", "invalidation"]:
        if signal.get(key) is not None:
            content_parts.append(f"{key}={signal.get(key)}")
    take_profit = signal.get("take_profit")
    if isinstance(take_profit, list):
        for idx, tp in enumerate(take_profit, start=1):
            if isinstance(tp, dict) and tp.get("price") is not None:
                content_parts.append(f"TP{idx}={tp.get('price')}")
    payload = {
        "market": "forex",
        "action": side,
        "symbol": symbol,
        "price": float(price),
        "quantity": 0.01,
        "content": " | ".join(content_parts),
        "executed_at": signal.get("timestamp_utc"),
        "token_id": signal.get("token_id"),
        "outcome": signal.get("outcome"),
    }
    headers = {
        "Authorization": f"Bearer {AI4TRADE_TOKEN}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(os.getenv("AI4TRADE_PUBLISH_URL", "https://ai4trade.ai/api/signals/realtime"), headers=headers, json=payload)
        print(response.status_code)
        print(response.text)
        if response.is_error and not AI_SIGNAL_IGNORE_PUBLISH_ERRORS:
            response.raise_for_status()


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


def _effective_risk_config():
    return {
        "active_signal_ttl_sec": ACTIVE_SIGNAL_TTL_SEC,
        "reversal_on_open_position": REVERSAL_ON_OPEN_POSITION,
        "post_close_cooldown_sec": POST_CLOSE_COOLDOWN_SEC,
        "loss_cooldown_sec": LOSS_COOLDOWN_SEC,
        "max_consecutive_losses_per_side": MAX_CONSECUTIVE_LOSSES_PER_SIDE,
        "xau_max_spread_points": int(os.getenv("XAU_MAX_SPREAD_POINTS", "120")),
        "forex_max_spread_points": int(os.getenv("FOREX_MAX_SPREAD_POINTS", "35")),
        "gemini_min_confidence": float(os.getenv("GEMINI_MIN_CONFIDENCE", "0.55")),
        "gemini_override_confidence": float(os.getenv("GEMINI_OVERRIDE_CONFIDENCE", "0.72")),
        "session_filter_enabled": os.getenv("SESSION_FILTER_ENABLED", "true").lower() in {"1", "true", "yes", "on"},
        "session_start_hour_utc": int(os.getenv("SESSION_START_HOUR_UTC", "6")),
        "session_end_hour_utc": int(os.getenv("SESSION_END_HOUR_UTC", "21")),
        "default_news_block_minutes": DEFAULT_NEWS_BLOCK_MINUTES,
    }


def _current_signal_summary():
    current_signal = _load_current_signal()
    signal_age_sec = None
    if current_signal:
        ts = _parse_iso_utc(current_signal.get("timestamp_utc"))
        if ts is not None:
            signal_age_sec = round((datetime.now(timezone.utc) - ts).total_seconds(), 2)
    return {
        "present": current_signal is not None,
        "signal_id": current_signal.get("signal_id") if current_signal else None,
        "symbol": current_signal.get("symbol") if current_signal else None,
        "side": current_signal.get("side") if current_signal else None,
        "status": current_signal.get("status") if current_signal else None,
        "confidence": current_signal.get("confidence") if current_signal else None,
        "age_sec": signal_age_sec,
        "fresh": _is_signal_fresh(current_signal),
    }


def _risk_state_summary():
    return {
        "last_trade_outcome": SNAPSHOT_STATE.get("last_trade_outcome"),
        "last_loss_side": SNAPSHOT_STATE.get("last_loss_side"),
        "last_loss_at": SNAPSHOT_STATE.get("last_loss_at"),
        "consecutive_losses": SNAPSHOT_STATE.get("consecutive_losses"),
        "last_no_trade_reason": SNAPSHOT_STATE.get("last_no_trade_reason"),
        "last_execution_type": SNAPSHOT_STATE.get("last_execution_type"),
        "last_execution_signal_id": SNAPSHOT_STATE.get("last_execution_signal_id"),
        "last_execution_ticket": SNAPSHOT_STATE.get("last_execution_ticket"),
    }


def _read_journal_events(limit: int = 50, event_type: Optional[str] = None):
    if not os.path.exists(JOURNAL_STORE):
        return []
    try:
        with open(JOURNAL_STORE, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return []
    events = []
    wanted_type = (event_type or "").strip()
    for line in reversed(lines):
        try:
            item = json.loads(line)
        except Exception:
            continue
        current_type = str(item.get("type") or item.get("event_type") or "")
        if wanted_type and current_type != wanted_type:
            continue
        events.append(item)
        if len(events) >= limit:
            break
    return events


def _run_startup_checks():
    checks = []
    env_exists = os.path.exists(os.path.join(BASE_DIR, ".env"))
    checks.append({"name": "env_file_present", "ok": env_exists, "detail": os.path.join(BASE_DIR, ".env")})
    strong_token = bool(APP_TOKEN and APP_TOKEN != "change-me-token" and len(APP_TOKEN) >= 16)
    checks.append({"name": "bridge_token_safe", "ok": strong_token, "detail": "BRIDGE_API_TOKEN must be set and not default"})
    news_ready = bool(NEWS_CACHE.get("updated_at") or os.path.exists(NEWS_CACHE_FILE))
    checks.append({"name": "news_source_or_cache_ready", "ok": news_ready, "detail": NEWS_CACHE.get("updated_at") or NEWS_CACHE_FILE})
    signal_dir = os.path.dirname(SIGNAL_STORE) or BASE_DIR
    journal_dir = os.path.dirname(JOURNAL_STORE) or BASE_DIR
    snapshot_dir = os.path.dirname(SNAPSHOT_STORE) or BASE_DIR
    checks.append({"name": "signal_store_writable", "ok": os.path.isdir(signal_dir) and os.access(signal_dir, os.W_OK), "detail": signal_dir})
    checks.append({"name": "journal_store_writable", "ok": os.path.isdir(journal_dir) and os.access(journal_dir, os.W_OK), "detail": journal_dir})
    checks.append({"name": "snapshot_store_writable", "ok": os.path.isdir(snapshot_dir) and os.access(snapshot_dir, os.W_OK), "detail": snapshot_dir})

    risk_cfg = _effective_risk_config()
    checks.append({"name": "active_signal_ttl_valid", "ok": risk_cfg["active_signal_ttl_sec"] > 0, "detail": risk_cfg["active_signal_ttl_sec"]})
    checks.append({"name": "post_close_cooldown_valid", "ok": risk_cfg["post_close_cooldown_sec"] >= 0, "detail": risk_cfg["post_close_cooldown_sec"]})
    checks.append({"name": "loss_cooldown_valid", "ok": risk_cfg["loss_cooldown_sec"] >= 0, "detail": risk_cfg["loss_cooldown_sec"]})
    checks.append({"name": "max_consecutive_losses_valid", "ok": risk_cfg["max_consecutive_losses_per_side"] >= 1, "detail": risk_cfg["max_consecutive_losses_per_side"]})
    checks.append({"name": "xau_spread_valid", "ok": risk_cfg["xau_max_spread_points"] > 0, "detail": risk_cfg["xau_max_spread_points"]})
    checks.append({"name": "forex_spread_valid", "ok": risk_cfg["forex_max_spread_points"] > 0, "detail": risk_cfg["forex_max_spread_points"]})
    checks.append({"name": "gemini_min_confidence_valid", "ok": 0 <= risk_cfg["gemini_min_confidence"] <= 1, "detail": risk_cfg["gemini_min_confidence"]})
    checks.append({"name": "gemini_override_confidence_valid", "ok": 0 <= risk_cfg["gemini_override_confidence"] <= 1, "detail": risk_cfg["gemini_override_confidence"]})
    checks.append({"name": "session_window_valid", "ok": 0 <= risk_cfg["session_start_hour_utc"] <= 23 and 0 <= risk_cfg["session_end_hour_utc"] <= 23 and risk_cfg["session_start_hour_utc"] != risk_cfg["session_end_hour_utc"], "detail": f"{risk_cfg['session_start_hour_utc']}->{risk_cfg['session_end_hour_utc']}"})
    checks.append({"name": "news_block_minutes_valid", "ok": risk_cfg["default_news_block_minutes"] >= 0, "detail": risk_cfg["default_news_block_minutes"]})

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
        "snapshot_queue": {
            "queue_size": SNAPSHOT_QUEUE.qsize(),
            "last_received_at": SNAPSHOT_STATE.get("last_received_at"),
            "last_processed_at": SNAPSHOT_STATE.get("last_processed_at"),
            "last_signal_id": SNAPSHOT_STATE.get("last_signal_id"),
            "last_decision": SNAPSHOT_STATE.get("last_decision"),
            "last_reason": SNAPSHOT_STATE.get("last_reason"),
            "last_decision_source": SNAPSHOT_STATE.get("last_decision_source"),
            "last_error": SNAPSHOT_STATE.get("last_error"),
        },
    }


@app.get("/health/ready")
def health_ready(authorization: Optional[str] = Header(default=None)):
    _check_token(authorization)
    return {"ok": True, "startup": STARTUP_STATUS, "snapshot_state": SNAPSHOT_STATE}


@app.get("/strategy/status")
def strategy_status(authorization: Optional[str] = Header(default=None)):
    _check_token(authorization)
    signal_payload = None
    signal_age_sec = None
    if os.path.exists(SIGNAL_STORE):
        try:
            with open(SIGNAL_STORE, "r", encoding="utf-8") as f:
                signal_payload = json.load(f)
            ts = signal_payload.get("timestamp_utc")
            if ts:
                signal_dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                signal_age_sec = round((datetime.now(timezone.utc) - signal_dt).total_seconds(), 2)
        except Exception:
            signal_payload = None
    return {
        "ok": True,
        "snapshot_state": SNAPSHOT_STATE,
        "signal_present": signal_payload is not None,
        "signal_age_sec": signal_age_sec,
        "signal": signal_payload,
        "risk_config": _effective_risk_config(),
    }


@app.get("/risk/status")
def risk_status(authorization: Optional[str] = Header(default=None)):
    _check_token(authorization)
    return {
        "ok": True,
        "risk_config": _effective_risk_config(),
        "risk_state": _risk_state_summary(),
        "current_signal": _current_signal_summary(),
    }


@app.get("/ops/summary")
def ops_summary(authorization: Optional[str] = Header(default=None)):
    _check_token(authorization)
    active_news = get_active_news_event(DEFAULT_NEWS_BLOCK_MINUTES)
    return {
        "ok": True,
        "service": "xauusd-mt4-bridge",
        "ready": STARTUP_STATUS.get("ready", False),
        "checked_at": STARTUP_STATUS.get("checked_at"),
        "queue": {
            "size": SNAPSHOT_QUEUE.qsize(),
            "last_received_at": SNAPSHOT_STATE.get("last_received_at"),
            "last_processed_at": SNAPSHOT_STATE.get("last_processed_at"),
        },
        "strategy": {
            "last_signal_id": SNAPSHOT_STATE.get("last_signal_id"),
            "last_decision": SNAPSHOT_STATE.get("last_decision"),
            "last_reason": SNAPSHOT_STATE.get("last_reason"),
            "last_decision_source": SNAPSHOT_STATE.get("last_decision_source"),
            "last_snapshot_timeframe": SNAPSHOT_STATE.get("last_snapshot_timeframe"),
        },
        "risk": _risk_state_summary(),
        "current_signal": _current_signal_summary(),
        "news": {
            "blocked": active_news is not None,
            "active": active_news,
            "updated_at": NEWS_CACHE.get("updated_at"),
        },
        "ai4trade": {
            "enabled": bool(AI4TRADE_TOKEN),
            "last_fetch_at": AI4TRADE_STATE.get("last_fetch_at"),
            "last_signal_count": AI4TRADE_STATE.get("last_signal_count"),
            "last_selected": AI4TRADE_STATE.get("last_selected"),
            "last_error": AI4TRADE_STATE.get("last_error"),
        },
        "risk_config": _effective_risk_config(),
    }


@app.post("/market/snapshot")
async def receive_snapshot(batch: SnapshotBatch, authorization: Optional[str] = Header(default=None)):
    _check_token(authorization)
    try:
        datetime.fromisoformat(batch.timestamp_utc.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(status_code=400, detail="invalid timestamp_utc")

    filtered = []
    for snap in batch.snapshots:
        raw_symbol = snap.symbol.upper()
        symbol = normalize_symbol(raw_symbol)
        if symbol not in AI4TRADE_ALLOWED_SYMBOLS:
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
    _save_snapshot_batch(payload)
    SNAPSHOT_STATE["last_received_at"] = payload["received_at"]
    await SNAPSHOT_QUEUE.put(payload)
    SNAPSHOT_STATE["queue_size"] = SNAPSHOT_QUEUE.qsize()
    return {"ok": True, "stored": len(filtered), "queued": len(filtered), "symbols": [x["symbol"] for x in filtered]}


@app.get("/market/snapshot/latest")
def latest_snapshot(authorization: Optional[str] = Header(default=None)):
    _check_token(authorization)
    if not os.path.exists(SNAPSHOT_STORE):
        return {"ok": True, "snapshot": None}
    with open(SNAPSHOT_STORE, "r", encoding="utf-8") as f:
        return {"ok": True, "snapshot": json.load(f), "state": SNAPSHOT_STATE}


@app.get("/ai4trade/status")
def ai4trade_status(authorization: Optional[str] = Header(default=None)):
    _check_token(authorization)
    return {
        "ok": True,
        "enabled": bool(AI4TRADE_TOKEN),
        "agent_id": AI4TRADE_AGENT_ID,
        "require_agent_match": AI4TRADE_REQUIRE_AGENT_MATCH,
        "allowed_symbols": sorted(list(AI4TRADE_ALLOWED_SYMBOLS)),
        "feed_url": AI4TRADE_FEED_URL,
        "poll_sec": AI4TRADE_POLL_SEC,
        "state": AI4TRADE_STATE,
        "raw_store": AI4TRADE_RAW_STORE,
    }


@app.get("/ai4trade/raw")
def ai4trade_raw(authorization: Optional[str] = Header(default=None)):
    _check_token(authorization)
    if not os.path.exists(AI4TRADE_RAW_STORE):
        return {"ok": True, "payload": None}
    with open(AI4TRADE_RAW_STORE, "r", encoding="utf-8") as f:
        return {"ok": True, "payload": json.load(f)}


@app.get("/ai4trade/dry-run")
def ai4trade_dry_run(authorization: Optional[str] = Header(default=None)):
    _check_token(authorization)
    if not os.path.exists(AI4TRADE_DRY_RUN_LOG):
        return {"ok": True, "enabled": AI4TRADE_DRY_RUN, "events": []}
    with open(AI4TRADE_DRY_RUN_LOG, "r", encoding="utf-8") as f:
        lines = f.readlines()[-100:]
    events = []
    for line in lines:
        try:
            events.append(json.loads(line))
        except Exception:
            continue
    return {"ok": True, "enabled": AI4TRADE_DRY_RUN, "events": events}


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


@app.get("/audit/journal")
def audit_journal(limit: int = 50, event_type: Optional[str] = None, authorization: Optional[str] = Header(default=None)):
    _check_token(authorization)
    safe_limit = max(1, min(limit, 200))
    events = _read_journal_events(limit=safe_limit, event_type=event_type)
    return {
        "ok": True,
        "count": len(events),
        "limit": safe_limit,
        "event_type": event_type,
        "events": events,
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
    _store_signal_payload(payload)
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
        return {"ok": True, "signal": None, "news_blocked": news_blocked, "active_news": active_news, "news_updated_at": NEWS_CACHE.get("updated_at")}
    with open(SIGNAL_STORE, "r", encoding="utf-8") as f:
        data = json.load(f)
    block_minutes = data.get("market_context", {}).get("news_block_minutes", DEFAULT_NEWS_BLOCK_MINUTES)
    active_news = get_active_news_event(block_minutes)
    news_blocked = active_news is not None
    if news_blocked:
        data["status"] = "BLOCKED_BY_NEWS"
    return {"ok": True, "signal": data, "news_blocked": news_blocked, "active_news": active_news, "news_updated_at": NEWS_CACHE.get("updated_at")}


@app.post("/execution/report")
def execution_report(payload: dict, authorization: Optional[str] = Header(default=None)):
    _check_token(authorization)
    report_kind = str(payload.get("type", "")).upper()
    event = dict(payload)
    event["event_type"] = "execution_report"
    event["at"] = datetime.now(timezone.utc).isoformat()
    _append_journal(event)

    SNAPSHOT_STATE["last_execution_at"] = event["at"]
    SNAPSHOT_STATE["last_execution_signal_id"] = payload.get("signal_id")
    SNAPSHOT_STATE["last_execution_type"] = report_kind
    SNAPSHOT_STATE["last_execution_ticket"] = payload.get("ticket")

    current_signal = _load_current_signal()
    if current_signal and current_signal.get("signal_id") == payload.get("signal_id"):
        if report_kind == "OPEN":
            current_signal["status"] = "OPEN"
            current_signal["executed_ticket"] = payload.get("ticket")
            current_signal["executed_at"] = event["at"]
            _store_signal_payload(current_signal)
        elif report_kind in {"CLOSE", "CLOSED", "EXIT"}:
            current_signal["status"] = "CLOSED"
            current_signal["closed_at"] = event["at"]
            outcome = str(payload.get("outcome", payload.get("result", ""))).upper()
            pnl = payload.get("pnl")
            if outcome:
                current_signal["outcome"] = outcome
            if pnl is not None:
                current_signal["pnl"] = pnl
            side = current_signal.get("side")
            if outcome in {"LOSS", "SL", "STOP_LOSS", "NEGATIVE"}:
                SNAPSHOT_STATE["last_trade_outcome"] = outcome
                SNAPSHOT_STATE["last_loss_side"] = side
                SNAPSHOT_STATE["last_loss_at"] = event["at"]
                losses = SNAPSHOT_STATE.setdefault("consecutive_losses", {"BUY": 0, "SELL": 0})
                losses[side] = int(losses.get(side, 0)) + 1
            elif outcome in {"WIN", "TP", "TAKE_PROFIT", "POSITIVE", "BREAKEVEN", "BE"}:
                SNAPSHOT_STATE["last_trade_outcome"] = outcome
                losses = SNAPSHOT_STATE.setdefault("consecutive_losses", {"BUY": 0, "SELL": 0})
                if side in losses:
                    losses[side] = 0
                if outcome in {"WIN", "TP", "TAKE_PROFIT", "POSITIVE"}:
                    SNAPSHOT_STATE["last_loss_side"] = None
                    SNAPSHOT_STATE["last_loss_at"] = None
            _store_signal_payload(current_signal)
    return {"ok": True}
