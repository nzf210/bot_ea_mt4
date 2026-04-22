import json
import os
import shutil
import subprocess
import tempfile
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
LATE_ENTRY_RANGE_FACTOR = float(os.getenv("LATE_ENTRY_RANGE_FACTOR", "0.75"))
EXHAUSTION_BODY_RATIO = float(os.getenv("EXHAUSTION_BODY_RATIO", "0.8"))
DETERMINISTIC_SCORE_TRADE_THRESHOLD = float(os.getenv("DETERMINISTIC_SCORE_TRADE_THRESHOLD", "0.58"))
DETERMINISTIC_SCORE_NO_TRADE_THRESHOLD = float(os.getenv("DETERMINISTIC_SCORE_NO_TRADE_THRESHOLD", "0.48"))
GEMINI_OVERRIDE_CONFIDENCE = float(os.getenv("GEMINI_OVERRIDE_CONFIDENCE", "0.72"))
GEMINI_RUNTIME_STATE = {
    "enabled": GEMINI_ENABLED,
    "model": GEMINI_MODEL,
    "binary_found": False,
    "binary_path": None,
    "last_error": None,
    "last_return_code": None,
    "last_decision_source": None,
}


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
    high = float(snapshot["ohlc"]["high"])
    low = float(snapshot["ohlc"]["low"])
    close = float(snapshot["ohlc"]["close"])
    open_ = float(snapshot["ohlc"]["open"])
    spread = int(snapshot.get("spread_points", 999))
    symbol = normalize_symbol(snapshot["symbol"])

    if symbol not in ALLOWED_SYMBOLS:
        return {"pass": False, "reason": "symbol_not_allowed"}
    max_spread = get_max_spread(symbol)
    if spread > max_spread:
        return {"pass": False, "reason": f"spread_too_high:{spread}>{max_spread}"}

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
    candle_range = max(high - low, 0.00001)
    body_ratio = abs(close - open_) / candle_range
    if bias == "BUY":
        late_distance = max(entry - low, 0.0)
    else:
        late_distance = max(high - entry, 0.0)
    late_ratio = late_distance / candle_range
    if late_ratio >= LATE_ENTRY_RANGE_FACTOR:
        return {"pass": False, "reason": f"late_entry:{late_ratio:.2f}"}
    if body_ratio >= EXHAUSTION_BODY_RATIO and late_ratio >= 0.6:
        return {"pass": False, "reason": f"exhaustion_risk:body={body_ratio:.2f},late={late_ratio:.2f}"}

    spread_quality = max(0.0, 1.0 - (spread / max_spread)) if max_spread > 0 else 0.0
    return {
        "pass": True,
        "bias": bias,
        "entry": entry,
        "reason": f"basic_candle_bias|{session['reason']}|{volatility['reason']}|{structure['reason']}",
        "recent_structure": structure['reason'],
        "recent_candles_used": len(_extract_recent_candles(snapshot)),
        "session_reason": session['reason'],
        "volatility_reason": volatility['reason'],
        "spread_quality": round(spread_quality, 4),
        "late_ratio": round(late_ratio, 4),
        "body_ratio": round(body_ratio, 4),
    }


def _score_prefilter_confidence(snapshot: dict, pf: dict) -> float:
    confidence = 0.5
    reason = str(pf.get("reason", ""))
    if "recent_structure_buy" in reason or "recent_structure_sell" in reason:
        confidence += 0.08
    if "range_ok:" in reason:
        confidence += 0.05

    spread_quality = float(pf.get("spread_quality", 0.0))
    confidence += min(max(spread_quality, 0.0), 1.0) * 0.1

    late_ratio = float(pf.get("late_ratio", 1.0))
    confidence += max(0.0, (1.0 - late_ratio)) * 0.08

    body_ratio = float(pf.get("body_ratio", 0.0))
    if 0.25 <= body_ratio <= 0.7:
        confidence += 0.07
    elif body_ratio > 0.85:
        confidence -= 0.08

    candles = _extract_recent_candles(snapshot)
    if len(candles) >= 3:
        same_dir = [_candle_direction(c) for c in candles[:3]]
        if len(set(same_dir)) == 1 and "FLAT" not in same_dir:
            confidence += 0.1
        elif len(set(same_dir)) == 2:
            confidence -= 0.04

    return max(0.0, min(confidence, 0.85))


def _deterministic_score(snapshot: dict, pf: dict) -> float:
    score = _score_prefilter_confidence(snapshot, pf)
    spread_quality = float(pf.get("spread_quality", 0.0))
    late_ratio = float(pf.get("late_ratio", 1.0))
    body_ratio = float(pf.get("body_ratio", 0.0))
    score += spread_quality * 0.06
    score += max(0.0, 1.0 - late_ratio) * 0.05
    if 0.3 <= body_ratio <= 0.7:
        score += 0.03
    elif body_ratio > 0.85:
        score -= 0.06
    return max(0.0, min(score, 0.95))


def decide_with_mock_gemini(snapshot: dict):
    pf = prefilter(snapshot)
    if not pf["pass"]:
        return {"decision": "NO_TRADE", "confidence": 0.0, "reason": pf["reason"]}
    score = _deterministic_score(snapshot, pf)
    decision = pf["bias"] if score >= DETERMINISTIC_SCORE_TRADE_THRESHOLD else "NO_TRADE"
    reason = pf["reason"] if decision != "NO_TRADE" else f"deterministic_score_too_low:{score:.2f}|{pf['reason']}"
    return {
        "decision": decision,
        "confidence": score,
        "reason": reason,
        "entry": pf["entry"],
        "symbol": normalize_symbol(snapshot["symbol"]),
        "timeframe": snapshot.get("timeframe", "M1"),
        "deterministic_score": score,
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
        "You are a trading decision assistant for short-term MT4 execution on GOLD/forex. "
        "You must be conservative. Deterministic prefilter has already passed, so your job is to confirm or downgrade setup quality, not invent reckless trades. "
        "Return ONLY valid JSON with keys: decision, confidence, reason, entry, symbol, timeframe, evaluation. "
        "decision must be one of BUY, SELL, NO_TRADE. confidence must be 0..1. entry must be numeric. "
        "evaluation must be an object with optional numeric keys trend_alignment, entry_quality, exhaustion_risk, noise_risk, each in 0..1. "
        "Higher trend_alignment and entry_quality are better. Higher exhaustion_risk and noise_risk are worse. "
        "Prefer NO_TRADE when the setup is weak, stretched, noisy, late, or unclear. "
        "Use recent_candles, volatility, spread, and prefilter reasoning. Avoid contrarian overrides unless confidence is very high and reason is explicit. "
        f"Snapshot: {json.dumps(payload, ensure_ascii=False)}"
    )


def get_gemini_runtime_state():
    gemini_bin = shutil.which("gemini")
    GEMINI_RUNTIME_STATE["enabled"] = GEMINI_ENABLED
    GEMINI_RUNTIME_STATE["model"] = GEMINI_MODEL
    GEMINI_RUNTIME_STATE["binary_found"] = bool(gemini_bin)
    GEMINI_RUNTIME_STATE["binary_path"] = gemini_bin
    state = dict(GEMINI_RUNTIME_STATE)
    state["last_mode"] = state.get("last_decision_source")
    return state


def set_gemini_runtime_state(payload: dict):
    if not isinstance(payload, dict):
        return
    for key in ["enabled", "model", "binary_found", "binary_path", "last_error", "last_return_code", "last_decision_source"]:
        if key in payload:
            GEMINI_RUNTIME_STATE[key] = payload.get(key)


def _debug(message: str):
    if GEMINI_DEBUG:
        print(f"[gemini_decider] {message}")


def _try_decide_with_gemini(snapshot: dict, pf: dict):
    if not GEMINI_ENABLED:
        _debug("Gemini disabled by config, using fallback")
        return None
    gemini_bin = shutil.which("gemini")
    GEMINI_RUNTIME_STATE["binary_found"] = bool(gemini_bin)
    GEMINI_RUNTIME_STATE["binary_path"] = gemini_bin
    if not gemini_bin:
        GEMINI_RUNTIME_STATE["last_error"] = "gemini_cli_not_found"
        GEMINI_RUNTIME_STATE["last_decision_source"] = "fallback"
        _debug("Gemini CLI not found, using fallback")
        return None
    prompt = _gemini_prompt(snapshot, pf)
    prompt_file = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False, dir=BASE_DIR) as f:
            f.write(prompt)
            prompt_file = f.name
        result = subprocess.run(
            [gemini_bin, "-m", GEMINI_MODEL, "-p", "@" + prompt_file, "-o", "json"],
            capture_output=True,
            text=True,
            timeout=45,
            cwd=BASE_DIR,
        )
        GEMINI_RUNTIME_STATE["last_return_code"] = result.returncode
        if result.returncode != 0:
            GEMINI_RUNTIME_STATE["last_error"] = (result.stderr or result.stdout or "gemini_cli_failed").strip()[:300]
            GEMINI_RUNTIME_STATE["last_decision_source"] = "fallback"
            _debug(f"Gemini CLI failed rc={result.returncode}, stderr={(result.stderr or '').strip()[:300]}")
            return None
        raw = (result.stdout or "").strip()
        if not raw:
            GEMINI_RUNTIME_STATE["last_error"] = "gemini_empty_output"
            GEMINI_RUNTIME_STATE["last_decision_source"] = "fallback"
            _debug("Gemini returned empty output, using fallback")
            return None
        parsed = json.loads(raw)
        decision = str(parsed.get("decision", "NO_TRADE")).upper()
        confidence = float(parsed.get("confidence", 0.0))
        if decision not in {"BUY", "SELL", "NO_TRADE"}:
            GEMINI_RUNTIME_STATE["last_error"] = f"gemini_invalid_decision:{decision}"
            GEMINI_RUNTIME_STATE["last_decision_source"] = "fallback"
            _debug(f"Gemini returned invalid decision={decision}, using fallback")
            return None
        symbol = normalize_symbol(parsed.get("symbol") or snapshot["symbol"])
        timeframe = parsed.get("timeframe") or snapshot.get("timeframe", "M1")
        entry = parsed.get("entry", pf.get("entry"))
        if entry is not None:
            entry = float(entry)
        reason = str(parsed.get("reason") or "gemini_decision")
        evaluation = parsed.get("evaluation") if isinstance(parsed.get("evaluation"), dict) else {}
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
        GEMINI_RUNTIME_STATE["last_error"] = None
        GEMINI_RUNTIME_STATE["last_decision_source"] = "gemini"
        _debug(f"Gemini decision used decision={decision} confidence={confidence} reason={reason}")
        result_payload = {
            "decision": decision,
            "confidence": confidence,
            "reason": reason,
            "entry": entry,
            "symbol": symbol,
            "timeframe": timeframe,
            "decision_source": "gemini",
        }
        if evaluation:
            result_payload["evaluation"] = {
                key: max(0.0, min(float(value), 1.0))
                for key, value in evaluation.items()
                if key in {"trend_alignment", "entry_quality", "exhaustion_risk", "noise_risk"}
            }
        return result_payload
    except Exception as e:
        GEMINI_RUNTIME_STATE["last_error"] = str(e)
        GEMINI_RUNTIME_STATE["last_decision_source"] = "fallback"
        _debug(f"Gemini exception {e}, using fallback")
        return None
    finally:
        if prompt_file:
            try:
                os.remove(prompt_file)
            except Exception:
                pass


def decide_trade(snapshot: dict):
    pf = prefilter(snapshot)
    if not pf["pass"]:
        return {"decision": "NO_TRADE", "confidence": 0.0, "reason": pf["reason"], "decision_source": "rule_gate"}

    fallback = decide_with_mock_gemini(snapshot)
    fallback["decision_source"] = "mock"
    deterministic_score = float(fallback.get("deterministic_score", fallback.get("confidence", 0.0)))
    GEMINI_RUNTIME_STATE["last_decision_source"] = "mock"
    gemini_result = _try_decide_with_gemini(snapshot, pf)
    if gemini_result is not None:
        if gemini_result.get("entry") is None:
            gemini_result["entry"] = pf["entry"]
        evaluation = gemini_result.get("evaluation") if isinstance(gemini_result.get("evaluation"), dict) else {}
        fusion_score = deterministic_score
        if evaluation:
            trend_alignment = float(evaluation.get("trend_alignment", 0.5))
            entry_quality = float(evaluation.get("entry_quality", 0.5))
            exhaustion_risk = float(evaluation.get("exhaustion_risk", 0.5))
            noise_risk = float(evaluation.get("noise_risk", 0.5))
            fusion_score = max(0.0, min(0.95, deterministic_score + (trend_alignment * 0.06) + (entry_quality * 0.06) - (exhaustion_risk * 0.05) - (noise_risk * 0.04)))
        gemini_result["fusion_score"] = fusion_score

        if gemini_result.get("decision") == fallback.get("decision"):
            gemini_result["confidence"] = max(float(gemini_result.get("confidence", 0.0)), fusion_score)
            if fusion_score < DETERMINISTIC_SCORE_NO_TRADE_THRESHOLD:
                _debug(f"Hybrid fusion downgraded to NO_TRADE score={fusion_score}")
                return {
                    "decision": "NO_TRADE",
                    "confidence": fusion_score,
                    "reason": f"fusion_score_too_low:{fusion_score:.2f}|{gemini_result.get('reason')}",
                    "entry": gemini_result.get("entry"),
                    "symbol": gemini_result.get("symbol"),
                    "timeframe": gemini_result.get("timeframe"),
                    "decision_source": "fusion",
                    "evaluation": evaluation,
                    "fusion_score": fusion_score,
                }
            _debug(f"Hybrid decision aligned with fallback decision={gemini_result.get('decision')}")
            return gemini_result
        if gemini_result.get("decision") == "NO_TRADE":
            _debug("Hybrid decision downgraded to NO_TRADE by Gemini")
            return gemini_result
        if fusion_score >= GEMINI_OVERRIDE_CONFIDENCE and float(gemini_result.get("confidence", 0.0)) >= MIN_CONFIDENCE:
            gemini_result["reason"] = f"gemini_override|{gemini_result.get('reason')}"
            gemini_result["confidence"] = max(float(gemini_result.get("confidence", 0.0)), fusion_score)
            _debug(f"Hybrid override accepted decision={gemini_result.get('decision')} confidence={gemini_result.get('confidence')}")
            return gemini_result
        _debug("Hybrid override rejected, fallback kept")

    _debug(f"Fallback decision used decision={fallback.get('decision')} reason={fallback.get('reason')}")
    return fallback
