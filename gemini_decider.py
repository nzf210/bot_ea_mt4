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


def normalize_symbol(symbol: str) -> str:
    return SYMBOL_ALIASES.get((symbol or "").upper(), (symbol or "").upper())


def get_max_spread(symbol: str) -> int:
    return XAU_MAX_SPREAD if symbol == "XAUUSD" else FOREX_MAX_SPREAD


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

    if close > open_:
        bias = "BUY"
    elif close < open_:
        bias = "SELL"
    else:
        return {"pass": False, "reason": "flat_candle"}

    entry = round((bid + ask) / 2.0, 5 if symbol != "XAUUSD" else 2)
    return {"pass": True, "bias": bias, "entry": entry, "reason": "basic_candle_bias"}


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
        "prefilter": pf,
    }
    return (
        "You are a trading signal classifier for short-term MT4 execution. "
        "Given the market snapshot JSON, return ONLY valid JSON with keys: decision, confidence, reason, entry, symbol, timeframe. "
        "decision must be one of BUY, SELL, NO_TRADE. confidence must be 0..1. "
        "If unsure, return NO_TRADE. Use the provided prefilter bias as a hint, not a rule. "
        f"Snapshot: {json.dumps(payload, ensure_ascii=False)}"
    )


def _try_decide_with_gemini(snapshot: dict, pf: dict):
    if not GEMINI_ENABLED:
        return None
    gemini_bin = shutil.which("gemini")
    if not gemini_bin:
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
            return None
        raw = (result.stdout or "").strip()
        if not raw:
            return None
        parsed = json.loads(raw)
        decision = str(parsed.get("decision", "NO_TRADE")).upper()
        confidence = float(parsed.get("confidence", 0.0))
        if decision not in {"BUY", "SELL", "NO_TRADE"}:
            return None
        symbol = normalize_symbol(parsed.get("symbol") or snapshot["symbol"])
        timeframe = parsed.get("timeframe") or snapshot.get("timeframe", "M1")
        entry = parsed.get("entry", pf.get("entry"))
        if entry is not None:
            entry = float(entry)
        reason = str(parsed.get("reason") or "gemini_decision")
        if decision in {"BUY", "SELL"} and confidence < MIN_CONFIDENCE:
            return {
                "decision": "NO_TRADE",
                "confidence": confidence,
                "reason": f"gemini_low_confidence:{reason}",
                "entry": entry,
                "symbol": symbol,
                "timeframe": timeframe,
            }
        return {
            "decision": decision,
            "confidence": confidence,
            "reason": reason,
            "entry": entry,
            "symbol": symbol,
            "timeframe": timeframe,
        }
    except Exception:
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
    return decide_with_mock_gemini(snapshot)
