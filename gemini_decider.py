import json
import os
import shutil
import subprocess
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(__file__)
load_dotenv(os.path.join(BASE_DIR, ".env"))

ALLOWED_SYMBOLS = {s.strip().upper() for s in os.getenv("AI4TRADE_ALLOWED_SYMBOLS", "XAUUSD,GBPUSD,EURUSD").split(",") if s.strip()}
SYMBOL_ALIASES = {
    "GOLD": "XAUUSD",
}
GEMINI_ENABLED = os.getenv("GEMINI_DECIDER_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
GEMINI_MODEL = os.getenv("GEMINI_DECIDER_MODEL", "gemini-2.5-flash")
XAU_MAX_SPREAD = int(os.getenv("XAU_MAX_SPREAD_POINTS", "120"))
FOREX_MAX_SPREAD = int(os.getenv("FOREX_MAX_SPREAD_POINTS", "35"))
MIN_CONFIDENCE = float(os.getenv("GEMINI_MIN_CONFIDENCE", "0.55"))
GEMINI_DEBUG = os.getenv("GEMINI_DEBUG", "true").lower() in {"1", "true", "yes", "on"}
SESSION_FILTER_ENABLED = os.getenv("SESSION_FILTER_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
SESSION_START_HOUR_UTC = int(os.getenv("SESSION_START_HOUR_UTC", "6"))
SESSION_END_HOUR_UTC = int(os.getenv("SESSION_END_HOUR_UTC", "21"))
XAU_MIN_CANDLE_RANGE = float(os.getenv("XAU_MIN_CANDLE_RANGE", "0.8"))
XAU_MAX_CANDLE_RANGE = float(os.getenv("XAU_MAX_CANDLE_RANGE", "8.0"))
FOREX_MIN_CANDLE_RANGE = float(os.getenv("FOREX_MIN_CANDLE_RANGE", "0.0005"))
FOREX_MAX_CANDLE_RANGE = float(os.getenv("FOREX_MAX_CANDLE_RANGE", "0.0080"))


def normalize_symbol(symbol: str) -> str:
    return SYMBOL_ALIASES.get((symbol or "").upper(), (symbol or "").upper())


def get_max_spread(symbol: str) -> int:
    return XAU_MAX_SPREAD if symbol == "XAUUSD" else FOREX_MAX_SPREAD


def _extract_recent_candles(snapshot: dict):
    candles = snapshot.get("recent_candles") or []
    if not isinstance(candles, list):
        return []
    clean = []
    for item in candles:
        if not isinstance(item, dict):
            continue
        try:
            clean.append({
                "shift": int(item.get("shift", 0)),
                "open": float(item["open"]),
                "high": float(item["high"]),
                "low": float(item["low"]),
                "close": float(item["close"]),
                "volume": float(item.get("volume", 0)),
            })
        except Exception:
            continue
    return clean


def _candle_direction(candle: dict):
    if candle["close"] > candle["open"]:
        return "BUY"
    if candle["close"] < candle["open"]:
        return "SELL"
    return "FLAT"


def _session_gate(snapshot: dict):
    if not SESSION_FILTER_ENABLED:
        return {"pass": True, "reason": "session_filter_disabled"}
    ts = snapshot.get("timestamp_utc")
    if not ts:
        return {"pass": True, "reason": "session_timestamp_missing"}
    try:
        dt = __import__("datetime").datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        hour = dt.hour
    except Exception:
        return {"pass": True, "reason": "session_timestamp_invalid"}
    if SESSION_START_HOUR_UTC <= hour < SESSION_END_HOUR_UTC:
        return {"pass": True, "reason": f"session_ok:{hour}"}
    return {"pass": False, "reason": f"outside_session:{hour}"}


def _volatility_gate(snapshot: dict):
    symbol = normalize_symbol(snapshot["symbol"])
    high = float(snapshot["ohlc"]["high"])
    low = float(snapshot["ohlc"]["low"])
    candle_range = max(high - low, 0.0)
    if symbol == "XAUUSD":
        min_range = XAU_MIN_CANDLE_RANGE
        max_range = XAU_MAX_CANDLE_RANGE
    else:
        min_range = FOREX_MIN_CANDLE_RANGE
        max_range = FOREX_MAX_CANDLE_RANGE
    if candle_range < min_range:
        return {"pass": False, "reason": f"range_too_small:{candle_range:.5f}<{min_range}"}
    if candle_range > max_range:
        return {"pass": False, "reason": f"range_too_large:{candle_range:.5f}>{max_range}"}
    return {"pass": True, "reason": f"range_ok:{candle_range:.5f}"}


def _recent_structure_gate(snapshot: dict):
    candles = _extract_recent_candles(snapshot)
    if len(candles) < 3:
        return {"pass": True, "reason": "recent_candles_insufficient"}

    latest = candles[0]
    latest_range = max(latest["high"] - latest["low"], 0.00001)
    latest_body = abs(latest["close"] - latest["open"])
    body_ratio = latest_body / latest_range
    if body_ratio < 0.2:
        return {"pass": False, "reason": f"weak_last_candle:{body_ratio:.2f}"}

    directions = [_candle_direction(c) for c in candles[:3]]
    buy_count = len([d for d in directions if d == "BUY"])
    sell_count = len([d for d in directions if d == "SELL"])
    if buy_count >= 2:
        return {"pass": True, "bias": "BUY", "reason": "recent_structure_buy"}
    if sell_count >= 2:
        return {"pass": True, "bias": "SELL", "reason": "recent_structure_sell"}
    return {"pass": False, "reason": "mixed_recent_structure"}


def prefilter(snapshot: dict):
    bid = float(snapshot["bid"])
    ask = float(snapshot["ask"])
    close = float(snapshot["ohlc"]["close"])
    open_ = float(snapshot["ohlc"]["open"])
    spread = int(snapshot.get("spread_points", 999))
    symbol = normalize_symbol(snapshot["symbol"])

    if symbol not in ALLOWED_SYMBOLS:
        return {"pass": False, "reason": "symbol_not_allowed"}
    if spread > get_max_spread(symbol):
        return {"pass": False, "reason": f"spread_too_high:{spread}>{get_max_spread(symbol)}"}

    session = _session_gate(snapshot)
    if not session["pass"]:
        return {"pass": False, "reason": session["reason"]}

    volatility = _volatility_gate(snapshot)
    if not volatility["pass"]:
        return {"pass": False, "reason": volatility["reason"]}

    if close > open_:
        bias = "BUY"
    elif close < open_:
        bias = "SELL"
    else:
        return {"pass": False, "reason": "flat_candle"}

    structure = _recent_structure_gate(snapshot)
    if not structure["pass"]:
        return {"pass": False, "reason": structure["reason"]}
    if structure.get("bias") and structure["bias"] != bias:
        return {"pass": False, "reason": f"bias_conflict:{bias}_vs_{structure['bias']}"}

    entry = round((bid + ask) / 2.0, 5 if symbol != "XAUUSD" else 2)
    return {
        "pass": True,
        "bias": bias,
        "entry": entry,
        "reason": f"basic_candle_bias|{session['reason']}|{volatility['reason']}|{structure['reason']}",
        "recent_structure": structure['reason'],
        "recent_candles_used": len(_extract_recent_candles(snapshot)),
        "session_reason": session['reason'],
        "volatility_reason": volatility['reason'],
    }


def decide_with_mock_gemini(snapshot: dict):
    pf = prefilter(snapshot)
    if not pf["pass"]:
        return {"decision": "NO_TRADE", "confidence": 0.0, "reason": pf["reason"]}
    return {
        "decision": pf["bias"],
        "confidence": 0.6,
        "reason": pf["reason"],
        "entry": pf["entry"],
        "symbol": normalize_symbol(snapshot["symbol"]),
        "timeframe": snapshot.get("timeframe", "M1"),
    }


def _gemini_prompt(snapshot: dict, pf: dict) -> str:
    normalized = normalize_symbol(snapshot["symbol"])
    payload = {
        "symbol": normalized,
        "timeframe": snapshot.get("timeframe", "M1"),
        "bid": snapshot.get("bid"),
        "ask": snapshot.get("ask"),
        "spread_points": snapshot.get("spread_points"),
        "ohlc": snapshot.get("ohlc"),
        "volume": snapshot.get("volume"),
        "recent_candles": snapshot.get("recent_candles", []),
        "prefilter": pf,
    }
    return (
        "You are a trading signal classifier for short-term MT4 execution. "
        "Given the market snapshot JSON, return ONLY valid JSON with keys: decision, confidence, reason, entry, symbol, timeframe. "
        "decision must be one of BUY, SELL, NO_TRADE. confidence must be 0..1. "
        "If unsure, return NO_TRADE. Use the provided prefilter bias as a hint, not a rule. "
        f"Snapshot: {json.dumps(payload, ensure_ascii=False)}"
    )


def _debug(message: str):
    if GEMINI_DEBUG:
        print(f"[gemini_decider] {message}")


def _try_decide_with_gemini(snapshot: dict, pf: dict):
    if not GEMINI_ENABLED:
        _debug("Gemini disabled by config, using fallback")
        return None
    gemini_bin = shutil.which("gemini")
    if not gemini_bin:
        _debug("Gemini CLI not found, using fallback")
        return None
    prompt = _gemini_prompt(snapshot, pf)
    try:
        result = subprocess.run(
            [gemini_bin, "-m", GEMINI_MODEL, "-p", prompt, "-o", "json"],
            capture_output=True,
            text=True,
            timeout=45,
            cwd=BASE_DIR,
        )
        if result.returncode != 0:
            _debug(f"Gemini CLI failed rc={result.returncode}, stderr={(result.stderr or '').strip()[:300]}")
            return None
        raw = (result.stdout or "").strip()
        if not raw:
            _debug("Gemini returned empty output, using fallback")
            return None
        parsed = json.loads(raw)
        decision = str(parsed.get("decision", "NO_TRADE")).upper()
        confidence = float(parsed.get("confidence", 0.0))
        if decision not in {"BUY", "SELL", "NO_TRADE"}:
            _debug(f"Gemini returned invalid decision={decision}, using fallback")
            return None
        symbol = normalize_symbol(parsed.get("symbol") or snapshot["symbol"])
        timeframe = parsed.get("timeframe") or snapshot.get("timeframe", "M1")
        entry = parsed.get("entry", pf.get("entry"))
        if entry is not None:
            entry = float(entry)
        reason = str(parsed.get("reason") or "gemini_decision")
        if decision in {"BUY", "SELL"} and confidence < MIN_CONFIDENCE:
            _debug(f"Gemini low confidence decision={decision} confidence={confidence}")
            return {
                "decision": "NO_TRADE",
                "confidence": confidence,
                "reason": f"gemini_low_confidence:{reason}",
                "entry": entry,
                "symbol": symbol,
                "timeframe": timeframe,
            }
        _debug(f"Gemini decision used decision={decision} confidence={confidence} reason={reason}")
        return {
            "decision": decision,
            "confidence": confidence,
            "reason": reason,
            "entry": entry,
            "symbol": symbol,
            "timeframe": timeframe,
            "decision_source": "gemini",
        }
    except Exception as e:
        _debug(f"Gemini exception {e}, using fallback")
        return None


def decide_trade(snapshot: dict):
    pf = prefilter(snapshot)
    if not pf["pass"]:
        return {"decision": "NO_TRADE", "confidence": 0.0, "reason": pf["reason"]}
    gemini_result = _try_decide_with_gemini(snapshot, pf)
    if gemini_result is not None:
        if gemini_result.get("entry") is None:
            gemini_result["entry"] = pf["entry"]
        return gemini_result
    fallback = decide_with_mock_gemini(snapshot)
    fallback["decision_source"] = "mock"
    _debug(f"Fallback decision used decision={fallback.get('decision')} reason={fallback.get('reason')}")
    return fallback
