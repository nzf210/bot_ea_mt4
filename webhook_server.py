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

from gemini_decider import decide_trade, normalize_symbol, get_gemini_runtime_state, set_gemini_runtime_state
from app_core.storage import append_jsonl, read_json_file, write_json_file, ensure_parent_dir
from app_core.runtime_state import save_runtime_state, load_runtime_state
from app_core.signal_state import (
    apply_execution_reject,
    apply_execution_report,
    build_bridge_contract,
    current_signal_summary,
    is_signal_fresh,
    parse_iso_utc,
    signal_staleness,
)
from app_core.contracts.terminal import (
    BridgeSignal as NeutralBridgeSignal,
    EntryZone as NeutralEntryZone,
    MarketContext as NeutralMarketContext,
    MarketSnapshot as NeutralMarketSnapshot,
    OHLC as NeutralOHLC,
    SnapshotBatch as NeutralSnapshotBatch,
    SnapshotCandle as NeutralSnapshotCandle,
    TakeProfit as NeutralTakeProfit,
)
from app_core.contracts.compat import (
    upgrade_execution_reject_payload,
    upgrade_execution_report_payload,
    upgrade_signal_payload,
    upgrade_snapshot_batch_payload,
)

BASE_DIR = os.path.dirname(__file__)
load_dotenv(os.path.join(BASE_DIR, ".env"))

STARTUP_STATUS = {
    "ready": False,
    "checks": [],
    "checked_at": None,
    "runtime_state_restored": False,
    "runtime_state_source": None,
    "runtime_state_saved_at": None,
    "runtime_state_error": None,
}

APP_TOKEN = os.getenv("BRIDGE_API_TOKEN", "change-me-token")
SIGNAL_STORE = os.getenv("SIGNAL_STORE", os.path.join(BASE_DIR, "latest_signal.json"))
JOURNAL_STORE = os.getenv("JOURNAL_STORE", os.path.join(BASE_DIR, "journal.log"))
NEWS_CACHE_FILE = os.getenv("NEWS_CACHE_FILE", os.path.join(BASE_DIR, "news_cache.json"))
SNAPSHOT_STORE = os.getenv("MARKET_SNAPSHOT_STORE", os.path.join(BASE_DIR, "latest_market_snapshot.json"))
GENERATED_SIGNAL_STORE = os.getenv("AI_GENERATED_SIGNAL_STORE", os.path.join(BASE_DIR, "generated_ai_signal.json"))
AI_SIGNAL_STATE_FILE = os.getenv("AI_SIGNAL_STATE_FILE", os.path.join(BASE_DIR, "ai_signal_state.json"))
RUNTIME_STATE_FILE = os.getenv("RUNTIME_STATE_FILE", os.path.join(BASE_DIR, "runtime_state.json"))
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
TELEGRAM_NOTIFY_ENABLED = os.getenv("TELEGRAM_NOTIFY_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
REVERSAL_ON_OPEN_POSITION = os.getenv("REVERSAL_ON_OPEN_POSITION", "false").lower() in {"1", "true", "yes", "on"}
POST_CLOSE_COOLDOWN_SEC = int(os.getenv("POST_CLOSE_COOLDOWN_SEC", "30"))
LOSS_COOLDOWN_SEC = int(os.getenv("LOSS_COOLDOWN_SEC", "180"))
MAX_CONSECUTIVE_LOSSES_PER_SIDE = int(os.getenv("MAX_CONSECUTIVE_LOSSES_PER_SIDE", "2"))
XAU_ENTRY_ZONE_MIN = float(os.getenv("XAU_ENTRY_ZONE_MIN", "0.35"))
XAU_ENTRY_ZONE_MAX = float(os.getenv("XAU_ENTRY_ZONE_MAX", "0.9"))
XAU_ENTRY_ZONE_RANGE_MULT = float(os.getenv("XAU_ENTRY_ZONE_RANGE_MULT", "0.22"))
XAU_SL_MIN = float(os.getenv("XAU_SL_MIN", "4.8"))
XAU_SL_MAX = float(os.getenv("XAU_SL_MAX", "10.5"))
XAU_SL_RANGE_MULT = float(os.getenv("XAU_SL_RANGE_MULT", "3.1"))
XAU_TP1_MIN = float(os.getenv("XAU_TP1_MIN", "6.0"))
XAU_TP1_RANGE_MULT = float(os.getenv("XAU_TP1_RANGE_MULT", "3.8"))
XAU_TP2_MIN = float(os.getenv("XAU_TP2_MIN", "10.0"))
XAU_TP2_RANGE_MULT = float(os.getenv("XAU_TP2_RANGE_MULT", "5.8"))
FOREX_ENTRY_ZONE_MIN = float(os.getenv("FOREX_ENTRY_ZONE_MIN", "0.0005"))
FOREX_ENTRY_ZONE_MAX = float(os.getenv("FOREX_ENTRY_ZONE_MAX", "0.0015"))
FOREX_ENTRY_ZONE_RANGE_MULT = float(os.getenv("FOREX_ENTRY_ZONE_RANGE_MULT", "0.25"))
FOREX_SL_MIN = float(os.getenv("FOREX_SL_MIN", "0.0025"))
FOREX_SL_MAX = float(os.getenv("FOREX_SL_MAX", "0.0065"))
FOREX_SL_RANGE_MULT = float(os.getenv("FOREX_SL_RANGE_MULT", "2.8"))
FOREX_TP1_MIN = float(os.getenv("FOREX_TP1_MIN", "0.0045"))
FOREX_TP1_RANGE_MULT = float(os.getenv("FOREX_TP1_RANGE_MULT", "3.8"))
FOREX_TP2_MIN = float(os.getenv("FOREX_TP2_MIN", "0.0075"))
FOREX_TP2_RANGE_MULT = float(os.getenv("FOREX_TP2_RANGE_MULT", "5.8"))
NEWS_URL = os.getenv("NEWS_CALENDAR_URL", "https://nfs.faireconomy.media/ff_calendar_thisweek.json")
NEWS_REFRESH_SEC = int(os.getenv("NEWS_REFRESH_SEC", "3600"))
DEFAULT_NEWS_BLOCK_MINUTES = int(os.getenv("DEFAULT_NEWS_BLOCK_MINUTES", "30"))
TRAILING_ENABLED = os.getenv("TRAILING_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
BREAK_EVEN_R_MULT = float(os.getenv("BREAK_EVEN_R_MULT", "0.85"))
BREAK_EVEN_BUFFER_R_MULT = float(os.getenv("BREAK_EVEN_BUFFER_R_MULT", "0.12"))
TRAILING_START_R_MULT = float(os.getenv("TRAILING_START_R_MULT", "1.2"))
TRAILING_STEP_R_MULT = float(os.getenv("TRAILING_STEP_R_MULT", "0.4"))
TRAILING_SL_R_MULT = float(os.getenv("TRAILING_SL_R_MULT", "0.85"))
TIME_BASED_TRAILING_ENABLED = os.getenv("TIME_BASED_TRAILING_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
TIME_BASED_TRAILING_AFTER_SEC = int(os.getenv("TIME_BASED_TRAILING_AFTER_SEC", "600"))
TIME_BASED_TRAILING_MIN_R_MULT = float(os.getenv("TIME_BASED_TRAILING_MIN_R_MULT", "0.25"))
TIME_BASED_TRAILING_SL_R_MULT = float(os.getenv("TIME_BASED_TRAILING_SL_R_MULT", "0.18"))
SLIPPAGE_COOLDOWN_ENABLED = os.getenv("SLIPPAGE_COOLDOWN_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
SLIPPAGE_COOLDOWN_WINDOW_SEC = int(os.getenv("SLIPPAGE_COOLDOWN_WINDOW_SEC", "10800"))
SLIPPAGE_COOLDOWN_THRESHOLD = int(os.getenv("SLIPPAGE_COOLDOWN_THRESHOLD", "2"))
SLIPPAGE_COOLDOWN_SEC = int(os.getenv("SLIPPAGE_COOLDOWN_SEC", "3600"))
SESSION_BUCKET_COOLDOWN_ENABLED = os.getenv("SESSION_BUCKET_COOLDOWN_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
SESSION_BUCKET_COOLDOWN_THRESHOLD = int(os.getenv("SESSION_BUCKET_COOLDOWN_THRESHOLD", "2"))
SESSION_BUCKET_COOLDOWN_SEC = int(os.getenv("SESSION_BUCKET_COOLDOWN_SEC", "5400"))
LOCAL_ONLY_MODE = os.getenv("LOCAL_ONLY_MODE", "true").lower() in {"1", "true", "yes", "on"}
ADAPTIVE_TRAILING_ENABLED = os.getenv("ADAPTIVE_TRAILING_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
ASIA_TRAILING_START_R_MULT = float(os.getenv("ASIA_TRAILING_START_R_MULT", "1.5"))
ASIA_TRAILING_STEP_R_MULT = float(os.getenv("ASIA_TRAILING_STEP_R_MULT", "0.5"))
LONDON_TRAILING_START_R_MULT = float(os.getenv("LONDON_TRAILING_START_R_MULT", "1.15"))
LONDON_TRAILING_STEP_R_MULT = float(os.getenv("LONDON_TRAILING_STEP_R_MULT", "0.35"))
NY_TRAILING_START_R_MULT = float(os.getenv("NY_TRAILING_START_R_MULT", "1.05"))
NY_TRAILING_STEP_R_MULT = float(os.getenv("NY_TRAILING_STEP_R_MULT", "0.3"))
ASIA_TIME_BASED_TRAILING_AFTER_SEC = int(os.getenv("ASIA_TIME_BASED_TRAILING_AFTER_SEC", "720"))
LONDON_TIME_BASED_TRAILING_AFTER_SEC = int(os.getenv("LONDON_TIME_BASED_TRAILING_AFTER_SEC", "600"))
NY_TIME_BASED_TRAILING_AFTER_SEC = int(os.getenv("NY_TIME_BASED_TRAILING_AFTER_SEC", "480"))
TRENDING_TIME_BASED_TRAILING_AFTER_SEC = int(os.getenv("TRENDING_TIME_BASED_TRAILING_AFTER_SEC", "720"))
BALANCED_TIME_BASED_TRAILING_AFTER_SEC = int(os.getenv("BALANCED_TIME_BASED_TRAILING_AFTER_SEC", "600"))
CHOPPY_TIME_BASED_TRAILING_AFTER_SEC = int(os.getenv("CHOPPY_TIME_BASED_TRAILING_AFTER_SEC", "420"))
TOXIC_TIME_BASED_TRAILING_AFTER_SEC = int(os.getenv("TOXIC_TIME_BASED_TRAILING_AFTER_SEC", "360"))
QUIET_TIME_BASED_TRAILING_AFTER_SEC = int(os.getenv("QUIET_TIME_BASED_TRAILING_AFTER_SEC", "540"))
TRENDING_TIME_BASED_TRAILING_MIN_R_MULT = float(os.getenv("TRENDING_TIME_BASED_TRAILING_MIN_R_MULT", "0.35"))
BALANCED_TIME_BASED_TRAILING_MIN_R_MULT = float(os.getenv("BALANCED_TIME_BASED_TRAILING_MIN_R_MULT", "0.25"))
CHOPPY_TIME_BASED_TRAILING_MIN_R_MULT = float(os.getenv("CHOPPY_TIME_BASED_TRAILING_MIN_R_MULT", "0.18"))
TOXIC_TIME_BASED_TRAILING_MIN_R_MULT = float(os.getenv("TOXIC_TIME_BASED_TRAILING_MIN_R_MULT", "0.12"))
QUIET_TIME_BASED_TRAILING_MIN_R_MULT = float(os.getenv("QUIET_TIME_BASED_TRAILING_MIN_R_MULT", "0.20"))
TRENDING_TIME_BASED_TRAILING_SL_R_MULT = float(os.getenv("TRENDING_TIME_BASED_TRAILING_SL_R_MULT", "0.28"))
BALANCED_TIME_BASED_TRAILING_SL_R_MULT = float(os.getenv("BALANCED_TIME_BASED_TRAILING_SL_R_MULT", "0.18"))
CHOPPY_TIME_BASED_TRAILING_SL_R_MULT = float(os.getenv("CHOPPY_TIME_BASED_TRAILING_SL_R_MULT", "0.10"))
TOXIC_TIME_BASED_TRAILING_SL_R_MULT = float(os.getenv("TOXIC_TIME_BASED_TRAILING_SL_R_MULT", "0.06"))
QUIET_TIME_BASED_TRAILING_SL_R_MULT = float(os.getenv("QUIET_TIME_BASED_TRAILING_SL_R_MULT", "0.14"))
ADAPTIVE_ENTRY_ZONE_ENABLED = os.getenv("ADAPTIVE_ENTRY_ZONE_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
ASIA_ENTRY_ZONE_MULT = float(os.getenv("ASIA_ENTRY_ZONE_MULT", "0.85"))
LONDON_ENTRY_ZONE_MULT = float(os.getenv("LONDON_ENTRY_ZONE_MULT", "1.0"))
NY_ENTRY_ZONE_MULT = float(os.getenv("NY_ENTRY_ZONE_MULT", "1.1"))
ADAPTIVE_GEOMETRY_ENABLED = os.getenv("ADAPTIVE_GEOMETRY_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
ASIA_SL_MULT = float(os.getenv("ASIA_SL_MULT", "0.95"))
ASIA_TP_MULT = float(os.getenv("ASIA_TP_MULT", "0.92"))
LONDON_SL_MULT = float(os.getenv("LONDON_SL_MULT", "1.0"))
LONDON_TP_MULT = float(os.getenv("LONDON_TP_MULT", "1.0"))
NY_SL_MULT = float(os.getenv("NY_SL_MULT", "1.08"))
NY_TP_MULT = float(os.getenv("NY_TP_MULT", "1.12"))
TREND_GEOMETRY_ADAPTIVE_ENABLED = os.getenv("TREND_GEOMETRY_ADAPTIVE_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
WEAK_TREND_SL_MULT = float(os.getenv("WEAK_TREND_SL_MULT", "1.08"))
WEAK_TREND_TP_MULT = float(os.getenv("WEAK_TREND_TP_MULT", "0.95"))
STRONG_TREND_SL_MULT = float(os.getenv("STRONG_TREND_SL_MULT", "0.96"))
STRONG_TREND_TP_MULT = float(os.getenv("STRONG_TREND_TP_MULT", "1.05"))
MARKET_MODE_TRENDING_SL_MULT = float(os.getenv("MARKET_MODE_TRENDING_SL_MULT", "1.1"))
MARKET_MODE_TRENDING_TP_MULT = float(os.getenv("MARKET_MODE_TRENDING_TP_MULT", "1.08"))
MARKET_MODE_BALANCED_SL_MULT = float(os.getenv("MARKET_MODE_BALANCED_SL_MULT", "1.0"))
MARKET_MODE_BALANCED_TP_MULT = float(os.getenv("MARKET_MODE_BALANCED_TP_MULT", "1.0"))
MARKET_MODE_CHOPPY_SL_MULT = float(os.getenv("MARKET_MODE_CHOPPY_SL_MULT", "0.98"))
MARKET_MODE_CHOPPY_TP_MULT = float(os.getenv("MARKET_MODE_CHOPPY_TP_MULT", "0.95"))
MARKET_MODE_TOXIC_SL_MULT = float(os.getenv("MARKET_MODE_TOXIC_SL_MULT", "0.95"))
MARKET_MODE_TOXIC_TP_MULT = float(os.getenv("MARKET_MODE_TOXIC_TP_MULT", "0.92"))
TRENDING_SELL_EXTRA_SL_MULT = float(os.getenv("TRENDING_SELL_EXTRA_SL_MULT", "1.05"))
TRENDING_SELL_EXTRA_TP_MULT = float(os.getenv("TRENDING_SELL_EXTRA_TP_MULT", "1.03"))

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
    "last_deterministic_score": None,
    "last_fusion_score": None,
    "last_adaptive_trade_threshold": None,
    "last_adaptive_no_trade_threshold": None,
    "last_gemini_evaluation": None,
    "last_outcome_penalty": None,
    "last_outcome_penalty_reason": None,
    "last_same_side_losses": None,
    "last_journal_reason_penalty": None,
    "last_journal_reason_penalty_reason": None,
    "last_journal_reason_loss_rate": None,
    "last_journal_reason_trade_count": None,
    "last_session_bucket": None,
    "last_session_penalty": None,
    "last_session_penalty_reason": None,
    "last_session_loss_rate": None,
    "last_session_trade_count": None,
    "last_exit_reason_penalty": None,
    "last_exit_reason_penalty_reason": None,
    "last_exit_reason_loss_rate": None,
    "last_exit_reason_trade_count": None,
    "last_auto_hardening_threshold_bonus": None,
    "last_auto_hardening_reason": None,
    "last_auto_hardening_triggered": None,
    "reason_outcome_scores": {},
    "last_pattern_lockout_penalty": None,
    "last_pattern_lockout_reason": None,
    "last_pattern_lockout_count": None,
    "last_pattern_lockout_key": None,
    "recent_loss_patterns": [],
    "last_trend_regime_reason": None,
    "last_trend_regime_score": None,
    "last_trend_regime_alignment": None,
    "last_trend_regime_opposing_count": None,
    "last_trend_regime_strong_aligned": None,
    "last_trend_regime_close_position": None,
    "last_sl_distance": None,
    "last_tp1_distance": None,
    "last_tp2_distance": None,
    "last_rr_tp1": None,
    "last_rr_tp2": None,
    "last_no_trade_at": None,
    "last_no_trade_reason": None,
    "last_no_trade_symbol": None,
    "last_snapshot_timeframe": None,
    "last_execution_at": None,
    "last_execution_signal_id": None,
    "last_execution_type": None,
    "last_execution_ticket": None,
    "last_exit_reason": None,
    "last_trailing_initial_risk_price": None,
    "last_trailing_initial_stop_loss": None,
    "last_trailing_initial_tp1": None,
    "last_trailing_last_applied_stop_loss": None,
    "last_break_even_activated": None,
    "last_trailing_activated": None,
    "last_market_toxicity_score": None,
    "last_market_toxicity_penalty": None,
    "last_market_toxicity_reason": None,
    "last_market_mode": None,
    "last_market_mode_reason": None,
    "last_market_mode_threshold_bonus": None,
    "last_market_mode_confidence_penalty": None,
    "last_trade_outcome": None,
    "last_loss_side": None,
    "last_loss_at": None,
    "slippage_cooldown_until": None,
    "recent_slippage_events": [],
    "session_cooldowns": {},
    "consecutive_losses": {"BUY": 0, "SELL": 0},
    "queue_size": 0,
    "last_error": None,
}
SNAPSHOT_QUEUE: asyncio.Queue = asyncio.Queue()


EntryZone = NeutralEntryZone
TakeProfit = NeutralTakeProfit
MarketContext = NeutralMarketContext
Signal = NeutralBridgeSignal
OHLC = NeutralOHLC
SnapshotCandle = NeutralSnapshotCandle
Snapshot = NeutralMarketSnapshot
SnapshotBatch = NeutralSnapshotBatch


@asynccontextmanager
async def lifespan(app: FastAPI):
    _load_runtime_state()
    _append_journal({
        "event_id": str(uuid.uuid4()),
        "type": "runtime_state_restore",
        "at": datetime.now(timezone.utc).isoformat(),
        "restored": STARTUP_STATUS.get("runtime_state_restored"),
        "source": STARTUP_STATUS.get("runtime_state_source"),
        "saved_at": STARTUP_STATUS.get("runtime_state_saved_at"),
        "error": STARTUP_STATUS.get("runtime_state_error"),
    })
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


def _append_journal(event: dict):
    append_jsonl(JOURNAL_STORE, event)


def _save_news_cache_to_file():
    try:
        write_json_file(NEWS_CACHE_FILE, NEWS_CACHE)
    except Exception as e:
        print(f"Error saving news cache: {e}")


def _load_news_cache_from_file():
    data = read_json_file(NEWS_CACHE_FILE, default=None)
    if isinstance(data, dict):
        NEWS_CACHE["latest"] = data.get("latest", [])
        NEWS_CACHE["updated_at"] = data.get("updated_at")


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
    write_json_file(SNAPSHOT_STORE, payload)


def _load_state():
    return read_json_file(AI_SIGNAL_STATE_FILE, default={"last_keys": {}})


def _save_state(state: dict):
    write_json_file(AI_SIGNAL_STATE_FILE, state)


def _save_runtime_state():
    save_runtime_state(
        runtime_state_file=RUNTIME_STATE_FILE,
        snapshot_state=SNAPSHOT_STATE,
        ai4trade_state=AI4TRADE_STATE,
        get_gemini_runtime_state=get_gemini_runtime_state,
    )


def _load_runtime_state():
    try:
        result = load_runtime_state(
            runtime_state_file=RUNTIME_STATE_FILE,
            snapshot_state=SNAPSHOT_STATE,
            ai4trade_state=AI4TRADE_STATE,
            set_gemini_runtime_state=set_gemini_runtime_state,
        )
        STARTUP_STATUS["runtime_state_restored"] = result.get("restored", False)
        STARTUP_STATUS["runtime_state_source"] = result.get("source")
        STARTUP_STATUS["runtime_state_saved_at"] = result.get("saved_at")
        STARTUP_STATUS["runtime_state_error"] = result.get("error")
    except Exception as e:
        STARTUP_STATUS["runtime_state_restored"] = False
        STARTUP_STATUS["runtime_state_source"] = RUNTIME_STATE_FILE
        STARTUP_STATUS["runtime_state_saved_at"] = None
        STARTUP_STATUS["runtime_state_error"] = str(e)
        print(f"Error loading runtime state: {e}")


def _store_signal_payload(payload: dict):
    write_json_file(SIGNAL_STORE, payload)


def _store_generated_signal(payload: dict):
    write_json_file(GENERATED_SIGNAL_STORE, payload)


async def _send_telegram_message(text: str):
    if not TELEGRAM_NOTIFY_ENABLED or not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(url, json=payload)
    except Exception as e:
        print(f"Telegram notify error: {e}")


def _format_execution_notification(payload: dict, current_signal: Optional[dict] = None) -> Optional[str]:
    kind = str(payload.get("type") or "").upper()
    signal = current_signal or {}
    symbol = str(payload.get("symbol") or signal.get("symbol") or "?")
    side = str(payload.get("side") or signal.get("side") or "?")
    ticket = payload.get("ticket")
    price = payload.get("price")

    if kind == "OPEN":
        return "\n".join([
            "🟢 OPEN POSITION",
            f"Symbol: {symbol}",
            f"Side: {side}",
            f"Ticket: {ticket}",
            f"Price: {price}",
        ])
    if kind in {"CLOSE", "CLOSED", "EXIT"}:
        outcome = str(payload.get("outcome") or payload.get("result") or "").upper()
        pnl = payload.get("pnl")
        exit_reason = payload.get("exit_reason")
        return "\n".join([
            "🔴 CLOSED POSITION",
            f"Symbol: {symbol}",
            f"Side: {side}",
            f"Ticket: {ticket}",
            f"Outcome: {outcome}",
            f"PNL: {pnl}",
            f"Exit: {exit_reason}",
        ])
    return None


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(value, max_value))


def _snapshot_range(snapshot: dict) -> float:
    ohlc = snapshot.get("ohlc") or {}
    try:
        return max(float(ohlc.get("high", 0)) - float(ohlc.get("low", 0)), 0.0)
    except Exception:
        return 0.0


def _load_current_signal():
    return read_json_file(SIGNAL_STORE, default=None)


def _is_signal_fresh(signal: Optional[dict]) -> bool:
    return is_signal_fresh(signal, ACTIVE_SIGNAL_TTL_SEC)


def _parse_iso_utc(value: Optional[str]):
    return parse_iso_utc(value)


def _check_signal_conflict(current_signal: Optional[dict], normalized_symbol: str, decision: str, session_bucket: Optional[str] = None):
    now = datetime.now(timezone.utc)
    if SESSION_BUCKET_COOLDOWN_ENABLED and session_bucket:
        cooldown_map = SNAPSHOT_STATE.get("session_cooldowns") if isinstance(SNAPSHOT_STATE.get("session_cooldowns"), dict) else {}
        session_until = _parse_iso_utc(cooldown_map.get(session_bucket))
        if session_until is not None and now < session_until:
            return f"session_bucket_cooldown_active:{session_bucket}"
    if SLIPPAGE_COOLDOWN_ENABLED:
        cooldown_until = _parse_iso_utc(SNAPSHOT_STATE.get("slippage_cooldown_until"))
        if cooldown_until is not None and now < cooldown_until:
            return "slippage_cooldown_active"
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


def _build_signal(symbol: str, decision: str, entry: float, timeframe: str, confidence: float, reason: str, snapshot: Optional[dict] = None, decision_meta: Optional[dict] = None):
    candle_range = _snapshot_range(snapshot or {})
    decision_meta = decision_meta or {}
    trend_regime_score = float(decision_meta.get("trend_regime_score") or 0.0)
    session_bucket = str(decision_meta.get("session_bucket") or "UNKNOWN").upper()
    market_mode = str(decision_meta.get("market_mode") or "UNKNOWN").upper()
    conservative_factor = 1.0
    if trend_regime_score and trend_regime_score < 0.7:
        conservative_factor = 1.12
    elif trend_regime_score and trend_regime_score > 0.82:
        conservative_factor = 0.94

    session_zone_mult = 1.0
    if ADAPTIVE_ENTRY_ZONE_ENABLED:
        if session_bucket == "ASIA":
            session_zone_mult = ASIA_ENTRY_ZONE_MULT
        elif session_bucket == "LONDON":
            session_zone_mult = LONDON_ENTRY_ZONE_MULT
        elif session_bucket == "NY":
            session_zone_mult = NY_ENTRY_ZONE_MULT

    geometry_sl_mult = 1.0
    geometry_tp_mult = 1.0
    if ADAPTIVE_GEOMETRY_ENABLED:
        if session_bucket == "ASIA":
            geometry_sl_mult = ASIA_SL_MULT
            geometry_tp_mult = ASIA_TP_MULT
        elif session_bucket == "LONDON":
            geometry_sl_mult = LONDON_SL_MULT
            geometry_tp_mult = LONDON_TP_MULT
        elif session_bucket == "NY":
            geometry_sl_mult = NY_SL_MULT
            geometry_tp_mult = NY_TP_MULT

    if market_mode == "TOXIC":
        conservative_factor *= 1.12
    elif market_mode == "TRENDING":
        conservative_factor *= 1.02

    market_mode_sl_mult = 1.0
    market_mode_tp_mult = 1.0
    if market_mode == "TRENDING":
        market_mode_sl_mult = MARKET_MODE_TRENDING_SL_MULT
        market_mode_tp_mult = MARKET_MODE_TRENDING_TP_MULT
    elif market_mode == "BALANCED":
        market_mode_sl_mult = MARKET_MODE_BALANCED_SL_MULT
        market_mode_tp_mult = MARKET_MODE_BALANCED_TP_MULT
    elif market_mode == "CHOPPY":
        market_mode_sl_mult = MARKET_MODE_CHOPPY_SL_MULT
        market_mode_tp_mult = MARKET_MODE_CHOPPY_TP_MULT
    elif market_mode == "TOXIC":
        market_mode_sl_mult = MARKET_MODE_TOXIC_SL_MULT
        market_mode_tp_mult = MARKET_MODE_TOXIC_TP_MULT

    trend_geometry_sl_mult = 1.0
    trend_geometry_tp_mult = 1.0
    if TREND_GEOMETRY_ADAPTIVE_ENABLED:
        if trend_regime_score and trend_regime_score < 0.7:
            trend_geometry_sl_mult = WEAK_TREND_SL_MULT
            trend_geometry_tp_mult = WEAK_TREND_TP_MULT
        elif trend_regime_score and trend_regime_score > 0.82:
            trend_geometry_sl_mult = STRONG_TREND_SL_MULT
            trend_geometry_tp_mult = STRONG_TREND_TP_MULT
    geometry_sl_mult *= trend_geometry_sl_mult
    geometry_tp_mult *= trend_geometry_tp_mult
    geometry_sl_mult *= market_mode_sl_mult
    geometry_tp_mult *= market_mode_tp_mult
    if market_mode == "TRENDING" and decision == "SELL":
        geometry_sl_mult *= TRENDING_SELL_EXTRA_SL_MULT
        geometry_tp_mult *= TRENDING_SELL_EXTRA_TP_MULT

    if symbol == "XAUUSD":
        zone = _clamp(candle_range * XAU_ENTRY_ZONE_RANGE_MULT * session_zone_mult, XAU_ENTRY_ZONE_MIN, XAU_ENTRY_ZONE_MAX)
        if market_mode == "TRENDING":
            zone *= 0.92
        elif market_mode in {"CHOPPY", "TOXIC"}:
            zone *= 0.8
        sl_offset = _clamp(max(XAU_SL_MIN, candle_range * XAU_SL_RANGE_MULT), XAU_SL_MIN, XAU_SL_MAX) * conservative_factor * geometry_sl_mult
        tp1_offset = max(XAU_TP1_MIN, candle_range * XAU_TP1_RANGE_MULT) * geometry_tp_mult
        tp2_offset = max(XAU_TP2_MIN, candle_range * XAU_TP2_RANGE_MULT) * geometry_tp_mult
        digits = 2
        spread_max_points = 120
    else:
        zone = _clamp(candle_range * FOREX_ENTRY_ZONE_RANGE_MULT * session_zone_mult, FOREX_ENTRY_ZONE_MIN, FOREX_ENTRY_ZONE_MAX)
        sl_offset = _clamp(max(FOREX_SL_MIN, candle_range * FOREX_SL_RANGE_MULT), FOREX_SL_MIN, FOREX_SL_MAX) * conservative_factor * geometry_sl_mult
        tp1_offset = max(FOREX_TP1_MIN, candle_range * FOREX_TP1_RANGE_MULT) * geometry_tp_mult
        tp2_offset = max(FOREX_TP2_MIN, candle_range * FOREX_TP2_RANGE_MULT) * geometry_tp_mult
        digits = 5
        spread_max_points = 35

    min_tp1_rr = 1.35
    min_tp2_rr = 1.9
    tp1_offset = max(tp1_offset, sl_offset * min_tp1_rr)
    tp2_offset = max(tp2_offset, sl_offset * min_tp2_rr)

    sl = entry - sl_offset if decision == "BUY" else entry + sl_offset
    tp1 = entry + tp1_offset if decision == "BUY" else entry - tp1_offset
    tp2 = entry + tp2_offset if decision == "BUY" else entry - tp2_offset
    rr_tp1 = tp1_offset / sl_offset if sl_offset > 0 else None
    rr_tp2 = tp2_offset / sl_offset if sl_offset > 0 else None

    trailing_start_r_mult = TRAILING_START_R_MULT
    trailing_step_r_mult = TRAILING_STEP_R_MULT
    time_based_trailing_after_sec = TIME_BASED_TRAILING_AFTER_SEC
    time_based_trailing_min_r_mult = TIME_BASED_TRAILING_MIN_R_MULT
    time_based_trailing_sl_r_mult = TIME_BASED_TRAILING_SL_R_MULT
    if ADAPTIVE_TRAILING_ENABLED:
        if session_bucket == "ASIA":
            trailing_start_r_mult = ASIA_TRAILING_START_R_MULT
            trailing_step_r_mult = ASIA_TRAILING_STEP_R_MULT
            time_based_trailing_after_sec = ASIA_TIME_BASED_TRAILING_AFTER_SEC
        elif session_bucket == "LONDON":
            trailing_start_r_mult = LONDON_TRAILING_START_R_MULT
            trailing_step_r_mult = LONDON_TRAILING_STEP_R_MULT
            time_based_trailing_after_sec = LONDON_TIME_BASED_TRAILING_AFTER_SEC
        elif session_bucket == "NY":
            trailing_start_r_mult = NY_TRAILING_START_R_MULT
            trailing_step_r_mult = NY_TRAILING_STEP_R_MULT
            time_based_trailing_after_sec = NY_TIME_BASED_TRAILING_AFTER_SEC

    if market_mode == "TRENDING":
        time_based_trailing_after_sec = TRENDING_TIME_BASED_TRAILING_AFTER_SEC
        time_based_trailing_min_r_mult = TRENDING_TIME_BASED_TRAILING_MIN_R_MULT
        time_based_trailing_sl_r_mult = TRENDING_TIME_BASED_TRAILING_SL_R_MULT
    elif market_mode == "BALANCED":
        time_based_trailing_after_sec = BALANCED_TIME_BASED_TRAILING_AFTER_SEC
        time_based_trailing_min_r_mult = BALANCED_TIME_BASED_TRAILING_MIN_R_MULT
        time_based_trailing_sl_r_mult = BALANCED_TIME_BASED_TRAILING_SL_R_MULT
    elif market_mode == "CHOPPY":
        time_based_trailing_after_sec = CHOPPY_TIME_BASED_TRAILING_AFTER_SEC
        time_based_trailing_min_r_mult = CHOPPY_TIME_BASED_TRAILING_MIN_R_MULT
        time_based_trailing_sl_r_mult = CHOPPY_TIME_BASED_TRAILING_SL_R_MULT
    elif market_mode == "TOXIC":
        time_based_trailing_after_sec = TOXIC_TIME_BASED_TRAILING_AFTER_SEC
        time_based_trailing_min_r_mult = TOXIC_TIME_BASED_TRAILING_MIN_R_MULT
        time_based_trailing_sl_r_mult = TOXIC_TIME_BASED_TRAILING_SL_R_MULT
    elif market_mode == "QUIET":
        time_based_trailing_after_sec = QUIET_TIME_BASED_TRAILING_AFTER_SEC
        time_based_trailing_min_r_mult = QUIET_TIME_BASED_TRAILING_MIN_R_MULT
        time_based_trailing_sl_r_mult = QUIET_TIME_BASED_TRAILING_SL_R_MULT

    signal_ttl = 180
    if market_mode == "TRENDING":
        signal_ttl = 120
    elif market_mode == "QUIET":
        signal_ttl = 240
    elif market_mode == "CHOPPY":
        signal_ttl = 90

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
        "max_signal_age_sec": signal_ttl,
        "market_context": {
            "spread_max_points": spread_max_points,
            "session": "LOCAL_AI_QUEUE",
            "news_block_minutes": DEFAULT_NEWS_BLOCK_MINUTES,
            "market_mode": market_mode,
            "signal_ttl_sec": signal_ttl,
            "entry_zone_size": round(zone, digits),
            "entry_zone_session_mult": round(session_zone_mult, 4),
            "geometry_sl_session_mult": round(geometry_sl_mult, 4),
            "geometry_tp_session_mult": round(geometry_tp_mult, 4),
            "geometry_trend_sl_mult": round(trend_geometry_sl_mult, 4),
            "geometry_trend_tp_mult": round(trend_geometry_tp_mult, 4),
            "geometry_market_mode_sl_mult": round(market_mode_sl_mult, 4),
            "geometry_market_mode_tp_mult": round(market_mode_tp_mult, 4),
            "snapshot_range": round(candle_range, digits),
            "sl_distance": round(sl_offset, digits),
            "tp1_distance": round(tp1_offset, digits),
            "tp2_distance": round(tp2_offset, digits),
            "rr_tp1": round(rr_tp1, 4) if rr_tp1 is not None else None,
            "rr_tp2": round(rr_tp2, 4) if rr_tp2 is not None else None,
            "trend_regime_score": decision_meta.get("trend_regime_score"),
            "structure_reason": decision_meta.get("recent_structure"),
            "trend_regime_reason": decision_meta.get("trend_regime_reason"),
            "pattern_lockout_key": decision_meta.get("pattern_lockout_key"),
            "quality_tier": decision_meta.get("quality_tier"),
            "quality_tier_label": decision_meta.get("quality_tier_label"),
            "quality_penalty_count": decision_meta.get("quality_penalty_count"),
            "trailing": {
                "enabled": TRAILING_ENABLED,
                "adaptive_enabled": ADAPTIVE_TRAILING_ENABLED,
                "session_bucket": session_bucket,
                "break_even_r_mult": BREAK_EVEN_R_MULT,
                "break_even_buffer_r_mult": BREAK_EVEN_BUFFER_R_MULT,
                "trailing_start_r_mult": trailing_start_r_mult,
                "trailing_step_r_mult": trailing_step_r_mult,
                "trailing_sl_r_mult": TRAILING_SL_R_MULT,
                "time_based_enabled": TIME_BASED_TRAILING_ENABLED,
                "time_based_after_sec": time_based_trailing_after_sec,
                "time_based_min_r_mult": time_based_trailing_min_r_mult,
                "time_based_sl_r_mult": time_based_trailing_sl_r_mult,
            },
        },
        "structure_reason": decision_meta.get("recent_structure"),
        "trend_regime_reason": decision_meta.get("trend_regime_reason"),
        "pattern_lockout_key": decision_meta.get("pattern_lockout_key"),
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
    if LOCAL_ONLY_MODE:
        AI4TRADE_STATE["last_error"] = "disabled_local_only_mode"
        return
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
    if LOCAL_ONLY_MODE:
        return
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
                SNAPSHOT_STATE["last_deterministic_score"] = result.get("deterministic_score")
                SNAPSHOT_STATE["last_fusion_score"] = result.get("fusion_score")
                SNAPSHOT_STATE["last_adaptive_trade_threshold"] = result.get("adaptive_trade_threshold")
                SNAPSHOT_STATE["last_adaptive_no_trade_threshold"] = result.get("adaptive_no_trade_threshold")
                SNAPSHOT_STATE["last_gemini_evaluation"] = result.get("evaluation")
                SNAPSHOT_STATE["last_outcome_penalty"] = result.get("outcome_penalty")
                SNAPSHOT_STATE["last_outcome_penalty_reason"] = result.get("outcome_penalty_reason")
                SNAPSHOT_STATE["last_same_side_losses"] = result.get("same_side_losses")
                SNAPSHOT_STATE["last_market_toxicity_score"] = result.get("market_toxicity_score")
                SNAPSHOT_STATE["last_market_toxicity_penalty"] = result.get("market_toxicity_penalty")
                SNAPSHOT_STATE["last_market_toxicity_reason"] = result.get("market_toxicity_reason")
                SNAPSHOT_STATE["last_market_mode"] = result.get("market_mode")
                SNAPSHOT_STATE["last_market_mode_reason"] = result.get("market_mode_reason")
                SNAPSHOT_STATE["last_market_mode_threshold_bonus"] = result.get("market_mode_threshold_bonus")
                SNAPSHOT_STATE["last_market_mode_confidence_penalty"] = result.get("market_mode_confidence_penalty")
                SNAPSHOT_STATE["last_journal_reason_penalty"] = result.get("journal_reason_penalty")
                SNAPSHOT_STATE["last_journal_reason_penalty_reason"] = result.get("journal_reason_penalty_reason")
                SNAPSHOT_STATE["last_journal_reason_loss_rate"] = result.get("journal_reason_loss_rate")
                SNAPSHOT_STATE["last_journal_reason_trade_count"] = result.get("journal_reason_trade_count")
                SNAPSHOT_STATE["last_session_bucket"] = result.get("session_bucket")
                SNAPSHOT_STATE["last_session_penalty"] = result.get("session_penalty")
                SNAPSHOT_STATE["last_session_penalty_reason"] = result.get("session_penalty_reason")
                SNAPSHOT_STATE["last_session_loss_rate"] = result.get("session_loss_rate")
                SNAPSHOT_STATE["last_session_trade_count"] = result.get("session_trade_count")
                SNAPSHOT_STATE["last_exit_reason_penalty"] = result.get("exit_reason_penalty")
                SNAPSHOT_STATE["last_exit_reason_penalty_reason"] = result.get("exit_reason_penalty_reason")
                SNAPSHOT_STATE["last_exit_reason_loss_rate"] = result.get("exit_reason_loss_rate")
                SNAPSHOT_STATE["last_exit_reason_trade_count"] = result.get("exit_reason_trade_count")
                SNAPSHOT_STATE["last_auto_hardening_threshold_bonus"] = result.get("auto_hardening_threshold_bonus")
                SNAPSHOT_STATE["last_auto_hardening_reason"] = result.get("auto_hardening_reason")
                SNAPSHOT_STATE["last_auto_hardening_triggered"] = result.get("auto_hardening_triggered")
                SNAPSHOT_STATE["last_pattern_lockout_penalty"] = result.get("pattern_lockout_penalty")
                SNAPSHOT_STATE["last_pattern_lockout_reason"] = result.get("pattern_lockout_reason")
                SNAPSHOT_STATE["last_pattern_lockout_count"] = result.get("pattern_lockout_count")
                SNAPSHOT_STATE["last_pattern_lockout_key"] = result.get("pattern_lockout_key")
                SNAPSHOT_STATE["last_trend_regime_reason"] = result.get("trend_regime_reason")
                SNAPSHOT_STATE["last_trend_regime_score"] = result.get("trend_regime_score")
                SNAPSHOT_STATE["last_trend_regime_alignment"] = result.get("trend_regime_alignment")
                SNAPSHOT_STATE["last_trend_regime_opposing_count"] = result.get("trend_regime_opposing_count")
                SNAPSHOT_STATE["last_trend_regime_strong_aligned"] = result.get("trend_regime_strong_aligned")
                SNAPSHOT_STATE["last_trend_regime_close_position"] = result.get("trend_regime_close_position")
                SNAPSHOT_STATE["last_snapshot_timeframe"] = snap.get("timeframe")
                SNAPSHOT_STATE["last_quality_tier"] = result.get("quality_tier")
                SNAPSHOT_STATE["last_quality_tier_label"] = result.get("quality_tier_label")
                SNAPSHOT_STATE["last_quality_penalty_count"] = result.get("quality_penalty_count")
                if result.get("decision") not in {"BUY", "SELL"}:
                    SNAPSHOT_STATE["last_no_trade_at"] = datetime.now(timezone.utc).isoformat()
                    SNAPSHOT_STATE["last_no_trade_reason"] = result.get("reason")
                    SNAPSHOT_STATE["last_no_trade_symbol"] = snap.get("symbol")
                    _save_runtime_state()
                    _append_journal({
                        "event_id": str(uuid.uuid4()),
                        "type": "snapshot_rejected",
                        "at": datetime.now(timezone.utc).isoformat(),
                        "symbol": snap.get("symbol"),
                        "timeframe": snap.get("timeframe"),
                        "reason": result.get("reason"),
                        "decision_source": result.get("decision_source", "unknown"),
                        "deterministic_score": result.get("deterministic_score"),
                        "fusion_score": result.get("fusion_score"),
                        "adaptive_trade_threshold": result.get("adaptive_trade_threshold"),
                        "adaptive_no_trade_threshold": result.get("adaptive_no_trade_threshold"),
                        "evaluation": result.get("evaluation"),
                        "outcome_penalty": result.get("outcome_penalty"),
                        "outcome_penalty_reason": result.get("outcome_penalty_reason"),
                        "same_side_losses": result.get("same_side_losses"),
                        "pattern_lockout_penalty": result.get("pattern_lockout_penalty"),
                        "pattern_lockout_reason": result.get("pattern_lockout_reason"),
                        "pattern_lockout_count": result.get("pattern_lockout_count"),
                        "pattern_lockout_key": result.get("pattern_lockout_key"),
                        "trend_regime_reason": result.get("trend_regime_reason"),
                        "trend_regime_score": result.get("trend_regime_score"),
                        "trend_regime_alignment": result.get("trend_regime_alignment"),
                        "trend_regime_opposing_count": result.get("trend_regime_opposing_count"),
                        "trend_regime_strong_aligned": result.get("trend_regime_strong_aligned"),
                        "trend_regime_close_position": result.get("trend_regime_close_position"),
                        "quality_tier": result.get("quality_tier"),
                        "quality_tier_label": result.get("quality_tier_label"),
                        "quality_penalty_count": result.get("quality_penalty_count"),
                    })
                    continue
                normalized_symbol = result.get("symbol", snap["symbol"])
                key = f"{normalized_symbol}:{result['decision']}:{result['entry']}"
                if state.get("last_keys", {}).get(normalized_symbol) == key:
                    continue
                current_signal = _load_current_signal()
                reject_reason = _check_signal_conflict(current_signal, normalized_symbol, result.get("decision"), result.get("session_bucket"))
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
                    _save_runtime_state()
                    continue
                signal = _build_signal(normalized_symbol, result["decision"], result["entry"], result["timeframe"], result["confidence"], result["reason"], snap, result)
                SNAPSHOT_STATE["last_sl_distance"] = signal.get("market_context", {}).get("sl_distance")
                SNAPSHOT_STATE["last_tp1_distance"] = signal.get("market_context", {}).get("tp1_distance")
                SNAPSHOT_STATE["last_tp2_distance"] = signal.get("market_context", {}).get("tp2_distance")
                SNAPSHOT_STATE["last_rr_tp1"] = signal.get("market_context", {}).get("rr_tp1")
                SNAPSHOT_STATE["last_rr_tp2"] = signal.get("market_context", {}).get("rr_tp2")
                _store_generated_signal(signal)
                _store_signal_payload(signal)
                state.setdefault("last_keys", {})[normalized_symbol] = key
                _save_state(state)
                SNAPSHOT_STATE["last_signal_id"] = signal["signal_id"]
                _save_runtime_state()
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
                    "deterministic_score": result.get("deterministic_score"),
                    "fusion_score": result.get("fusion_score"),
                    "adaptive_trade_threshold": result.get("adaptive_trade_threshold"),
                    "adaptive_no_trade_threshold": result.get("adaptive_no_trade_threshold"),
                    "evaluation": result.get("evaluation"),
                    "outcome_penalty": result.get("outcome_penalty"),
                    "outcome_penalty_reason": result.get("outcome_penalty_reason"),
                    "same_side_losses": result.get("same_side_losses"),
                    "market_toxicity_score": result.get("market_toxicity_score"),
                    "market_toxicity_penalty": result.get("market_toxicity_penalty"),
                    "market_toxicity_reason": result.get("market_toxicity_reason"),
                    "journal_reason_penalty": result.get("journal_reason_penalty"),
                    "journal_reason_penalty_reason": result.get("journal_reason_penalty_reason"),
                    "journal_reason_loss_rate": result.get("journal_reason_loss_rate"),
                    "journal_reason_trade_count": result.get("journal_reason_trade_count"),
                    "session_bucket": result.get("session_bucket"),
                    "session_penalty": result.get("session_penalty"),
                    "session_penalty_reason": result.get("session_penalty_reason"),
                    "session_loss_rate": result.get("session_loss_rate"),
                    "session_trade_count": result.get("session_trade_count"),
                    "exit_reason_penalty": result.get("exit_reason_penalty"),
                    "exit_reason_penalty_reason": result.get("exit_reason_penalty_reason"),
                    "exit_reason_loss_rate": result.get("exit_reason_loss_rate"),
                    "exit_reason_trade_count": result.get("exit_reason_trade_count"),
                    "auto_hardening_threshold_bonus": result.get("auto_hardening_threshold_bonus"),
                    "auto_hardening_reason": result.get("auto_hardening_reason"),
                    "auto_hardening_triggered": result.get("auto_hardening_triggered"),
                    "pattern_lockout_penalty": result.get("pattern_lockout_penalty"),
                    "pattern_lockout_reason": result.get("pattern_lockout_reason"),
                    "pattern_lockout_count": result.get("pattern_lockout_count"),
                    "pattern_lockout_key": result.get("pattern_lockout_key"),
                    "trend_regime_reason": result.get("trend_regime_reason"),
                    "trend_regime_score": result.get("trend_regime_score"),
                    "trend_regime_alignment": result.get("trend_regime_alignment"),
                    "trend_regime_opposing_count": result.get("trend_regime_opposing_count"),
                    "trend_regime_strong_aligned": result.get("trend_regime_strong_aligned"),
                    "trend_regime_close_position": result.get("trend_regime_close_position"),
                    "quality_tier": result.get("quality_tier"),
                    "quality_tier_label": result.get("quality_tier_label"),
                    "quality_penalty_count": result.get("quality_penalty_count"),
                    "sl_distance": signal.get("market_context", {}).get("sl_distance"),
                    "tp1_distance": signal.get("market_context", {}).get("tp1_distance"),
                    "tp2_distance": signal.get("market_context", {}).get("tp2_distance"),
                    "rr_tp1": signal.get("market_context", {}).get("rr_tp1"),
                    "rr_tp2": signal.get("market_context", {}).get("rr_tp2"),
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
        "xau_sl_min": XAU_SL_MIN,
        "xau_sl_max": XAU_SL_MAX,
        "xau_sl_range_mult": XAU_SL_RANGE_MULT,
        "xau_tp1_min": XAU_TP1_MIN,
        "xau_tp1_range_mult": XAU_TP1_RANGE_MULT,
        "xau_tp2_min": XAU_TP2_MIN,
        "xau_tp2_range_mult": XAU_TP2_RANGE_MULT,
        "session_filter_enabled": os.getenv("SESSION_FILTER_ENABLED", "true").lower() in {"1", "true", "yes", "on"},
        "session_start_hour_utc": int(os.getenv("SESSION_START_HOUR_UTC", "6")),
        "session_end_hour_utc": int(os.getenv("SESSION_END_HOUR_UTC", "21")),
        "default_news_block_minutes": DEFAULT_NEWS_BLOCK_MINUTES,
        "trailing_enabled": TRAILING_ENABLED,
        "slippage_cooldown_enabled": SLIPPAGE_COOLDOWN_ENABLED,
        "slippage_cooldown_window_sec": SLIPPAGE_COOLDOWN_WINDOW_SEC,
        "slippage_cooldown_threshold": SLIPPAGE_COOLDOWN_THRESHOLD,
        "slippage_cooldown_sec": SLIPPAGE_COOLDOWN_SEC,
        "session_bucket_cooldown_enabled": SESSION_BUCKET_COOLDOWN_ENABLED,
        "session_bucket_cooldown_threshold": SESSION_BUCKET_COOLDOWN_THRESHOLD,
        "session_bucket_cooldown_sec": SESSION_BUCKET_COOLDOWN_SEC,
        "local_only_mode": LOCAL_ONLY_MODE,
        "break_even_r_mult": BREAK_EVEN_R_MULT,
        "break_even_buffer_r_mult": BREAK_EVEN_BUFFER_R_MULT,
        "trailing_start_r_mult": TRAILING_START_R_MULT,
        "trailing_step_r_mult": TRAILING_STEP_R_MULT,
        "trailing_sl_r_mult": TRAILING_SL_R_MULT,
        "adaptive_trailing_enabled": ADAPTIVE_TRAILING_ENABLED,
        "asia_trailing_start_r_mult": ASIA_TRAILING_START_R_MULT,
        "asia_trailing_step_r_mult": ASIA_TRAILING_STEP_R_MULT,
        "london_trailing_start_r_mult": LONDON_TRAILING_START_R_MULT,
        "london_trailing_step_r_mult": LONDON_TRAILING_STEP_R_MULT,
        "ny_trailing_start_r_mult": NY_TRAILING_START_R_MULT,
        "ny_trailing_step_r_mult": NY_TRAILING_STEP_R_MULT,
        "adaptive_entry_zone_enabled": ADAPTIVE_ENTRY_ZONE_ENABLED,
        "asia_entry_zone_mult": ASIA_ENTRY_ZONE_MULT,
        "london_entry_zone_mult": LONDON_ENTRY_ZONE_MULT,
        "ny_entry_zone_mult": NY_ENTRY_ZONE_MULT,
        "adaptive_geometry_enabled": ADAPTIVE_GEOMETRY_ENABLED,
        "asia_sl_mult": ASIA_SL_MULT,
        "asia_tp_mult": ASIA_TP_MULT,
        "london_sl_mult": LONDON_SL_MULT,
        "london_tp_mult": LONDON_TP_MULT,
        "ny_sl_mult": NY_SL_MULT,
        "ny_tp_mult": NY_TP_MULT,
        "trend_geometry_adaptive_enabled": TREND_GEOMETRY_ADAPTIVE_ENABLED,
        "weak_trend_sl_mult": WEAK_TREND_SL_MULT,
        "weak_trend_tp_mult": WEAK_TREND_TP_MULT,
        "strong_trend_sl_mult": STRONG_TREND_SL_MULT,
        "strong_trend_tp_mult": STRONG_TREND_TP_MULT,
    }


def _current_signal_summary():
    return current_signal_summary(_load_current_signal(), ACTIVE_SIGNAL_TTL_SEC)


def _risk_state_summary():
    return {
        "last_trade_outcome": SNAPSHOT_STATE.get("last_trade_outcome"),
        "last_loss_side": SNAPSHOT_STATE.get("last_loss_side"),
        "last_loss_at": SNAPSHOT_STATE.get("last_loss_at"),
        "slippage_cooldown_until": SNAPSHOT_STATE.get("slippage_cooldown_until"),
        "recent_slippage_events": SNAPSHOT_STATE.get("recent_slippage_events"),
        "session_cooldowns": SNAPSHOT_STATE.get("session_cooldowns"),
        "consecutive_losses": SNAPSHOT_STATE.get("consecutive_losses"),
        "last_no_trade_reason": SNAPSHOT_STATE.get("last_no_trade_reason"),
        "last_execution_type": SNAPSHOT_STATE.get("last_execution_type"),
        "last_execution_signal_id": SNAPSHOT_STATE.get("last_execution_signal_id"),
        "last_execution_ticket": SNAPSHOT_STATE.get("last_execution_ticket"),
        "last_exit_reason": SNAPSHOT_STATE.get("last_exit_reason"),
        "last_trailing_initial_risk_price": SNAPSHOT_STATE.get("last_trailing_initial_risk_price"),
        "last_trailing_initial_stop_loss": SNAPSHOT_STATE.get("last_trailing_initial_stop_loss"),
        "last_trailing_initial_tp1": SNAPSHOT_STATE.get("last_trailing_initial_tp1"),
        "last_trailing_last_applied_stop_loss": SNAPSHOT_STATE.get("last_trailing_last_applied_stop_loss"),
        "last_break_even_activated": SNAPSHOT_STATE.get("last_break_even_activated"),
        "last_trailing_activated": SNAPSHOT_STATE.get("last_trailing_activated"),
        "last_market_toxicity_score": SNAPSHOT_STATE.get("last_market_toxicity_score"),
        "last_market_toxicity_penalty": SNAPSHOT_STATE.get("last_market_toxicity_penalty"),
        "last_market_toxicity_reason": SNAPSHOT_STATE.get("last_market_toxicity_reason"),
        "last_outcome_penalty": SNAPSHOT_STATE.get("last_outcome_penalty"),
        "last_outcome_penalty_reason": SNAPSHOT_STATE.get("last_outcome_penalty_reason"),
        "last_same_side_losses": SNAPSHOT_STATE.get("last_same_side_losses"),
        "last_journal_reason_penalty": SNAPSHOT_STATE.get("last_journal_reason_penalty"),
        "last_journal_reason_penalty_reason": SNAPSHOT_STATE.get("last_journal_reason_penalty_reason"),
        "last_journal_reason_loss_rate": SNAPSHOT_STATE.get("last_journal_reason_loss_rate"),
        "last_journal_reason_trade_count": SNAPSHOT_STATE.get("last_journal_reason_trade_count"),
        "last_session_bucket": SNAPSHOT_STATE.get("last_session_bucket"),
        "last_session_penalty": SNAPSHOT_STATE.get("last_session_penalty"),
        "last_session_penalty_reason": SNAPSHOT_STATE.get("last_session_penalty_reason"),
        "last_session_loss_rate": SNAPSHOT_STATE.get("last_session_loss_rate"),
        "last_session_trade_count": SNAPSHOT_STATE.get("last_session_trade_count"),
        "last_exit_reason_penalty": SNAPSHOT_STATE.get("last_exit_reason_penalty"),
        "last_exit_reason_penalty_reason": SNAPSHOT_STATE.get("last_exit_reason_penalty_reason"),
        "last_exit_reason_loss_rate": SNAPSHOT_STATE.get("last_exit_reason_loss_rate"),
        "last_exit_reason_trade_count": SNAPSHOT_STATE.get("last_exit_reason_trade_count"),
        "last_auto_hardening_threshold_bonus": SNAPSHOT_STATE.get("last_auto_hardening_threshold_bonus"),
        "last_auto_hardening_reason": SNAPSHOT_STATE.get("last_auto_hardening_reason"),
        "last_auto_hardening_triggered": SNAPSHOT_STATE.get("last_auto_hardening_triggered"),
        "last_pattern_lockout_penalty": SNAPSHOT_STATE.get("last_pattern_lockout_penalty"),
        "last_pattern_lockout_reason": SNAPSHOT_STATE.get("last_pattern_lockout_reason"),
        "last_pattern_lockout_count": SNAPSHOT_STATE.get("last_pattern_lockout_count"),
        "last_pattern_lockout_key": SNAPSHOT_STATE.get("last_pattern_lockout_key"),
    }


def _queue_summary():
    return {
        "size": SNAPSHOT_QUEUE.qsize(),
        "last_received_at": SNAPSHOT_STATE.get("last_received_at"),
        "last_processed_at": SNAPSHOT_STATE.get("last_processed_at"),
    }


def _strategy_summary():
    return {
        "last_signal_id": SNAPSHOT_STATE.get("last_signal_id"),
        "last_decision": SNAPSHOT_STATE.get("last_decision"),
        "last_reason": SNAPSHOT_STATE.get("last_reason"),
        "last_decision_source": SNAPSHOT_STATE.get("last_decision_source"),
        "last_deterministic_score": SNAPSHOT_STATE.get("last_deterministic_score"),
        "last_fusion_score": SNAPSHOT_STATE.get("last_fusion_score"),
        "last_adaptive_trade_threshold": SNAPSHOT_STATE.get("last_adaptive_trade_threshold"),
        "last_adaptive_no_trade_threshold": SNAPSHOT_STATE.get("last_adaptive_no_trade_threshold"),
        "last_gemini_evaluation": SNAPSHOT_STATE.get("last_gemini_evaluation"),
        "last_outcome_penalty": SNAPSHOT_STATE.get("last_outcome_penalty"),
        "last_outcome_penalty_reason": SNAPSHOT_STATE.get("last_outcome_penalty_reason"),
        "last_same_side_losses": SNAPSHOT_STATE.get("last_same_side_losses"),
        "last_market_toxicity_score": SNAPSHOT_STATE.get("last_market_toxicity_score"),
        "last_market_toxicity_penalty": SNAPSHOT_STATE.get("last_market_toxicity_penalty"),
        "last_market_toxicity_reason": SNAPSHOT_STATE.get("last_market_toxicity_reason"),
        "last_journal_reason_penalty": SNAPSHOT_STATE.get("last_journal_reason_penalty"),
        "last_journal_reason_penalty_reason": SNAPSHOT_STATE.get("last_journal_reason_penalty_reason"),
        "last_journal_reason_loss_rate": SNAPSHOT_STATE.get("last_journal_reason_loss_rate"),
        "last_journal_reason_trade_count": SNAPSHOT_STATE.get("last_journal_reason_trade_count"),
        "last_session_bucket": SNAPSHOT_STATE.get("last_session_bucket"),
        "last_session_penalty": SNAPSHOT_STATE.get("last_session_penalty"),
        "last_session_penalty_reason": SNAPSHOT_STATE.get("last_session_penalty_reason"),
        "last_session_loss_rate": SNAPSHOT_STATE.get("last_session_loss_rate"),
        "last_session_trade_count": SNAPSHOT_STATE.get("last_session_trade_count"),
        "last_exit_reason_penalty": SNAPSHOT_STATE.get("last_exit_reason_penalty"),
        "last_exit_reason_penalty_reason": SNAPSHOT_STATE.get("last_exit_reason_penalty_reason"),
        "last_exit_reason_loss_rate": SNAPSHOT_STATE.get("last_exit_reason_loss_rate"),
        "last_exit_reason_trade_count": SNAPSHOT_STATE.get("last_exit_reason_trade_count"),
        "last_auto_hardening_threshold_bonus": SNAPSHOT_STATE.get("last_auto_hardening_threshold_bonus"),
        "last_auto_hardening_reason": SNAPSHOT_STATE.get("last_auto_hardening_reason"),
        "last_auto_hardening_triggered": SNAPSHOT_STATE.get("last_auto_hardening_triggered"),
        "last_pattern_lockout_penalty": SNAPSHOT_STATE.get("last_pattern_lockout_penalty"),
        "last_pattern_lockout_reason": SNAPSHOT_STATE.get("last_pattern_lockout_reason"),
        "last_pattern_lockout_count": SNAPSHOT_STATE.get("last_pattern_lockout_count"),
        "last_pattern_lockout_key": SNAPSHOT_STATE.get("last_pattern_lockout_key"),
        "last_trend_regime_reason": SNAPSHOT_STATE.get("last_trend_regime_reason"),
        "last_trend_regime_score": SNAPSHOT_STATE.get("last_trend_regime_score"),
        "last_trend_regime_alignment": SNAPSHOT_STATE.get("last_trend_regime_alignment"),
        "last_trend_regime_opposing_count": SNAPSHOT_STATE.get("last_trend_regime_opposing_count"),
        "last_trend_regime_strong_aligned": SNAPSHOT_STATE.get("last_trend_regime_strong_aligned"),
        "last_trend_regime_close_position": SNAPSHOT_STATE.get("last_trend_regime_close_position"),
        "last_sl_distance": SNAPSHOT_STATE.get("last_sl_distance"),
        "last_tp1_distance": SNAPSHOT_STATE.get("last_tp1_distance"),
        "last_tp2_distance": SNAPSHOT_STATE.get("last_tp2_distance"),
        "last_rr_tp1": SNAPSHOT_STATE.get("last_rr_tp1"),
        "last_rr_tp2": SNAPSHOT_STATE.get("last_rr_tp2"),
        "last_snapshot_timeframe": SNAPSHOT_STATE.get("last_snapshot_timeframe"),
        "last_trailing_initial_risk_price": SNAPSHOT_STATE.get("last_trailing_initial_risk_price"),
        "last_trailing_initial_stop_loss": SNAPSHOT_STATE.get("last_trailing_initial_stop_loss"),
        "last_trailing_initial_tp1": SNAPSHOT_STATE.get("last_trailing_initial_tp1"),
        "last_trailing_last_applied_stop_loss": SNAPSHOT_STATE.get("last_trailing_last_applied_stop_loss"),
        "last_break_even_activated": SNAPSHOT_STATE.get("last_break_even_activated"),
        "last_trailing_activated": SNAPSHOT_STATE.get("last_trailing_activated"),
        "last_quality_tier": SNAPSHOT_STATE.get("last_quality_tier"),
        "last_quality_tier_label": SNAPSHOT_STATE.get("last_quality_tier_label"),
        "last_quality_penalty_count": SNAPSHOT_STATE.get("last_quality_penalty_count"),
    }


def _news_summary(block_minutes: int = DEFAULT_NEWS_BLOCK_MINUTES):
    active_news = get_active_news_event(block_minutes)
    return {
        "blocked": active_news is not None,
        "active": active_news,
        "updated_at": NEWS_CACHE.get("updated_at"),
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


def _classify_rejection_gate(reason: str) -> str:
    reason = str(reason or "unknown")
    if reason.startswith("outside_session:") or reason.startswith("session_hard_block:") or reason.startswith("session_bucket_cooldown_active:"):
        return "session"
    if reason.startswith("range_too_"):
        return "volatility"
    if "structure" in reason or reason.startswith("weak_last_candle:") or reason.startswith("weak_prev_candle:") or reason.startswith("bias_conflict:"):
        return "structure"
    if reason.startswith("trend_regime_"):
        return "trend"
    if reason.startswith("slippage_cooldown_active") or reason.startswith("poor_spread_quality:") or reason.startswith("spread_too_high:"):
        return "execution"
    if reason.startswith("outcome_revenge_block:") or reason.startswith("loss_cooldown_active") or reason.startswith("max_consecutive_losses_reached"):
        return "outcome"
    if reason.startswith("pattern_lockout:"):
        return "pattern"
    if reason.startswith("market_toxicity_block:"):
        return "toxicity"
    if reason.startswith("quality_tier_block:"):
        return "quality"
    if reason.startswith("position_open_") or reason.startswith("active_signal_") or reason.startswith("opposite_signal_blocked_") or reason.startswith("post_close_cooldown_active"):
        return "conflict"
    return "other"


def _audit_summary(limit: int = 200):
    events = _read_journal_events(limit=limit)
    rejection_counts = {}
    recent_errors = []
    executions = []
    decision_funnel = {
        "snapshots_rejected": 0,
        "signals_generated": 0,
        "executions_opened": 0,
        "executions_closed": 0,
        "wins": 0,
        "losses": 0,
        "breakevens": 0,
    }
    gate_kill_breakdown = {
        "session": 0,
        "volatility": 0,
        "structure": 0,
        "trend": 0,
        "execution": 0,
        "outcome": 0,
        "pattern": 0,
        "toxicity": 0,
        "quality": 0,
        "conflict": 0,
        "other": 0,
    }
    gate_session_matrix = {}
    generated_signals = []
    reason_stats = {}
    exit_reason_counts = {}
    outcome_counts = {}
    market_toxicity_histogram = {
        "0.00-0.19": 0,
        "0.20-0.39": 0,
        "0.40-0.59": 0,
        "0.60-0.79": 0,
        "0.80-1.00": 0,
    }
    geometry_market_mode_sl_mult_counts = {}
    geometry_market_mode_tp_mult_counts = {}
    geometry_market_mode_side_counts = {}
    generated_by_signal_id = {}
    for item in events:
        event_type = str(item.get("type") or item.get("event_type") or "")
        if event_type == "snapshot_rejected":
            reason = str(item.get("reason") or "unknown")
            rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
            decision_funnel["snapshots_rejected"] += 1
            matched_gate = _classify_rejection_gate(reason)
            gate_kill_breakdown[matched_gate] += 1
            session_bucket = str(item.get("session_bucket") or "UNKNOWN")
            session_map = gate_session_matrix.setdefault(matched_gate, {})
            session_map[session_bucket] = session_map.get(session_bucket, 0) + 1
        if event_type == "signal_generated_from_snapshot":
            generated_signals.append(item)
            decision_funnel["signals_generated"] += 1
            try:
                toxicity_score = float(item.get("market_toxicity_score") or 0.0)
            except Exception:
                toxicity_score = 0.0
            market_context = item.get("market_context") if isinstance(item.get("market_context"), dict) else {}
            geometry_sl_mult = market_context.get("geometry_market_mode_sl_mult")
            geometry_tp_mult = market_context.get("geometry_market_mode_tp_mult")
            side = str(item.get("side") or "UNKNOWN").upper()
            market_mode = str(item.get("market_mode") or market_context.get("market_mode") or "UNKNOWN").upper()
            if geometry_sl_mult is not None:
                sl_key = f"{float(geometry_sl_mult):.2f}"
                geometry_market_mode_sl_mult_counts[sl_key] = geometry_market_mode_sl_mult_counts.get(sl_key, 0) + 1
                side_key = f"{market_mode}|{side}|SL|{sl_key}"
                geometry_market_mode_side_counts[side_key] = geometry_market_mode_side_counts.get(side_key, 0) + 1
            if geometry_tp_mult is not None:
                tp_key = f"{float(geometry_tp_mult):.2f}"
                geometry_market_mode_tp_mult_counts[tp_key] = geometry_market_mode_tp_mult_counts.get(tp_key, 0) + 1
                side_key = f"{market_mode}|{side}|TP|{tp_key}"
                geometry_market_mode_side_counts[side_key] = geometry_market_mode_side_counts.get(side_key, 0) + 1
            if toxicity_score < 0.2:
                market_toxicity_histogram["0.00-0.19"] += 1
            elif toxicity_score < 0.4:
                market_toxicity_histogram["0.20-0.39"] += 1
            elif toxicity_score < 0.6:
                market_toxicity_histogram["0.40-0.59"] += 1
            elif toxicity_score < 0.8:
                market_toxicity_histogram["0.60-0.79"] += 1
            else:
                market_toxicity_histogram["0.80-1.00"] += 1
            signal_id = str(item.get("signal_id") or "")
            if signal_id:
                generated_by_signal_id[signal_id] = item
        if event_type == "execution_report":
            executions.append(item)
            report_kind = str(item.get("type") or "").upper()
            if report_kind == "OPEN":
                decision_funnel["executions_opened"] += 1
            elif report_kind in {"CLOSE", "CLOSED", "EXIT"}:
                decision_funnel["executions_closed"] += 1
            outcome = str(item.get("outcome") or item.get("result") or "").upper()
            exit_reason = str(item.get("exit_reason") or "UNKNOWN_EXIT").upper()
            if outcome:
                outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1
                if outcome in {"WIN", "TP", "TAKE_PROFIT", "POSITIVE"}:
                    decision_funnel["wins"] += 1
                elif outcome in {"LOSS", "SL", "STOP_LOSS", "NEGATIVE"}:
                    decision_funnel["losses"] += 1
                elif outcome in {"BREAKEVEN", "BE"}:
                    decision_funnel["breakevens"] += 1
            exit_reason_counts[exit_reason] = exit_reason_counts.get(exit_reason, 0) + 1
            signal_id = str(item.get("signal_id") or "")
            source = generated_by_signal_id.get(signal_id)
            if source:
                side = str(source.get("side") or "unknown")
                structure_reason = str(source.get("structure_reason") or source.get("recent_structure") or source.get("pattern_structure_reason") or "unknown_structure")
                trend_reason = str(source.get("trend_regime_reason") or source.get("pattern_trend_regime_reason") or "unknown_trend")
                session_bucket = str(source.get("session_bucket") or "UNKNOWN")
                quality_tier = str(source.get("quality_tier") or "UNKNOWN")
                keys = [
                    f"side:{side}",
                    f"structure:{structure_reason}",
                    f"trend:{trend_reason}",
                    f"combo:{side}|{structure_reason}|{trend_reason}",
                    f"session:{session_bucket}",
                    f"session_side:{session_bucket}|{side}",
                    f"quality_tier:{quality_tier}",
                    f"session_quality:{session_bucket}|{quality_tier}",
                    f"exit:{exit_reason}",
                    f"session_exit:{session_bucket}|{exit_reason}",
                ]
                is_loss = outcome in {"LOSS", "SL", "STOP_LOSS", "NEGATIVE"}
                is_win = outcome in {"WIN", "TP", "TAKE_PROFIT", "POSITIVE", "BREAKEVEN", "BE"}
                if is_loss or is_win:
                    for key in keys:
                        bucket = reason_stats.setdefault(key, {"trades": 0, "losses": 0, "wins": 0})
                        bucket["trades"] += 1
                        if is_loss:
                            bucket["losses"] += 1
                        if is_win:
                            bucket["wins"] += 1
        if item.get("level") == "error" or event_type in {"error", "snapshot_worker_error"}:
            recent_errors.append(item)
    top_rejections = [
        {"reason": reason, "count": count}
        for reason, count in sorted(rejection_counts.items(), key=lambda kv: kv[1], reverse=True)[:10]
    ]
    top_reason_loss_rates = []
    for key, stat in reason_stats.items():
        trades = int(stat.get("trades", 0) or 0)
        losses = int(stat.get("losses", 0) or 0)
        wins = int(stat.get("wins", 0) or 0)
        loss_rate = (losses / trades) if trades > 0 else 0.0
        top_reason_loss_rates.append({"key": key, "trades": trades, "losses": losses, "wins": wins, "loss_rate": round(loss_rate, 4)})
    top_reason_loss_rates = sorted(top_reason_loss_rates, key=lambda x: (x["loss_rate"], x["trades"]), reverse=True)[:15]
    SNAPSHOT_STATE["reason_outcome_scores"] = reason_stats
    top_exit_reasons = [
        {"exit_reason": reason, "count": count}
        for reason, count in sorted(exit_reason_counts.items(), key=lambda kv: kv[1], reverse=True)[:10]
    ]
    top_outcomes = [
        {"outcome": outcome, "count": count}
        for outcome, count in sorted(outcome_counts.items(), key=lambda kv: kv[1], reverse=True)[:10]
    ]
    top_block_reasons = [
        {"reason": reason, "count": count}
        for reason, count in sorted(
            {k: v for k, v in rejection_counts.items() if str(k).startswith("session_hard_block:") or str(k).startswith("market_toxicity_block:") or str(k).startswith("quality_tier_block:")}.items(),
            key=lambda kv: kv[1],
            reverse=True,
        )[:10]
    ]
    top_session_quality_loss_rates = [
        {"key": item["key"], "trades": item["trades"], "losses": item["losses"], "wins": item["wins"], "loss_rate": item["loss_rate"]}
        for item in top_reason_loss_rates
        if str(item.get("key") or "").startswith("session:") or str(item.get("key") or "").startswith("quality_tier:") or str(item.get("key") or "").startswith("session_quality:")
    ][:15]
    return {
        "decision_funnel": decision_funnel,
        "gate_kill_breakdown": gate_kill_breakdown,
        "gate_session_matrix": {
            gate: dict(sorted(session_map.items(), key=lambda kv: kv[1], reverse=True))
            for gate, session_map in sorted(
                gate_session_matrix.items(),
                key=lambda kv: sum(kv[1].values()),
                reverse=True,
            )
        },
        "top_rejection_reasons": top_rejections,
        "top_reason_loss_rates": top_reason_loss_rates,
        "top_exit_reasons": top_exit_reasons,
        "top_outcomes": top_outcomes,
        "top_block_reasons": top_block_reasons,
        "top_session_quality_loss_rates": top_session_quality_loss_rates,
        "market_toxicity_histogram": market_toxicity_histogram,
        "geometry_market_mode_sl_mult_counts": dict(sorted(geometry_market_mode_sl_mult_counts.items(), key=lambda kv: kv[1], reverse=True)),
        "geometry_market_mode_tp_mult_counts": dict(sorted(geometry_market_mode_tp_mult_counts.items(), key=lambda kv: kv[1], reverse=True)),
        "geometry_market_mode_side_counts": dict(sorted(geometry_market_mode_side_counts.items(), key=lambda kv: kv[1], reverse=True)[:20]),
        "recent_executions": executions[:10],
        "recent_generated_signals": generated_signals[:10],
        "recent_errors": recent_errors[:10],
        "journal_events_scanned": len(events),
    }


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
    strategy = _strategy_summary()
    queue = _queue_summary()
    return {
        "ok": True,
        "service": "xauusd-mt4-bridge",
        "ready": STARTUP_STATUS.get("ready", False),
        "checked_at": STARTUP_STATUS.get("checked_at"),
        "snapshot_queue": {
            "queue_size": queue.get("size"),
            "last_received_at": queue.get("last_received_at"),
            "last_processed_at": queue.get("last_processed_at"),
            "last_signal_id": strategy.get("last_signal_id"),
            "last_decision": strategy.get("last_decision"),
            "last_reason": strategy.get("last_reason"),
            "last_decision_source": strategy.get("last_decision_source"),
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
    return {
        "ok": True,
        "service": "xauusd-mt4-bridge",
        "ready": STARTUP_STATUS.get("ready", False),
        "checked_at": STARTUP_STATUS.get("checked_at"),
        "queue": _queue_summary(),
        "strategy": _strategy_summary(),
        "risk": _risk_state_summary(),
        "current_signal": _current_signal_summary(),
        "news": _news_summary(),
        "ai4trade": {
            "enabled": bool(AI4TRADE_TOKEN),
            "last_fetch_at": AI4TRADE_STATE.get("last_fetch_at"),
            "last_signal_count": AI4TRADE_STATE.get("last_signal_count"),
            "last_selected": AI4TRADE_STATE.get("last_selected"),
            "last_error": AI4TRADE_STATE.get("last_error"),
        },
        "gemini": get_gemini_runtime_state(),
        "risk_config": _effective_risk_config(),
        "runtime_restore": {
            "restored": STARTUP_STATUS.get("runtime_state_restored"),
            "source": STARTUP_STATUS.get("runtime_state_source"),
            "saved_at": STARTUP_STATUS.get("runtime_state_saved_at"),
            "error": STARTUP_STATUS.get("runtime_state_error"),
        },
    }


@app.post("/market/snapshot")
async def receive_snapshot(batch: SnapshotBatch, authorization: Optional[str] = Header(default=None)):
    _check_token(authorization)
    batch = SnapshotBatch.model_validate(upgrade_snapshot_batch_payload(batch.model_dump()))
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
        item["runtime_state"] = {
            "last_loss_side": SNAPSHOT_STATE.get("last_loss_side"),
            "last_loss_at": SNAPSHOT_STATE.get("last_loss_at"),
            "consecutive_losses": SNAPSHOT_STATE.get("consecutive_losses", {"BUY": 0, "SELL": 0}),
            "last_trade_outcome": SNAPSHOT_STATE.get("last_trade_outcome"),
            "recent_loss_patterns": SNAPSHOT_STATE.get("recent_loss_patterns", []),
            "reason_outcome_scores": SNAPSHOT_STATE.get("reason_outcome_scores", {}),
            "slippage_cooldown_until": SNAPSHOT_STATE.get("slippage_cooldown_until"),
            "recent_slippage_events": SNAPSHOT_STATE.get("recent_slippage_events", []),
        }
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
    _save_runtime_state()
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
    summary = _news_summary()
    return {
        "ok": True,
        "news_blocked": summary.get("blocked"),
        "active_news": summary.get("active"),
        "news_updated_at": summary.get("updated_at"),
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


@app.get("/audit/summary")
def audit_summary(limit: int = 200, authorization: Optional[str] = Header(default=None)):
    _check_token(authorization)
    safe_limit = max(20, min(limit, 500))
    return {
        "ok": True,
        "limit": safe_limit,
        "summary": _audit_summary(limit=safe_limit),
    }


@app.post("/signal")
def publish_signal(signal: Signal, authorization: Optional[str] = Header(default=None)):
    _check_token(authorization)
    signal = Signal.model_validate(upgrade_signal_payload(signal.model_dump()))
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


def _build_bridge_contract(data: dict):
    return build_bridge_contract(data)


def _signal_staleness(data: dict):
    return signal_staleness(data)


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
    stale = _signal_staleness(data)
    bridge_contract = _build_bridge_contract(data)
    if stale.get("is_stale"):
        return {
            "ok": True,
            "signal": None,
            "bridge_contract": None,
            "news_blocked": news_blocked,
            "active_news": active_news,
            "news_updated_at": NEWS_CACHE.get("updated_at"),
            "stale_signal_dropped": True,
            "stale_age_sec": stale.get("signal_age_sec"),
        }
    return {"ok": True, "signal": data, "bridge_contract": bridge_contract, "news_blocked": news_blocked, "active_news": active_news, "news_updated_at": NEWS_CACHE.get("updated_at"), "stale_signal_dropped": False, "stale_age_sec": stale.get("signal_age_sec")}


@app.get("/contract/status")
def contract_status(authorization: Optional[str] = Header(default=None)):
    _check_token(authorization)
    active_news = get_active_news_event(DEFAULT_NEWS_BLOCK_MINUTES)
    news_blocked = active_news is not None
    if not os.path.exists(SIGNAL_STORE):
        return {"ok": True, "signal_present": False, "bridge_contract": None, "validation": {"valid": False, "missing": ["signal"]}, "news_blocked": news_blocked, "active_news": active_news}
    with open(SIGNAL_STORE, "r", encoding="utf-8") as f:
        data = json.load(f)
    block_minutes = data.get("market_context", {}).get("news_block_minutes", DEFAULT_NEWS_BLOCK_MINUTES)
    active_news = get_active_news_event(block_minutes)
    news_blocked = active_news is not None
    bridge_contract = _build_bridge_contract(data)
    required_fields = [
        "signal_id", "symbol", "side", "timestamp_utc", "stop_loss",
        "entry_zone_min", "entry_zone_max", "tp1_price", "max_signal_age_sec"
    ]
    missing = [field for field in required_fields if bridge_contract.get(field) in (None, "")]
    issues = []
    stale = _signal_staleness(data)
    signal_age_sec = stale.get("signal_age_sec")
    is_stale = stale.get("is_stale")
    if stale.get("issue"):
        issues.append(stale.get("issue"))

    try:
        entry_min = float(bridge_contract.get("entry_zone_min")) if bridge_contract.get("entry_zone_min") is not None else None
        entry_max = float(bridge_contract.get("entry_zone_max")) if bridge_contract.get("entry_zone_max") is not None else None
        stop_loss = float(bridge_contract.get("stop_loss")) if bridge_contract.get("stop_loss") is not None else None
        tp1_price = float(bridge_contract.get("tp1_price")) if bridge_contract.get("tp1_price") is not None else None
        side = str(bridge_contract.get("side") or "")
        if entry_min is not None and entry_max is not None and entry_min > entry_max:
            issues.append("entry_zone_inverted")
        if side == "BUY":
            if stop_loss is not None and entry_min is not None and stop_loss >= entry_min:
                issues.append("buy_stop_loss_not_below_entry")
            if tp1_price is not None and entry_max is not None and tp1_price <= entry_max:
                issues.append("buy_tp1_not_above_entry")
        elif side == "SELL":
            if stop_loss is not None and entry_max is not None and stop_loss <= entry_max:
                issues.append("sell_stop_loss_not_above_entry")
            if tp1_price is not None and entry_min is not None and tp1_price >= entry_min:
                issues.append("sell_tp1_not_below_entry")
    except Exception:
        issues.append("geometry_validation_error")

    validation = {
        "valid": len(missing) == 0 and len(issues) == 0 and not bool(is_stale),
        "missing": missing,
        "issues": issues,
        "signal_age_sec": signal_age_sec,
        "is_stale": is_stale,
        "trailing_contract_present": any(bridge_contract.get(field) is not None for field in [
            "break_even_r_mult", "break_even_buffer_r_mult", "trailing_start_r_mult", "trailing_step_r_mult", "trailing_sl_r_mult"
        ]),
        "trailing_enabled": bridge_contract.get("trailing_enabled"),
    }
    return {"ok": True, "signal_present": True, "status": data.get("status"), "news_blocked": news_blocked, "active_news": active_news, "bridge_contract": bridge_contract, "validation": validation}


@app.post("/execution/reject")
def execution_reject(payload: dict, authorization: Optional[str] = Header(default=None)):
    _check_token(authorization)
    payload = upgrade_execution_reject_payload(payload)
    event = apply_execution_reject(SNAPSHOT_STATE, payload, _save_runtime_state)
    _append_journal(event)
    return {"ok": True}


@app.post("/notify/test")
async def notify_test(payload: Optional[dict] = None, authorization: Optional[str] = Header(default=None)):
    _check_token(authorization)
    test_message = (payload or {}).get("message") if isinstance(payload, dict) else None
    text = test_message or "✅ Test notification from xau_mt4_bridge"
    await _send_telegram_message(text)
    return {
        "ok": True,
        "telegram_notify_enabled": TELEGRAM_NOTIFY_ENABLED,
        "telegram_chat_id": TELEGRAM_CHAT_ID,
        "bot_token_present": bool(TELEGRAM_BOT_TOKEN),
        "message": text,
    }


@app.post("/execution/report")
def execution_report(payload: dict, authorization: Optional[str] = Header(default=None)):
    _check_token(authorization)
    payload = upgrade_execution_report_payload(payload)
    current_signal = _load_current_signal()
    event, current_signal = apply_execution_report(
        snapshot_state=SNAPSHOT_STATE,
        payload=payload,
        current_signal=current_signal,
        store_signal_payload=_store_signal_payload,
        save_runtime_state=_save_runtime_state,
        parse_iso_utc_fn=_parse_iso_utc,
        session_bucket_cooldown_enabled=SESSION_BUCKET_COOLDOWN_ENABLED,
        session_bucket_cooldown_threshold=SESSION_BUCKET_COOLDOWN_THRESHOLD,
        session_bucket_cooldown_sec=SESSION_BUCKET_COOLDOWN_SEC,
        slippage_cooldown_enabled=SLIPPAGE_COOLDOWN_ENABLED,
        slippage_cooldown_window_sec=SLIPPAGE_COOLDOWN_WINDOW_SEC,
        slippage_cooldown_sec=SLIPPAGE_COOLDOWN_SEC,
    )
    _append_journal(event)

    notify_text = _format_execution_notification(payload, current_signal if isinstance(current_signal, dict) else None)
    if notify_text:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_send_telegram_message(notify_text))
        except RuntimeError:
            asyncio.run(_send_telegram_message(notify_text))

    return {"ok": True}
