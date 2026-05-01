import json
import os
import httpx
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(__file__)
load_dotenv(os.path.join(BASE_DIR, ".env"))

ALLOWED_SYMBOLS = {s.strip().upper() for s in os.getenv("AI4TRADE_ALLOWED_SYMBOLS", "XAUUSD,GBPUSD,EURUSD").split(",") if s.strip()}
SYMBOL_ALIASES = {
    "GOLD": "XAUUSD",
}
GEMINI_ENABLED = os.getenv("GEMINI_DECIDER_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
GEMINI_MODEL = os.getenv("GEMINI_DECIDER_MODEL", "gemini-2.5-flash")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_API_URL = os.getenv("GEMINI_API_URL", "https://generativelanguage.googleapis.com/v1beta/models")
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
LATE_ENTRY_RANGE_FACTOR = float(os.getenv("LATE_ENTRY_RANGE_FACTOR", "0.55"))
EXHAUSTION_BODY_RATIO = float(os.getenv("EXHAUSTION_BODY_RATIO", "0.72"))
NO_CHASE_CLOSE_EXTREME_RATIO = float(os.getenv("NO_CHASE_CLOSE_EXTREME_RATIO", "0.12"))
MIN_STRUCTURE_BODY_RATIO = float(os.getenv("MIN_STRUCTURE_BODY_RATIO", "0.28"))
STRONG_BODY_RATIO = float(os.getenv("STRONG_BODY_RATIO", "0.45"))
MISALIGNED_STRUCTURE_PENALTY = float(os.getenv("MISALIGNED_STRUCTURE_PENALTY", "0.05"))
MISALIGNED_STRUCTURE_STRONG_BODY_THRESHOLD = float(os.getenv("MISALIGNED_STRUCTURE_STRONG_BODY_THRESHOLD", "0.38"))
INSUFFICIENT_ALIGNMENT_SOFT_PENALTY = float(os.getenv("INSUFFICIENT_ALIGNMENT_SOFT_PENALTY", "0.06"))
INSUFFICIENT_ALIGNMENT_STRONG_BODY_THRESHOLD = float(os.getenv("INSUFFICIENT_ALIGNMENT_STRONG_BODY_THRESHOLD", "0.52"))
TREND_REGIME_MIN_BODY_RATIO = float(os.getenv("TREND_REGIME_MIN_BODY_RATIO", "0.22"))
TREND_REGIME_ALIGNMENT_MIN = int(os.getenv("TREND_REGIME_ALIGNMENT_MIN", "3"))
TREND_REGIME_SCORE_MIN = float(os.getenv("TREND_REGIME_SCORE_MIN", "0.58"))
TREND_REGIME_PULLBACK_TOLERANCE = float(os.getenv("TREND_REGIME_PULLBACK_TOLERANCE", "0.38"))
TREND_REGIME_SOFT_ALIGNMENT_ALLOWED = int(os.getenv("TREND_REGIME_SOFT_ALIGNMENT_ALLOWED", "2"))
TREND_REGIME_SOFT_ALIGNMENT_PENALTY = float(os.getenv("TREND_REGIME_SOFT_ALIGNMENT_PENALTY", "0.06"))
DETERMINISTIC_SCORE_TRADE_THRESHOLD = float(os.getenv("DETERMINISTIC_SCORE_TRADE_THRESHOLD", "0.68"))
DETERMINISTIC_SCORE_NO_TRADE_THRESHOLD = float(os.getenv("DETERMINISTIC_SCORE_NO_TRADE_THRESHOLD", "0.56"))
ADAPTIVE_THRESHOLD_ENABLED = os.getenv("ADAPTIVE_THRESHOLD_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
ADAPTIVE_THRESHOLD_MAX_PENALTY = float(os.getenv("ADAPTIVE_THRESHOLD_MAX_PENALTY", "0.12"))
ADAPTIVE_THRESHOLD_MAX_BONUS = float(os.getenv("ADAPTIVE_THRESHOLD_MAX_BONUS", "0.02"))
GEMINI_OVERRIDE_CONFIDENCE = float(os.getenv("GEMINI_OVERRIDE_CONFIDENCE", "0.80"))
OUTCOME_PENALTY_ENABLED = os.getenv("OUTCOME_PENALTY_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
OUTCOME_PENALTY_MAX = float(os.getenv("OUTCOME_PENALTY_MAX", "0.12"))
OUTCOME_PENALTY_WINDOW_SEC = int(os.getenv("OUTCOME_PENALTY_WINDOW_SEC", "7200"))
OUTCOME_PENALTY_RECENT_LOSS_WEIGHT = float(os.getenv("OUTCOME_PENALTY_RECENT_LOSS_WEIGHT", "0.05"))
OUTCOME_PENALTY_CONSECUTIVE_LOSS_WEIGHT = float(os.getenv("OUTCOME_PENALTY_CONSECUTIVE_LOSS_WEIGHT", "0.03"))
OUTCOME_PENALTY_REVENGE_BLOCK_THRESHOLD = int(os.getenv("OUTCOME_PENALTY_REVENGE_BLOCK_THRESHOLD", "2"))
PATTERN_LOCKOUT_ENABLED = os.getenv("PATTERN_LOCKOUT_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
PATTERN_LOCKOUT_WINDOW_SEC = int(os.getenv("PATTERN_LOCKOUT_WINDOW_SEC", "10800"))
PATTERN_LOCKOUT_THRESHOLD = int(os.getenv("PATTERN_LOCKOUT_THRESHOLD", "2"))
PATTERN_LOCKOUT_PENALTY = float(os.getenv("PATTERN_LOCKOUT_PENALTY", "0.08"))
JOURNAL_REASON_SCORE_ENABLED = os.getenv("JOURNAL_REASON_SCORE_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
JOURNAL_REASON_SCORE_MAX_PENALTY = float(os.getenv("JOURNAL_REASON_SCORE_MAX_PENALTY", "0.10"))
JOURNAL_REASON_SCORE_MIN_TRADES = int(os.getenv("JOURNAL_REASON_SCORE_MIN_TRADES", "3"))
MULTI_PENALTY_CONFIDENCE_CAP_ENABLED = os.getenv("MULTI_PENALTY_CONFIDENCE_CAP_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
MULTI_PENALTY_CONFIDENCE_CAP_THRESHOLD = int(os.getenv("MULTI_PENALTY_CONFIDENCE_CAP_THRESHOLD", "2"))
MULTI_PENALTY_CONFIDENCE_CAP_VALUE = float(os.getenv("MULTI_PENALTY_CONFIDENCE_CAP_VALUE", "0.58"))
AUTO_HARDENING_ENABLED = os.getenv("AUTO_HARDENING_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
AUTO_HARDENING_THRESHOLD = float(os.getenv("AUTO_HARDENING_THRESHOLD", "0.65"))
AUTO_HARDENING_THRESHOLD_BONUS = float(os.getenv("AUTO_HARDENING_THRESHOLD_BONUS", "0.05"))
SESSION_SCORING_ENABLED = os.getenv("SESSION_SCORING_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
SESSION_SCORE_MAX_PENALTY = float(os.getenv("SESSION_SCORE_MAX_PENALTY", "0.08"))
SESSION_SCORE_MIN_TRADES = int(os.getenv("SESSION_SCORE_MIN_TRADES", "3"))
EXIT_REASON_PENALTY_ENABLED = os.getenv("EXIT_REASON_PENALTY_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
EXIT_REASON_PENALTY_MAX = float(os.getenv("EXIT_REASON_PENALTY_MAX", "0.08"))
EXIT_REASON_PENALTY_MIN_TRADES = int(os.getenv("EXIT_REASON_PENALTY_MIN_TRADES", "3"))
EXIT_REASON_HARD_BLOCK_THRESHOLD = float(os.getenv("EXIT_REASON_HARD_BLOCK_THRESHOLD", "0.85"))
MARKET_TOXICITY_ENABLED = os.getenv("MARKET_TOXICITY_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
MARKET_TOXICITY_PENALTY_MAX = float(os.getenv("MARKET_TOXICITY_PENALTY_MAX", "0.08"))
MARKET_TOXICITY_HARD_BLOCK_THRESHOLD = float(os.getenv("MARKET_TOXICITY_HARD_BLOCK_THRESHOLD", "0.85"))
SESSION_HARD_BLOCK_ENABLED = os.getenv("SESSION_HARD_BLOCK_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
SESSION_HARD_BLOCK_MIN_TRADES = int(os.getenv("SESSION_HARD_BLOCK_MIN_TRADES", "4"))
SESSION_HARD_BLOCK_LOSS_RATE = float(os.getenv("SESSION_HARD_BLOCK_LOSS_RATE", "0.80"))
QUALITY_TIERING_ENABLED = os.getenv("QUALITY_TIERING_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
QUALITY_TIER_A_MIN = float(os.getenv("QUALITY_TIER_A_MIN", "0.78"))
QUALITY_TIER_B_MIN = float(os.getenv("QUALITY_TIER_B_MIN", "0.68"))
QUALITY_TIER_C_BLOCK_ENABLED = os.getenv("QUALITY_TIER_C_BLOCK_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
MARKET_MODE_ENABLED = os.getenv("MARKET_MODE_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
MARKET_MODE_QUIET_RANGE_FACTOR = float(os.getenv("MARKET_MODE_QUIET_RANGE_FACTOR", "0.85"))
MARKET_MODE_TOXIC_SPREAD_FACTOR = float(os.getenv("MARKET_MODE_TOXIC_SPREAD_FACTOR", "0.75"))
MARKET_MODE_TRENDING_ALIGNMENT_MIN = int(os.getenv("MARKET_MODE_TRENDING_ALIGNMENT_MIN", "4"))
MARKET_MODE_THRESHOLD_BONUS_MAX = float(os.getenv("MARKET_MODE_THRESHOLD_BONUS_MAX", "0.05"))
MARKET_MODE_TRENDING_LATE_ENTRY_BONUS = float(os.getenv("MARKET_MODE_TRENDING_LATE_ENTRY_BONUS", "0.08"))
MARKET_MODE_TRENDING_THRESHOLD_BONUS = float(os.getenv("MARKET_MODE_TRENDING_THRESHOLD_BONUS", "0.015"))
MARKET_MODE_TRENDING_B_TIER_MAX_PENALTIES = int(os.getenv("MARKET_MODE_TRENDING_B_TIER_MAX_PENALTIES", "2"))
GEMINI_RUNTIME_STATE = {
    "enabled": GEMINI_ENABLED,
    "model": GEMINI_MODEL,
    "api_configured": bool(GEMINI_API_KEY),
    "binary_found": False,
    "binary_path": None,
    "last_error": None,
    "last_return_code": None,
    "last_http_status": None,
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


def _market_mode(snapshot: dict):
    if not MARKET_MODE_ENABLED:
        return {"mode": "DISABLED", "threshold_bonus": 0.0, "confidence_penalty": 0.0, "reason": "market_mode_disabled"}
    candles = _extract_recent_candles(snapshot)
    symbol = normalize_symbol(snapshot.get("symbol"))
    spread_points = float(snapshot.get("spread_points") or 0.0)
    max_spread = float(get_max_spread(symbol) or 1.0)
    spread_factor = min(max(spread_points / max_spread, 0.0), 2.0)
    if not candles:
        return {"mode": "UNKNOWN", "threshold_bonus": 0.0, "confidence_penalty": 0.0, "reason": "market_mode_no_candles"}

    ranges = [max(float(c["high"]) - float(c["low"]), 0.0) for c in candles[:5]]
    avg_range = sum(ranges) / max(len(ranges), 1)
    current_range = ranges[0] if ranges else 0.0
    body_ratios = []
    directions = []
    for candle in candles[:5]:
        candle_range = max(candle["high"] - candle["low"], 0.00001)
        body_ratios.append(abs(candle["close"] - candle["open"]) / candle_range)
        directions.append(_candle_direction(candle))
    avg_body_ratio = sum(body_ratios) / max(len(body_ratios), 1)
    dominant_dir = max(["BUY", "SELL", "FLAT"], key=lambda d: directions.count(d))
    directional_consistency = directions.count(dominant_dir) / max(len(directions), 1)

    if spread_factor >= MARKET_MODE_TOXIC_SPREAD_FACTOR:
        return {"mode": "TOXIC", "threshold_bonus": MARKET_MODE_THRESHOLD_BONUS_MAX, "confidence_penalty": 0.08, "reason": f"spread_factor={spread_factor:.2f}"}
    if avg_range > 0 and current_range <= avg_range * MARKET_MODE_QUIET_RANGE_FACTOR and avg_body_ratio < 0.38:
        return {"mode": "QUIET", "threshold_bonus": 0.01, "confidence_penalty": 0.02, "reason": f"range={current_range:.2f}|avg={avg_range:.2f}|body={avg_body_ratio:.2f}"}
    if directional_consistency >= 0.8 and directions.count(dominant_dir) >= MARKET_MODE_TRENDING_ALIGNMENT_MIN and avg_body_ratio >= 0.45:
        return {"mode": "TRENDING", "threshold_bonus": -0.02, "confidence_penalty": 0.0, "reason": f"dir={dominant_dir}|consistency={directional_consistency:.2f}|body={avg_body_ratio:.2f}"}
    if avg_body_ratio < 0.33 and directional_consistency < 0.6:
        return {"mode": "CHOPPY", "threshold_bonus": 0.03, "confidence_penalty": 0.05, "reason": f"consistency={directional_consistency:.2f}|body={avg_body_ratio:.2f}"}
    return {"mode": "BALANCED", "threshold_bonus": 0.0, "confidence_penalty": 0.0, "reason": f"consistency={directional_consistency:.2f}|body={avg_body_ratio:.2f}|spread={spread_factor:.2f}"}


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

    latest, prev1, prev2 = candles[:3]

    def _body_ratio(candle: dict) -> float:
        candle_range = max(candle["high"] - candle["low"], 0.00001)
        return abs(candle["close"] - candle["open"]) / candle_range

    latest_body_ratio = _body_ratio(latest)
    prev1_body_ratio = _body_ratio(prev1)
    prev2_body_ratio = _body_ratio(prev2)
    if latest_body_ratio < MIN_STRUCTURE_BODY_RATIO:
        return {"pass": False, "reason": f"weak_last_candle:{latest_body_ratio:.2f}"}
    if prev1_body_ratio < 0.18:
        return {"pass": False, "reason": f"weak_prev_candle:{prev1_body_ratio:.2f}"}

    latest_dir = _candle_direction(latest)
    prev1_dir = _candle_direction(prev1)
    prev2_dir = _candle_direction(prev2)
    if "FLAT" in {latest_dir, prev1_dir}:
        return {"pass": False, "reason": "flat_structure_component"}
    soft_penalty = 0.0
    soft_reason = None
    if latest_dir != prev1_dir:
        soft_penalty = max(soft_penalty, MISALIGNED_STRUCTURE_PENALTY)
        soft_reason = f"latest_prev_misaligned_soft:{latest_dir}_vs_{prev1_dir}"

    aligned_count = len([d for d in [latest_dir, prev1_dir, prev2_dir] if d == latest_dir])
    if aligned_count < 2:
        soft_penalty = max(soft_penalty, INSUFFICIENT_ALIGNMENT_SOFT_PENALTY)
        soft_reason = (soft_reason + "|" if soft_reason else "") + "insufficient_directional_alignment_soft"

    if latest_body_ratio < STRONG_BODY_RATIO and prev1_body_ratio < STRONG_BODY_RATIO:
        return {"pass": False, "reason": f"weak_structure_impulse:{latest_body_ratio:.2f},{prev1_body_ratio:.2f}"}

    reason = "recent_structure_strong" if aligned_count == 3 else "recent_structure_supported"
    return {
        "pass": True,
        "bias": latest_dir,
        "reason": reason,
        "aligned_count": aligned_count,
        "latest_body_ratio": round(latest_body_ratio, 4),
        "prev1_body_ratio": round(prev1_body_ratio, 4),
        "prev2_body_ratio": round(prev2_body_ratio, 4),
        "soft_penalty": round(soft_penalty, 4),
        "soft_reason": soft_reason,
    }


def _trend_regime_gate(snapshot: dict, bias: str):
    candles = _extract_recent_candles(snapshot)
    if len(candles) < 5:
        return {"pass": True, "reason": "trend_regime_insufficient_candles", "score": None}

    sample = candles[:5]
    directions = [_candle_direction(c) for c in sample]

    def _body_ratio(candle: dict) -> float:
        candle_range = max(candle["high"] - candle["low"], 0.00001)
        return abs(candle["close"] - candle["open"]) / candle_range

    aligned_count = len([d for d in directions if d == bias])
    opposing_count = len([d for d in directions if d not in {bias, "FLAT"}])
    strong_aligned = len([c for c in sample if _candle_direction(c) == bias and _body_ratio(c) >= TREND_REGIME_MIN_BODY_RATIO])
    latest = sample[0]
    latest_range = max(latest["high"] - latest["low"], 0.00001)
    if bias == "BUY":
        close_position = max(latest["close"] - latest["low"], 0.0) / latest_range
    else:
        close_position = max(latest["high"] - latest["close"], 0.0) / latest_range

    regime_score = (aligned_count * 0.16) + (strong_aligned * 0.12) + (close_position * 0.18) - (opposing_count * 0.14)
    regime_score = max(0.0, min(regime_score, 1.0))

    soft_penalty = 0.0
    soft_reason = None
    market_mode = _market_mode(snapshot)
    trending_soft_allow = market_mode.get("mode") == "TRENDING" and aligned_count >= max(TREND_REGIME_SOFT_ALIGNMENT_ALLOWED - 1, 1) and regime_score >= max(TREND_REGIME_SCORE_MIN - 0.18, 0.0)
    if aligned_count < TREND_REGIME_ALIGNMENT_MIN:
        if aligned_count >= TREND_REGIME_SOFT_ALIGNMENT_ALLOWED and regime_score >= max(TREND_REGIME_SCORE_MIN - 0.14, 0.0):
            soft_penalty = TREND_REGIME_SOFT_ALIGNMENT_PENALTY
            soft_reason = f"trend_regime_alignment_soft:{aligned_count}/5"
        elif trending_soft_allow:
            soft_penalty = max(TREND_REGIME_SOFT_ALIGNMENT_PENALTY * 0.75, 0.01)
            soft_reason = f"trend_regime_alignment_trending_soft:{aligned_count}/5"
        else:
            return {"pass": False, "reason": f"trend_regime_alignment_weak:{aligned_count}/5", "score": round(regime_score, 4), "aligned_count": aligned_count, "opposing_count": opposing_count}
    if strong_aligned < 2:
        return {"pass": False, "reason": f"trend_regime_impulse_weak:{strong_aligned}", "score": round(regime_score, 4), "aligned_count": aligned_count, "opposing_count": opposing_count}
    if close_position < TREND_REGIME_PULLBACK_TOLERANCE:
        return {"pass": False, "reason": f"trend_regime_close_position_weak:{close_position:.2f}", "score": round(regime_score, 4), "aligned_count": aligned_count, "opposing_count": opposing_count}
    if regime_score < TREND_REGIME_SCORE_MIN:
        return {"pass": False, "reason": f"trend_regime_score_too_low:{regime_score:.2f}", "score": round(regime_score, 4), "aligned_count": aligned_count, "opposing_count": opposing_count}

    return {
        "pass": True,
        "reason": "trend_regime_aligned",
        "score": round(regime_score, 4),
        "aligned_count": aligned_count,
        "opposing_count": opposing_count,
        "strong_aligned": strong_aligned,
        "close_position": round(close_position, 4),
        "soft_penalty": round(soft_penalty, 4),
        "soft_reason": soft_reason,
    }


def _slippage_cooldown_gate(snapshot: dict):
    runtime = snapshot.get("runtime_state") if isinstance(snapshot.get("runtime_state"), dict) else {}
    cooldown_until = runtime.get("slippage_cooldown_until")
    if not cooldown_until:
        return {"active": False, "reason": "slippage_cooldown_inactive"}
    try:
        cooldown_dt = __import__("datetime").datetime.fromisoformat(str(cooldown_until).replace("Z", "+00:00"))
        snapshot_dt_raw = snapshot.get("timestamp_utc")
        snapshot_dt = __import__("datetime").datetime.fromisoformat(str(snapshot_dt_raw).replace("Z", "+00:00")) if snapshot_dt_raw else __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        if snapshot_dt < cooldown_dt:
            remaining = int(max((cooldown_dt - snapshot_dt).total_seconds(), 0.0))
            return {"active": True, "reason": f"slippage_cooldown_active:{remaining}s"}
    except Exception:
        return {"active": True, "reason": "slippage_cooldown_active"}
    return {"active": False, "reason": "slippage_cooldown_expired"}


def _outcome_penalty(snapshot: dict, bias: str):
    if not OUTCOME_PENALTY_ENABLED:
        return {"penalty": 0.0, "reason": "outcome_penalty_disabled", "block": False}
    runtime = snapshot.get("runtime_state") if isinstance(snapshot.get("runtime_state"), dict) else {}
    loss_side = str(runtime.get("last_loss_side") or "").upper()
    last_loss_at = runtime.get("last_loss_at")
    consecutive_losses = runtime.get("consecutive_losses") if isinstance(runtime.get("consecutive_losses"), dict) else {}
    same_side_losses = int(consecutive_losses.get(bias, 0) or 0)

    penalty = min(same_side_losses * OUTCOME_PENALTY_CONSECUTIVE_LOSS_WEIGHT, OUTCOME_PENALTY_MAX)
    reasons = []
    if same_side_losses > 0:
        reasons.append(f"same_side_losses:{same_side_losses}")

    if loss_side == bias and last_loss_at:
        try:
            loss_dt = __import__("datetime").datetime.fromisoformat(str(last_loss_at).replace("Z", "+00:00"))
            snapshot_dt_raw = snapshot.get("timestamp_utc")
            snapshot_dt = __import__("datetime").datetime.fromisoformat(str(snapshot_dt_raw).replace("Z", "+00:00")) if snapshot_dt_raw else __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
            age_sec = max((snapshot_dt - loss_dt).total_seconds(), 0.0)
            if age_sec <= OUTCOME_PENALTY_WINDOW_SEC and loss_side == bias:
                penalty += OUTCOME_PENALTY_RECENT_LOSS_WEIGHT
                reasons.append(f"recent_same_side_loss:{int(age_sec)}s")
        except Exception:
            pass

    penalty = min(penalty, OUTCOME_PENALTY_MAX)
    block = same_side_losses >= OUTCOME_PENALTY_REVENGE_BLOCK_THRESHOLD and loss_side == bias
    return {
        "penalty": round(penalty, 4),
        "reason": "|".join(reasons) if reasons else "no_recent_outcome_penalty",
        "block": block,
        "same_side_losses": same_side_losses,
    }


def _pattern_lockout(snapshot: dict, bias: str, structure_reason: str, trend_regime_reason: str):
    if not PATTERN_LOCKOUT_ENABLED:
        return {"penalty": 0.0, "reason": "pattern_lockout_disabled", "block": False, "count": 0}
    runtime = snapshot.get("runtime_state") if isinstance(snapshot.get("runtime_state"), dict) else {}
    recent_losses = runtime.get("recent_loss_patterns") if isinstance(runtime.get("recent_loss_patterns"), list) else []
    pattern_key = f"{bias}|{structure_reason}|{trend_regime_reason}"
    snapshot_ts_raw = snapshot.get("timestamp_utc")
    try:
        snapshot_dt = __import__("datetime").datetime.fromisoformat(str(snapshot_ts_raw).replace("Z", "+00:00")) if snapshot_ts_raw else __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    except Exception:
        snapshot_dt = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)

    matched = 0
    for item in recent_losses:
        if not isinstance(item, dict):
            continue
        if str(item.get("pattern_key") or "") != pattern_key:
            continue
        try:
            loss_dt = __import__("datetime").datetime.fromisoformat(str(item.get("at")).replace("Z", "+00:00"))
            age_sec = max((snapshot_dt - loss_dt).total_seconds(), 0.0)
        except Exception:
            age_sec = PATTERN_LOCKOUT_WINDOW_SEC + 1
        if age_sec <= PATTERN_LOCKOUT_WINDOW_SEC:
            matched += 1

    block = matched >= PATTERN_LOCKOUT_THRESHOLD
    penalty = PATTERN_LOCKOUT_PENALTY if matched > 0 else 0.0
    return {
        "penalty": penalty,
        "reason": f"pattern_matches:{matched}|key:{pattern_key}",
        "block": block,
        "count": matched,
        "pattern_key": pattern_key,
    }


def _journal_reason_penalty(snapshot: dict, bias: str, structure_reason: str, trend_regime_reason: str):
    if not JOURNAL_REASON_SCORE_ENABLED:
        return {"penalty": 0.0, "reason": "journal_reason_score_disabled", "loss_rate": None, "trade_count": 0}
    runtime = snapshot.get("runtime_state") if isinstance(snapshot.get("runtime_state"), dict) else {}
    reason_scores = runtime.get("reason_outcome_scores") if isinstance(runtime.get("reason_outcome_scores"), dict) else {}
    key_candidates = [
        f"side:{bias}",
        f"structure:{structure_reason}",
        f"trend:{trend_regime_reason}",
        f"combo:{bias}|{structure_reason}|{trend_regime_reason}",
    ]
    penalties = []
    descriptors = []
    max_trade_count = 0
    worst_loss_rate = None
    for key in key_candidates:
        item = reason_scores.get(key)
        if not isinstance(item, dict):
            continue
        trade_count = int(item.get("trades", 0) or 0)
        loss_count = int(item.get("losses", 0) or 0)
        if trade_count < JOURNAL_REASON_SCORE_MIN_TRADES or trade_count <= 0:
            continue
        loss_rate = loss_count / trade_count
        max_trade_count = max(max_trade_count, trade_count)
        if worst_loss_rate is None or loss_rate > worst_loss_rate:
            worst_loss_rate = loss_rate
        if loss_rate >= 0.75:
            penalties.append(JOURNAL_REASON_SCORE_MAX_PENALTY)
        elif loss_rate >= 0.6:
            penalties.append(JOURNAL_REASON_SCORE_MAX_PENALTY * 0.7)
        elif loss_rate >= 0.5:
            penalties.append(JOURNAL_REASON_SCORE_MAX_PENALTY * 0.4)
        descriptors.append(f"{key}:{loss_count}/{trade_count}")

    penalty = max(penalties) if penalties else 0.0
    return {
        "penalty": round(min(penalty, JOURNAL_REASON_SCORE_MAX_PENALTY), 4),
        "reason": "|".join(descriptors) if descriptors else "no_reason_score_penalty",
        "loss_rate": round(worst_loss_rate, 4) if worst_loss_rate is not None else None,
        "trade_count": max_trade_count,
    }


def _exit_reason_penalty(snapshot: dict, session_bucket: str):
    if not EXIT_REASON_PENALTY_ENABLED:
        return {"penalty": 0.0, "reason": "exit_reason_penalty_disabled", "loss_rate": None, "trade_count": 0, "block": False}
    runtime = snapshot.get("runtime_state") if isinstance(snapshot.get("runtime_state"), dict) else {}
    reason_scores = runtime.get("reason_outcome_scores") if isinstance(runtime.get("reason_outcome_scores"), dict) else {}
    key_candidates = [
        "exit:STOP_LOSS",
        "exit:GAP_SLIPPAGE_SL",
        f"session_exit:{session_bucket}|STOP_LOSS",
        f"session_exit:{session_bucket}|GAP_SLIPPAGE_SL",
    ]
    penalties = []
    descriptors = []
    worst_loss_rate = None
    max_trade_count = 0
    block = False
    for key in key_candidates:
        item = reason_scores.get(key)
        if not isinstance(item, dict):
            continue
        trades = int(item.get("trades", 0) or 0)
        losses = int(item.get("losses", 0) or 0)
        if trades < EXIT_REASON_PENALTY_MIN_TRADES or trades <= 0:
            continue
        loss_rate = losses / trades
        max_trade_count = max(max_trade_count, trades)
        if worst_loss_rate is None or loss_rate > worst_loss_rate:
            worst_loss_rate = loss_rate
        if loss_rate >= EXIT_REASON_HARD_BLOCK_THRESHOLD and "GAP_SLIPPAGE_SL" in key:
            block = True
        if loss_rate >= 0.75:
            penalties.append(EXIT_REASON_PENALTY_MAX)
        elif loss_rate >= 0.6:
            penalties.append(EXIT_REASON_PENALTY_MAX * 0.7)
        elif loss_rate >= 0.5:
            penalties.append(EXIT_REASON_PENALTY_MAX * 0.4)
        descriptors.append(f"{key}:{losses}/{trades}")
    penalty = max(penalties) if penalties else 0.0
    return {
        "penalty": round(min(penalty, EXIT_REASON_PENALTY_MAX), 4),
        "reason": "|".join(descriptors) if descriptors else "no_exit_reason_penalty",
        "loss_rate": round(worst_loss_rate, 4) if worst_loss_rate is not None else None,
        "trade_count": max_trade_count,
        "block": block,
    }


def _market_toxicity(snapshot: dict):
    if not MARKET_TOXICITY_ENABLED:
        return {"score": 0.0, "penalty": 0.0, "reason": "market_toxicity_disabled", "block": False}
    runtime = snapshot.get("runtime_state") if isinstance(snapshot.get("runtime_state"), dict) else {}
    spread_points = float(snapshot.get("spread_points") or 0.0)
    symbol = normalize_symbol(snapshot.get("symbol"))
    max_spread = float(get_max_spread(symbol) or 1.0)
    spread_component = min(max(spread_points / max_spread, 0.0), 1.0)
    slippage_events = runtime.get("recent_slippage_events") if isinstance(runtime.get("recent_slippage_events"), list) else []
    slippage_component = min(len(slippage_events) / 3.0, 1.0)
    reason_scores = runtime.get("reason_outcome_scores") if isinstance(runtime.get("reason_outcome_scores"), dict) else {}
    exit_gap = reason_scores.get("exit:GAP_SLIPPAGE_SL") if isinstance(reason_scores.get("exit:GAP_SLIPPAGE_SL"), dict) else None
    gap_loss_rate = 0.0
    if exit_gap:
        trades = int(exit_gap.get("trades", 0) or 0)
        losses = int(exit_gap.get("losses", 0) or 0)
        if trades > 0:
            gap_loss_rate = losses / trades
    score = min((spread_component * 0.35) + (slippage_component * 0.4) + (gap_loss_rate * 0.25), 1.0)
    penalty = 0.0
    if score >= 0.75:
        penalty = MARKET_TOXICITY_PENALTY_MAX
    elif score >= 0.6:
        penalty = MARKET_TOXICITY_PENALTY_MAX * 0.7
    elif score >= 0.45:
        penalty = MARKET_TOXICITY_PENALTY_MAX * 0.4
    return {
        "score": round(score, 4),
        "penalty": round(min(penalty, MARKET_TOXICITY_PENALTY_MAX), 4),
        "reason": f"spread={spread_component:.2f}|slippage={slippage_component:.2f}|gap_loss={gap_loss_rate:.2f}",
        "block": score >= MARKET_TOXICITY_HARD_BLOCK_THRESHOLD,
    }


def _auto_hardening(snapshot: dict, bias: str, structure_reason: str, trend_regime_reason: str):
    if not AUTO_HARDENING_ENABLED:
        return {"threshold_bonus": 0.0, "reason": "auto_hardening_disabled", "triggered": False}
    runtime = snapshot.get("runtime_state") if isinstance(snapshot.get("runtime_state"), dict) else {}
    reason_scores = runtime.get("reason_outcome_scores") if isinstance(runtime.get("reason_outcome_scores"), dict) else {}
    key_candidates = [
        f"side:{bias}",
        f"structure:{structure_reason}",
        f"trend:{trend_regime_reason}",
        f"combo:{bias}|{structure_reason}|{trend_regime_reason}",
    ]
    triggered_keys = []
    for key in key_candidates:
        item = reason_scores.get(key)
        if not isinstance(item, dict):
            continue
        trades = int(item.get("trades", 0) or 0)
        losses = int(item.get("losses", 0) or 0)
        if trades < JOURNAL_REASON_SCORE_MIN_TRADES or trades <= 0:
            continue
        loss_rate = losses / trades
        if loss_rate >= AUTO_HARDENING_THRESHOLD:
            triggered_keys.append(f"{key}:{losses}/{trades}")
    triggered = len(triggered_keys) > 0
    return {
        "threshold_bonus": AUTO_HARDENING_THRESHOLD_BONUS if triggered else 0.0,
        "reason": "|".join(triggered_keys) if triggered else "no_auto_hardening",
        "triggered": triggered,
    }


def _apply_confidence_cap(raw_score: float, pf: dict) -> float:
    if not MULTI_PENALTY_CONFIDENCE_CAP_ENABLED:
        return raw_score
    penalty_count = 0
    for key in ["outcome_penalty", "market_toxicity_penalty", "pattern_lockout_penalty", "journal_reason_penalty", "session_penalty", "exit_reason_penalty"]:
        if float(pf.get(key) or 0.0) > 0:
            penalty_count += 1
    if penalty_count >= MULTI_PENALTY_CONFIDENCE_CAP_THRESHOLD:
        return min(raw_score, MULTI_PENALTY_CONFIDENCE_CAP_VALUE)
    return raw_score


def _session_bucket(snapshot: dict) -> str:
    ts = snapshot.get("timestamp_utc")
    if not ts:
        return "UNKNOWN"
    try:
        dt = __import__("datetime").datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        hour = dt.hour
    except Exception:
        return "UNKNOWN"
    if 0 <= hour < 7:
        return "ASIA"
    if 7 <= hour < 13:
        return "LONDON"
    if 13 <= hour < 21:
        return "NY"
    return "OFF_SESSION"


def _session_hard_block(snapshot: dict, bias: str, session_bucket: str):
    if not SESSION_HARD_BLOCK_ENABLED:
        return {"block": False, "reason": "session_hard_block_disabled"}
    runtime = snapshot.get("runtime_state") if isinstance(snapshot.get("runtime_state"), dict) else {}
    reason_scores = runtime.get("reason_outcome_scores") if isinstance(runtime.get("reason_outcome_scores"), dict) else {}
    keys = [f"session:{session_bucket}", f"session_side:{session_bucket}|{bias}"]
    reasons = []
    for key in keys:
        item = reason_scores.get(key)
        if not isinstance(item, dict):
            continue
        trades = int(item.get("trades", 0) or 0)
        losses = int(item.get("losses", 0) or 0)
        if trades < SESSION_HARD_BLOCK_MIN_TRADES or trades <= 0:
            continue
        loss_rate = losses / trades
        if loss_rate >= SESSION_HARD_BLOCK_LOSS_RATE:
            reasons.append(f"{key}:{losses}/{trades}")
    return {"block": len(reasons) > 0, "reason": "|".join(reasons) if reasons else "session_hard_block_clear"}


def _session_penalty(snapshot: dict, bias: str):
    session_bucket = _session_bucket(snapshot)
    if not SESSION_SCORING_ENABLED:
        return {"penalty": 0.0, "reason": "session_scoring_disabled", "session_bucket": session_bucket, "loss_rate": None, "trade_count": 0}
    runtime = snapshot.get("runtime_state") if isinstance(snapshot.get("runtime_state"), dict) else {}
    reason_scores = runtime.get("reason_outcome_scores") if isinstance(runtime.get("reason_outcome_scores"), dict) else {}
    key_candidates = [f"session:{session_bucket}", f"session_side:{session_bucket}|{bias}"]
    penalties = []
    descriptors = []
    max_trade_count = 0
    worst_loss_rate = None
    for key in key_candidates:
        item = reason_scores.get(key)
        if not isinstance(item, dict):
            continue
        trades = int(item.get("trades", 0) or 0)
        losses = int(item.get("losses", 0) or 0)
        if trades < SESSION_SCORE_MIN_TRADES or trades <= 0:
            continue
        loss_rate = losses / trades
        max_trade_count = max(max_trade_count, trades)
        if worst_loss_rate is None or loss_rate > worst_loss_rate:
            worst_loss_rate = loss_rate
        if loss_rate >= 0.75:
            penalties.append(SESSION_SCORE_MAX_PENALTY)
        elif loss_rate >= 0.6:
            penalties.append(SESSION_SCORE_MAX_PENALTY * 0.7)
        elif loss_rate >= 0.5:
            penalties.append(SESSION_SCORE_MAX_PENALTY * 0.4)
        descriptors.append(f"{key}:{losses}/{trades}")
    penalty = max(penalties) if penalties else 0.0
    return {
        "penalty": round(min(penalty, SESSION_SCORE_MAX_PENALTY), 4),
        "reason": "|".join(descriptors) if descriptors else "no_session_penalty",
        "session_bucket": session_bucket,
        "loss_rate": round(worst_loss_rate, 4) if worst_loss_rate is not None else None,
        "trade_count": max_trade_count,
    }


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

    market_mode = _market_mode(snapshot)
    if market_mode.get("mode") == "TOXIC":
        return {"pass": False, "reason": f"market_mode_block:{market_mode.get('reason')}"}

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

    trend_regime = _trend_regime_gate(snapshot, bias)
    if not trend_regime["pass"]:
        return {"pass": False, "reason": trend_regime["reason"]}

    slippage_cooldown = _slippage_cooldown_gate(snapshot)
    if slippage_cooldown.get("active"):
        return {"pass": False, "reason": slippage_cooldown.get("reason")}

    market_toxicity = _market_toxicity(snapshot)
    if market_toxicity.get("block"):
        return {"pass": False, "reason": f"market_toxicity_block:{market_toxicity.get('reason')}"}

    outcome_penalty = _outcome_penalty(snapshot, bias)
    if outcome_penalty.get("block"):
        return {"pass": False, "reason": f"outcome_revenge_block:{outcome_penalty.get('reason')}"}

    pattern_lockout = _pattern_lockout(snapshot, bias, structure.get("reason", "unknown_structure"), trend_regime.get("reason", "unknown_trend"))
    if pattern_lockout.get("block"):
        return {"pass": False, "reason": f"pattern_lockout:{pattern_lockout.get('reason')}"}

    journal_reason_penalty = _journal_reason_penalty(snapshot, bias, structure.get("reason", "unknown_structure"), trend_regime.get("reason", "unknown_trend"))
    auto_hardening = _auto_hardening(snapshot, bias, structure.get("reason", "unknown_structure"), trend_regime.get("reason", "unknown_trend"))
    session_penalty = _session_penalty(snapshot, bias)
    session_hard_block = _session_hard_block(snapshot, bias, session_penalty.get("session_bucket", "UNKNOWN"))
    if session_hard_block.get("block"):
        return {"pass": False, "reason": f"session_hard_block:{session_hard_block.get('reason')}"}
    exit_reason_penalty = _exit_reason_penalty(snapshot, session_penalty.get("session_bucket", "UNKNOWN"))
    if exit_reason_penalty.get("block"):
        return {"pass": False, "reason": f"exit_reason_hard_block:{exit_reason_penalty.get('reason')}"}

    entry = round((bid + ask) / 2.0, 5 if symbol != "XAUUSD" else 2)
    candle_range = max(high - low, 0.00001)
    body_ratio = abs(close - open_) / candle_range
    close_to_high_ratio = max(high - close, 0.0) / candle_range
    close_to_low_ratio = max(close - low, 0.0) / candle_range
    if bias == "BUY":
        late_distance = max(entry - low, 0.0)
    else:
        late_distance = max(high - entry, 0.0)
    late_ratio = late_distance / candle_range
    late_entry_limit = LATE_ENTRY_RANGE_FACTOR
    if market_mode.get("mode") == "TRENDING" and float(trend_regime.get("score") or 0.0) >= 0.72:
        late_entry_limit += MARKET_MODE_TRENDING_LATE_ENTRY_BONUS
    if late_ratio >= late_entry_limit:
        return {"pass": False, "reason": f"late_entry:{late_ratio:.2f}>={late_entry_limit:.2f}"}
    if bias == "BUY" and close_to_high_ratio <= NO_CHASE_CLOSE_EXTREME_RATIO:
        return {"pass": False, "reason": f"no_chase_buy:close_to_high={close_to_high_ratio:.2f}"}
    if bias == "SELL" and close_to_low_ratio <= NO_CHASE_CLOSE_EXTREME_RATIO:
        return {"pass": False, "reason": f"no_chase_sell:close_to_low={close_to_low_ratio:.2f}"}
    if body_ratio >= EXHAUSTION_BODY_RATIO and late_ratio >= 0.5:
        return {"pass": False, "reason": f"exhaustion_risk:body={body_ratio:.2f},late={late_ratio:.2f}"}

    spread_quality = max(0.0, 1.0 - (spread / max_spread)) if max_spread > 0 else 0.0
    if symbol == "XAUUSD" and spread_quality < 0.25:
        return {"pass": False, "reason": f"poor_spread_quality:{spread_quality:.2f}"}

    structure_soft_penalty = float(structure.get("soft_penalty") or 0.0)
    trend_soft_penalty = float(trend_regime.get("soft_penalty") or 0.0)

    return {
        "pass": True,
        "bias": bias,
        "entry": entry,
        "reason": f"basic_candle_bias|{session['reason']}|{volatility['reason']}|{structure['reason']}|market_mode:{market_mode.get('mode')}",
        "recent_structure": structure['reason'],
        "recent_candles_used": len(_extract_recent_candles(snapshot)),
        "session_reason": session['reason'],
        "volatility_reason": volatility['reason'],
        "market_mode": market_mode.get("mode"),
        "market_mode_reason": market_mode.get("reason"),
        "market_mode_threshold_bonus": market_mode.get("threshold_bonus"),
        "market_mode_confidence_penalty": market_mode.get("confidence_penalty"),
        "spread_quality": round(spread_quality, 4),
        "late_ratio": round(late_ratio, 4),
        "late_entry_limit": round(late_entry_limit, 4),
        "body_ratio": round(body_ratio, 4),
        "close_to_high_ratio": round(close_to_high_ratio, 4),
        "close_to_low_ratio": round(close_to_low_ratio, 4),
        "structure_alignment": structure.get("aligned_count"),
        "latest_structure_body_ratio": structure.get("latest_body_ratio"),
        "prev1_structure_body_ratio": structure.get("prev1_body_ratio"),
        "structure_soft_penalty": structure_soft_penalty,
        "structure_soft_reason": structure.get("soft_reason"),
        "trend_regime_reason": trend_regime.get("reason"),
        "trend_regime_score": trend_regime.get("score"),
        "trend_regime_alignment": trend_regime.get("aligned_count"),
        "trend_regime_opposing_count": trend_regime.get("opposing_count"),
        "trend_regime_strong_aligned": trend_regime.get("strong_aligned"),
        "trend_regime_close_position": trend_regime.get("close_position"),
        "trend_regime_soft_penalty": trend_soft_penalty,
        "trend_regime_soft_reason": trend_regime.get("soft_reason"),
        "outcome_penalty": outcome_penalty.get("penalty"),
        "outcome_penalty_reason": outcome_penalty.get("reason"),
        "same_side_losses": outcome_penalty.get("same_side_losses"),
        "market_toxicity_score": market_toxicity.get("score"),
        "market_toxicity_penalty": market_toxicity.get("penalty"),
        "market_toxicity_reason": market_toxicity.get("reason"),
        "pattern_lockout_penalty": pattern_lockout.get("penalty"),
        "pattern_lockout_reason": pattern_lockout.get("reason"),
        "pattern_lockout_count": pattern_lockout.get("count"),
        "pattern_lockout_key": pattern_lockout.get("pattern_key"),
        "journal_reason_penalty": journal_reason_penalty.get("penalty"),
        "journal_reason_penalty_reason": journal_reason_penalty.get("reason"),
        "journal_reason_loss_rate": journal_reason_penalty.get("loss_rate"),
        "journal_reason_trade_count": journal_reason_penalty.get("trade_count"),
        "auto_hardening_threshold_bonus": auto_hardening.get("threshold_bonus"),
        "auto_hardening_reason": auto_hardening.get("reason"),
        "auto_hardening_triggered": auto_hardening.get("triggered"),
        "session_bucket": session_penalty.get("session_bucket"),
        "session_penalty": session_penalty.get("penalty"),
        "session_penalty_reason": session_penalty.get("reason"),
        "session_loss_rate": session_penalty.get("loss_rate"),
        "session_trade_count": session_penalty.get("trade_count"),
        "exit_reason_penalty": exit_reason_penalty.get("penalty"),
        "exit_reason_penalty_reason": exit_reason_penalty.get("reason"),
        "exit_reason_loss_rate": exit_reason_penalty.get("loss_rate"),
        "exit_reason_trade_count": exit_reason_penalty.get("trade_count"),
    }


def _score_prefilter_confidence(snapshot: dict, pf: dict) -> float:
    confidence = 0.42
    reason = str(pf.get("reason", ""))
    if "recent_structure_strong" in reason:
        confidence += 0.10
    elif "recent_structure_supported" in reason:
        confidence += 0.05
    if "range_ok:" in reason:
        confidence += 0.04

    spread_quality = float(pf.get("spread_quality", 0.0))
    confidence += min(max(spread_quality, 0.0), 1.0) * 0.08

    late_ratio = float(pf.get("late_ratio", 1.0))
    confidence += max(0.0, (1.0 - late_ratio)) * 0.06
    if late_ratio > 0.45:
        confidence -= 0.05

    body_ratio = float(pf.get("body_ratio", 0.0))
    if 0.35 <= body_ratio <= 0.65:
        confidence += 0.05
    elif body_ratio > 0.78:
        confidence -= 0.10

    close_to_high_ratio = float(pf.get("close_to_high_ratio", 0.5))
    close_to_low_ratio = float(pf.get("close_to_low_ratio", 0.5))
    bias = pf.get("bias")
    if bias == "BUY" and close_to_high_ratio < 0.18:
        confidence -= 0.06
    if bias == "SELL" and close_to_low_ratio < 0.18:
        confidence -= 0.06

    structure_alignment = int(pf.get("structure_alignment") or 0)
    if structure_alignment == 3:
        confidence += 0.08
    elif structure_alignment == 2:
        confidence += 0.03

    confidence -= float(pf.get("structure_soft_penalty") or 0.0)

    trend_regime_score = float(pf.get("trend_regime_score") or 0.0)
    trend_regime_alignment = int(pf.get("trend_regime_alignment") or 0)
    if trend_regime_score >= 0.7:
        confidence += 0.06
    elif trend_regime_score < 0.6:
        confidence -= 0.05
    if trend_regime_alignment >= 4:
        confidence += 0.04
    confidence -= float(pf.get("trend_regime_soft_penalty") or 0.0)
    confidence -= float(pf.get("market_mode_confidence_penalty") or 0.0)

    outcome_penalty = float(pf.get("outcome_penalty") or 0.0)
    if outcome_penalty > 0:
        confidence -= outcome_penalty

    market_toxicity_penalty = float(pf.get("market_toxicity_penalty") or 0.0)
    if market_toxicity_penalty > 0:
        confidence -= market_toxicity_penalty

    pattern_lockout_penalty = float(pf.get("pattern_lockout_penalty") or 0.0)
    if pattern_lockout_penalty > 0:
        confidence -= pattern_lockout_penalty

    journal_reason_penalty = float(pf.get("journal_reason_penalty") or 0.0)
    if journal_reason_penalty > 0:
        confidence -= journal_reason_penalty

    session_penalty = float(pf.get("session_penalty") or 0.0)
    if session_penalty > 0:
        confidence -= session_penalty

    exit_reason_penalty = float(pf.get("exit_reason_penalty") or 0.0)
    if exit_reason_penalty > 0:
        confidence -= exit_reason_penalty

    candles = _extract_recent_candles(snapshot)
    if len(candles) >= 3:
        same_dir = [_candle_direction(c) for c in candles[:3]]
        if len(set(same_dir)) == 1 and "FLAT" not in same_dir:
            confidence += 0.08
        elif len(set(same_dir)) == 2:
            confidence -= 0.05

    return max(0.0, min(confidence, 0.82))


def _deterministic_score(snapshot: dict, pf: dict) -> float:
    score = _score_prefilter_confidence(snapshot, pf)
    spread_quality = float(pf.get("spread_quality", 0.0))
    late_ratio = float(pf.get("late_ratio", 1.0))
    body_ratio = float(pf.get("body_ratio", 0.0))
    score += spread_quality * 0.05
    score += max(0.0, 1.0 - late_ratio) * 0.04
    if 0.35 <= body_ratio <= 0.65:
        score += 0.02
    elif body_ratio > 0.78:
        score -= 0.08
    if late_ratio > 0.45:
        score -= 0.05
    if float(pf.get("close_to_high_ratio", 0.5)) < 0.18 and pf.get("bias") == "BUY":
        score -= 0.05
    if float(pf.get("close_to_low_ratio", 0.5)) < 0.18 and pf.get("bias") == "SELL":
        score -= 0.05
    if int(pf.get("structure_alignment") or 0) == 3:
        score += 0.04
    trend_regime_score = float(pf.get("trend_regime_score") or 0.0)
    if trend_regime_score >= 0.72:
        score += 0.05
    elif trend_regime_score < 0.6:
        score -= 0.06
    if int(pf.get("trend_regime_alignment") or 0) >= 4:
        score += 0.03
    score -= float(pf.get("outcome_penalty") or 0.0)
    score -= float(pf.get("market_toxicity_penalty") or 0.0)
    score -= float(pf.get("pattern_lockout_penalty") or 0.0)
    score -= float(pf.get("journal_reason_penalty") or 0.0)
    score -= float(pf.get("session_penalty") or 0.0)
    score -= float(pf.get("exit_reason_penalty") or 0.0)
    score = _apply_confidence_cap(score, pf)
    return max(0.0, min(score, 0.9))


def _adaptive_thresholds(pf: dict):
    trade_threshold = DETERMINISTIC_SCORE_TRADE_THRESHOLD
    no_trade_threshold = DETERMINISTIC_SCORE_NO_TRADE_THRESHOLD
    if not ADAPTIVE_THRESHOLD_ENABLED:
        return trade_threshold, no_trade_threshold

    spread_quality = float(pf.get("spread_quality", 0.0))
    late_ratio = float(pf.get("late_ratio", 1.0))
    body_ratio = float(pf.get("body_ratio", 0.0))

    penalty = 0.0
    bonus = 0.0

    if spread_quality < 0.45:
        penalty += 0.04
    elif spread_quality > 0.82:
        bonus += 0.01

    if late_ratio > 0.5:
        penalty += 0.04
    elif late_ratio < 0.25:
        bonus += 0.005

    if body_ratio > 0.72:
        penalty += 0.03
    elif 0.35 <= body_ratio <= 0.58:
        bonus += 0.005

    if float(pf.get("close_to_high_ratio", 0.5)) < 0.18 and pf.get("bias") == "BUY":
        penalty += 0.02
    if float(pf.get("close_to_low_ratio", 0.5)) < 0.18 and pf.get("bias") == "SELL":
        penalty += 0.02

    if int(pf.get("structure_alignment") or 0) == 3:
        bonus += 0.005
    elif int(pf.get("structure_alignment") or 0) < 2:
        penalty += 0.02

    trend_regime_score = float(pf.get("trend_regime_score") or 0.0)
    trend_regime_alignment = int(pf.get("trend_regime_alignment") or 0)
    if trend_regime_score < 0.62:
        penalty += 0.03
    elif trend_regime_score > 0.78:
        bonus += 0.005

    market_mode = str(pf.get("market_mode") or "UNKNOWN").upper()
    if market_mode == "TRENDING" and trend_regime_score >= 0.78 and float(pf.get("market_toxicity_score") or 0.0) <= 0.25:
        bonus += MARKET_MODE_TRENDING_THRESHOLD_BONUS
    if trend_regime_alignment < 3:
        penalty += 0.02
    elif trend_regime_alignment >= 4:
        bonus += 0.005

    threshold_bonus = float(pf.get("market_mode_threshold_bonus") or 0.0)
    if threshold_bonus >= 0:
        penalty += threshold_bonus
    else:
        bonus += abs(threshold_bonus)

    penalty += float(pf.get("outcome_penalty") or 0.0)
    penalty += float(pf.get("market_toxicity_penalty") or 0.0)
    penalty += float(pf.get("pattern_lockout_penalty") or 0.0)
    penalty += float(pf.get("journal_reason_penalty") or 0.0)
    penalty += float(pf.get("session_penalty") or 0.0)
    penalty += float(pf.get("exit_reason_penalty") or 0.0)
    penalty += float(pf.get("auto_hardening_threshold_bonus") or 0.0)

    penalty = min(penalty, ADAPTIVE_THRESHOLD_MAX_PENALTY)
    bonus = min(bonus, ADAPTIVE_THRESHOLD_MAX_BONUS)
    trade_threshold = max(0.4, min(0.9, trade_threshold + penalty - bonus))
    no_trade_threshold = max(0.3, min(trade_threshold - 0.02, no_trade_threshold + (penalty * 0.7) - (bonus * 0.5)))
    return trade_threshold, no_trade_threshold


def _quality_tier(score: float, pf: dict):
    if not QUALITY_TIERING_ENABLED:
        return {"tier": "UNSET", "label": "tiering_disabled", "penalty_count": 0}
    penalty_count = len([1 for key in ["outcome_penalty", "market_toxicity_penalty", "pattern_lockout_penalty", "journal_reason_penalty", "session_penalty", "exit_reason_penalty"] if float(pf.get(key) or 0.0) > 0.0])
    if score >= QUALITY_TIER_A_MIN and penalty_count <= 1:
        return {"tier": "A", "label": "high_quality", "penalty_count": penalty_count}
    market_mode = str(pf.get("market_mode") or "UNKNOWN").upper()
    trend_regime_score = float(pf.get("trend_regime_score") or 0.0)
    market_toxicity_score = float(pf.get("market_toxicity_score") or 0.0)
    if score >= QUALITY_TIER_B_MIN and penalty_count <= 3:
        if market_mode == "TRENDING" and trend_regime_score >= 0.78 and market_toxicity_score <= 0.25 and penalty_count <= MARKET_MODE_TRENDING_B_TIER_MAX_PENALTIES:
            return {"tier": "B", "label": "acceptable_quality_trending", "penalty_count": penalty_count}
        return {"tier": "B", "label": "acceptable_quality", "penalty_count": penalty_count}
    return {"tier": "C", "label": "fragile_quality", "penalty_count": penalty_count}


def _build_trend_context(pf: dict) -> dict:
    bias = str(pf.get("bias") or "UNKNOWN").upper()
    trend_score = float(pf.get("trend_regime_score") or 0.0)
    alignment_count = int(pf.get("trend_regime_alignment") or 0)
    opposing_count = int(pf.get("trend_regime_opposing_count") or 0)
    market_mode = str(pf.get("market_mode") or "UNKNOWN").upper()
    body_ratio = float(pf.get("body_ratio") or 0.0)
    late_ratio = float(pf.get("late_ratio") or 1.0)
    exhaustion_flag = body_ratio >= EXHAUSTION_BODY_RATIO or late_ratio >= max(LATE_ENTRY_RANGE_FACTOR * 0.9, 0.5)
    continuation_candidate = alignment_count >= TREND_REGIME_ALIGNMENT_MIN and trend_score >= TREND_REGIME_SCORE_MIN and opposing_count <= 1 and market_mode not in {"CHOPPY", "TOXIC"}
    reversal_candidate = alignment_count <= max(TREND_REGIME_SOFT_ALIGNMENT_ALLOWED, 2) and opposing_count >= 1 and body_ratio >= MIN_STRUCTURE_BODY_RATIO and market_mode in {"BALANCED", "TRENDING", "QUIET"}
    return {
        "dominant_bias": bias,
        "trend_strength": round(trend_score, 4),
        "alignment_count": alignment_count,
        "opposing_count": opposing_count,
        "market_mode": market_mode,
        "exhaustion_flag": exhaustion_flag,
        "reversal_candidate": reversal_candidate,
        "continuation_candidate": continuation_candidate,
        "late_ratio": round(late_ratio, 4),
        "body_ratio": round(body_ratio, 4),
    }


def _classify_setup_type(pf: dict, trend_context: dict, quality_tier: dict) -> dict:
    bias = str(pf.get("bias") or "UNKNOWN").upper()
    quality = str(quality_tier.get("tier") or "C").upper()
    market_mode = str(trend_context.get("market_mode") or "UNKNOWN").upper()
    continuation_candidate = bool(trend_context.get("continuation_candidate"))
    reversal_candidate = bool(trend_context.get("reversal_candidate"))
    exhaustion_flag = bool(trend_context.get("exhaustion_flag"))
    trend_strength = float(trend_context.get("trend_strength") or 0.0)
    alignment_count = int(trend_context.get("alignment_count") or 0)
    opposing_count = int(trend_context.get("opposing_count") or 0)
    late_ratio = float(trend_context.get("late_ratio") or 1.0)
    body_ratio = float(trend_context.get("body_ratio") or 0.0)

    continuation_hard_ok = continuation_candidate and quality in {"A", "B"} and trend_strength >= max(TREND_REGIME_SCORE_MIN, 0.62) and alignment_count >= max(TREND_REGIME_ALIGNMENT_MIN, 3) and late_ratio <= 0.55
    reversal_hard_ok = reversal_candidate and quality == "A" and market_mode not in {"CHOPPY", "TOXIC"} and trend_strength <= 0.68 and opposing_count >= 1 and body_ratio >= max(MIN_STRUCTURE_BODY_RATIO, 0.30) and late_ratio <= 0.45

    if continuation_hard_ok:
        return {
            "setup_type": "CONTINUATION",
            "setup_reason": f"continuation_aligned:{bias}|trend={trend_strength:.2f}|align={alignment_count}|late={late_ratio:.2f}",
            "trend_aligned": True,
            "reversal_confirmed": False,
            "continuation_confirmed": True,
            "policy_mode": "trend_follow_only",
        }

    if reversal_hard_ok and not exhaustion_flag:
        return {
            "setup_type": "REVERSAL",
            "setup_reason": f"reversal_confirmed:{bias}|trend={trend_strength:.2f}|opp={opposing_count}|late={late_ratio:.2f}",
            "trend_aligned": False,
            "reversal_confirmed": True,
            "continuation_confirmed": False,
            "policy_mode": "confirmed_reversal_only",
        }

    return {
        "setup_type": "NO_TRADE",
        "setup_reason": f"setup_ambiguous:{bias}|trend={trend_strength:.2f}|mode={market_mode}|quality={quality}|late={late_ratio:.2f}",
        "trend_aligned": continuation_candidate,
        "reversal_confirmed": False,
        "continuation_confirmed": continuation_candidate,
        "policy_mode": "hard_block_ambiguous",
    }


def decide_with_mock_gemini(snapshot: dict):
    pf = prefilter(snapshot)
    if not pf["pass"]:
        return {"decision": "NO_TRADE", "confidence": 0.0, "reason": pf["reason"]}
    score = _deterministic_score(snapshot, pf)
    trade_threshold, no_trade_threshold = _adaptive_thresholds(pf)
    decision = pf["bias"] if score >= trade_threshold else "NO_TRADE"
    reason = pf["reason"] if decision != "NO_TRADE" else f"deterministic_score_too_low:{score:.2f}|threshold={trade_threshold:.2f}|{pf['reason']}"
    quality_tier = _quality_tier(score, pf)
    trend_context = _build_trend_context(pf)
    setup_meta = _classify_setup_type(pf, trend_context, quality_tier)
    if decision in {"BUY", "SELL"} and QUALITY_TIER_C_BLOCK_ENABLED and quality_tier.get("tier") == "C":
        decision = "NO_TRADE"
        reason = f"quality_tier_block:C|score={score:.2f}|{pf['reason']}"
    if decision in {"BUY", "SELL"} and setup_meta.get("setup_type") == "NO_TRADE":
        decision = "NO_TRADE"
        reason = f"setup_type_block:{setup_meta.get('setup_reason')}|{pf['reason']}"
    return {
        "decision": decision,
        "confidence": score,
        "reason": reason,
        "entry": pf["entry"],
        "symbol": normalize_symbol(snapshot["symbol"]),
        "timeframe": snapshot.get("timeframe", "M1"),
        "deterministic_score": score,
        "adaptive_trade_threshold": trade_threshold,
        "adaptive_no_trade_threshold": no_trade_threshold,
        "trend_regime_reason": pf.get("trend_regime_reason"),
        "trend_regime_score": pf.get("trend_regime_score"),
        "trend_regime_alignment": pf.get("trend_regime_alignment"),
        "trend_regime_opposing_count": pf.get("trend_regime_opposing_count"),
        "trend_regime_strong_aligned": pf.get("trend_regime_strong_aligned"),
        "trend_regime_close_position": pf.get("trend_regime_close_position"),
        "outcome_penalty": pf.get("outcome_penalty"),
        "outcome_penalty_reason": pf.get("outcome_penalty_reason"),
        "same_side_losses": pf.get("same_side_losses"),
        "market_toxicity_score": pf.get("market_toxicity_score"),
        "market_toxicity_penalty": pf.get("market_toxicity_penalty"),
        "market_toxicity_reason": pf.get("market_toxicity_reason"),
        "pattern_lockout_penalty": pf.get("pattern_lockout_penalty"),
        "pattern_lockout_reason": pf.get("pattern_lockout_reason"),
        "pattern_lockout_count": pf.get("pattern_lockout_count"),
        "pattern_lockout_key": pf.get("pattern_lockout_key"),
        "journal_reason_penalty": pf.get("journal_reason_penalty"),
        "journal_reason_penalty_reason": pf.get("journal_reason_penalty_reason"),
        "journal_reason_loss_rate": pf.get("journal_reason_loss_rate"),
        "journal_reason_trade_count": pf.get("journal_reason_trade_count"),
        "auto_hardening_threshold_bonus": pf.get("auto_hardening_threshold_bonus"),
        "auto_hardening_reason": pf.get("auto_hardening_reason"),
        "auto_hardening_triggered": pf.get("auto_hardening_triggered"),
        "session_bucket": pf.get("session_bucket"),
        "session_penalty": pf.get("session_penalty"),
        "session_penalty_reason": pf.get("session_penalty_reason"),
        "session_loss_rate": pf.get("session_loss_rate"),
        "session_trade_count": pf.get("session_trade_count"),
        "exit_reason_penalty": pf.get("exit_reason_penalty"),
        "exit_reason_penalty_reason": pf.get("exit_reason_penalty_reason"),
        "exit_reason_loss_rate": pf.get("exit_reason_loss_rate"),
        "exit_reason_trade_count": pf.get("exit_reason_trade_count"),
        "quality_tier": quality_tier.get("tier"),
        "quality_tier_label": quality_tier.get("label"),
        "quality_penalty_count": quality_tier.get("penalty_count"),
        "trend_context": trend_context,
        "setup_type": setup_meta.get("setup_type"),
        "setup_reason": setup_meta.get("setup_reason"),
        "trend_aligned": setup_meta.get("trend_aligned"),
        "reversal_confirmed": setup_meta.get("reversal_confirmed"),
        "continuation_confirmed": setup_meta.get("continuation_confirmed"),
        "policy_mode": setup_meta.get("policy_mode"),
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
    GEMINI_RUNTIME_STATE["enabled"] = GEMINI_ENABLED
    GEMINI_RUNTIME_STATE["model"] = GEMINI_MODEL
    GEMINI_RUNTIME_STATE["api_configured"] = bool(GEMINI_API_KEY)
    GEMINI_RUNTIME_STATE["binary_found"] = False
    GEMINI_RUNTIME_STATE["binary_path"] = None
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
    GEMINI_RUNTIME_STATE["api_configured"] = bool(GEMINI_API_KEY)
    GEMINI_RUNTIME_STATE["binary_found"] = False
    GEMINI_RUNTIME_STATE["binary_path"] = None
    if not GEMINI_API_KEY:
        GEMINI_RUNTIME_STATE["last_error"] = "gemini_api_key_missing"
        GEMINI_RUNTIME_STATE["last_decision_source"] = "fallback"
        _debug("Gemini API key missing, using fallback")
        return None

    prompt = _gemini_prompt(snapshot, pf)
    endpoint = f"{GEMINI_API_URL}/{GEMINI_MODEL}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "topP": 0.8,
            "topK": 20,
            "maxOutputTokens": 400,
            "responseMimeType": "application/json",
        },
    }
    try:
        with httpx.Client(timeout=45.0) as client:
            response = client.post(endpoint, params={"key": GEMINI_API_KEY}, json=payload)
        GEMINI_RUNTIME_STATE["last_http_status"] = response.status_code
        GEMINI_RUNTIME_STATE["last_return_code"] = 0 if response.is_success else response.status_code
        if not response.is_success:
            GEMINI_RUNTIME_STATE["last_error"] = response.text[:300]
            GEMINI_RUNTIME_STATE["last_decision_source"] = "fallback"
            _debug(f"Gemini API failed status={response.status_code}, body={response.text[:300]}")
            return None

        data = response.json()
        candidates = data.get("candidates") or []
        parts = (((candidates[0] or {}).get("content") or {}).get("parts") or []) if candidates else []
        raw = ""
        for part in parts:
            if isinstance(part, dict) and part.get("text"):
                raw += str(part.get("text"))
        raw = raw.strip()
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


def decide_trade(snapshot: dict):
    pf = prefilter(snapshot)
    if not pf["pass"]:
        return {"decision": "NO_TRADE", "confidence": 0.0, "reason": pf["reason"], "decision_source": "rule_gate", "quality_tier": "C", "quality_tier_label": "blocked_by_rule_gate", "quality_penalty_count": 0}

    fallback = decide_with_mock_gemini(snapshot)
    fallback["decision_source"] = "mock"
    deterministic_score = float(fallback.get("deterministic_score", fallback.get("confidence", 0.0)))
    adaptive_trade_threshold = float(fallback.get("adaptive_trade_threshold", DETERMINISTIC_SCORE_TRADE_THRESHOLD))
    adaptive_no_trade_threshold = float(fallback.get("adaptive_no_trade_threshold", DETERMINISTIC_SCORE_NO_TRADE_THRESHOLD))
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

        quality_tier = _quality_tier(fusion_score, pf)
        trend_context = _build_trend_context(pf)
        setup_meta = _classify_setup_type(pf, trend_context, quality_tier)
        gemini_result["quality_tier"] = quality_tier.get("tier")
        gemini_result["quality_tier_label"] = quality_tier.get("label")
        gemini_result["quality_penalty_count"] = quality_tier.get("penalty_count")
        gemini_result["trend_context"] = trend_context
        gemini_result["setup_type"] = setup_meta.get("setup_type")
        gemini_result["setup_reason"] = setup_meta.get("setup_reason")
        gemini_result["trend_aligned"] = setup_meta.get("trend_aligned")
        gemini_result["reversal_confirmed"] = setup_meta.get("reversal_confirmed")
        gemini_result["continuation_confirmed"] = setup_meta.get("continuation_confirmed")
        gemini_result["policy_mode"] = setup_meta.get("policy_mode")
        if gemini_result.get("decision") in {"BUY", "SELL"} and QUALITY_TIER_C_BLOCK_ENABLED and quality_tier.get("tier") == "C":
            return {
                "decision": "NO_TRADE",
                "confidence": fusion_score,
                "reason": f"quality_tier_block:C|fusion_score={fusion_score:.2f}|{gemini_result.get('reason')}",
                "entry": gemini_result.get("entry"),
                "symbol": gemini_result.get("symbol"),
                "timeframe": gemini_result.get("timeframe"),
                "decision_source": "quality_gate",
                "evaluation": evaluation,
                "deterministic_score": deterministic_score,
                "fusion_score": fusion_score,
                "adaptive_trade_threshold": adaptive_trade_threshold,
                "adaptive_no_trade_threshold": adaptive_no_trade_threshold,
                "trend_regime_reason": fallback.get("trend_regime_reason"),
                "trend_regime_score": fallback.get("trend_regime_score"),
                "trend_regime_alignment": fallback.get("trend_regime_alignment"),
                "trend_regime_opposing_count": fallback.get("trend_regime_opposing_count"),
                "trend_regime_strong_aligned": fallback.get("trend_regime_strong_aligned"),
                "trend_regime_close_position": fallback.get("trend_regime_close_position"),
                "quality_tier": quality_tier.get("tier"),
                "quality_tier_label": quality_tier.get("label"),
                "quality_penalty_count": quality_tier.get("penalty_count"),
            }
        if gemini_result.get("decision") in {"BUY", "SELL"} and setup_meta.get("setup_type") == "NO_TRADE":
            return {
                "decision": "NO_TRADE",
                "confidence": fusion_score,
                "reason": f"setup_type_block:{setup_meta.get('setup_reason')}|{gemini_result.get('reason')}",
                "entry": gemini_result.get("entry"),
                "symbol": gemini_result.get("symbol"),
                "timeframe": gemini_result.get("timeframe"),
                "decision_source": "setup_gate",
                "evaluation": evaluation,
                "deterministic_score": deterministic_score,
                "fusion_score": fusion_score,
                "adaptive_trade_threshold": adaptive_trade_threshold,
                "adaptive_no_trade_threshold": adaptive_no_trade_threshold,
                "trend_regime_reason": fallback.get("trend_regime_reason"),
                "trend_regime_score": fallback.get("trend_regime_score"),
                "trend_regime_alignment": fallback.get("trend_regime_alignment"),
                "trend_regime_opposing_count": fallback.get("trend_regime_opposing_count"),
                "trend_regime_strong_aligned": fallback.get("trend_regime_strong_aligned"),
                "trend_regime_close_position": fallback.get("trend_regime_close_position"),
                "quality_tier": quality_tier.get("tier"),
                "quality_tier_label": quality_tier.get("label"),
                "quality_penalty_count": quality_tier.get("penalty_count"),
                "trend_context": trend_context,
                "setup_type": setup_meta.get("setup_type"),
                "setup_reason": setup_meta.get("setup_reason"),
                "trend_aligned": setup_meta.get("trend_aligned"),
                "reversal_confirmed": setup_meta.get("reversal_confirmed"),
                "continuation_confirmed": setup_meta.get("continuation_confirmed"),
                "policy_mode": setup_meta.get("policy_mode"),
            }
        if gemini_result.get("decision") == fallback.get("decision"):
            gemini_result["deterministic_score"] = deterministic_score
            gemini_result["confidence"] = max(float(gemini_result.get("confidence", 0.0)), fusion_score)
            if fusion_score < adaptive_no_trade_threshold:
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
                    "deterministic_score": deterministic_score,
                    "fusion_score": fusion_score,
                    "adaptive_trade_threshold": adaptive_trade_threshold,
                    "adaptive_no_trade_threshold": adaptive_no_trade_threshold,
                    "trend_regime_reason": fallback.get("trend_regime_reason"),
                    "trend_regime_score": fallback.get("trend_regime_score"),
                    "trend_regime_alignment": fallback.get("trend_regime_alignment"),
                    "trend_regime_opposing_count": fallback.get("trend_regime_opposing_count"),
                    "trend_regime_strong_aligned": fallback.get("trend_regime_strong_aligned"),
                    "trend_regime_close_position": fallback.get("trend_regime_close_position"),
                }
            _debug(f"Hybrid decision aligned with fallback decision={gemini_result.get('decision')}")
            return gemini_result
        if gemini_result.get("decision") == "NO_TRADE":
            gemini_result["deterministic_score"] = deterministic_score
            gemini_result["fusion_score"] = fusion_score
            gemini_result["adaptive_trade_threshold"] = adaptive_trade_threshold
            gemini_result["adaptive_no_trade_threshold"] = adaptive_no_trade_threshold
            gemini_result["trend_regime_reason"] = fallback.get("trend_regime_reason")
            gemini_result["trend_regime_score"] = fallback.get("trend_regime_score")
            gemini_result["trend_regime_alignment"] = fallback.get("trend_regime_alignment")
            gemini_result["trend_regime_opposing_count"] = fallback.get("trend_regime_opposing_count")
            gemini_result["trend_regime_strong_aligned"] = fallback.get("trend_regime_strong_aligned")
            gemini_result["trend_regime_close_position"] = fallback.get("trend_regime_close_position")
            _debug("Hybrid decision downgraded to NO_TRADE by Gemini")
            return gemini_result
        if fusion_score >= GEMINI_OVERRIDE_CONFIDENCE and float(gemini_result.get("confidence", 0.0)) >= MIN_CONFIDENCE:
            gemini_result["reason"] = f"gemini_override|{gemini_result.get('reason')}"
            gemini_result["confidence"] = max(float(gemini_result.get("confidence", 0.0)), fusion_score)
            gemini_result["deterministic_score"] = deterministic_score
            gemini_result["fusion_score"] = fusion_score
            gemini_result["adaptive_trade_threshold"] = adaptive_trade_threshold
            gemini_result["adaptive_no_trade_threshold"] = adaptive_no_trade_threshold
            gemini_result["trend_regime_reason"] = fallback.get("trend_regime_reason")
            gemini_result["trend_regime_score"] = fallback.get("trend_regime_score")
            gemini_result["trend_regime_alignment"] = fallback.get("trend_regime_alignment")
            gemini_result["trend_regime_opposing_count"] = fallback.get("trend_regime_opposing_count")
            gemini_result["trend_regime_strong_aligned"] = fallback.get("trend_regime_strong_aligned")
            gemini_result["trend_regime_close_position"] = fallback.get("trend_regime_close_position")
            _debug(f"Hybrid override accepted decision={gemini_result.get('decision')} confidence={gemini_result.get('confidence')}")
            return gemini_result
        _debug("Hybrid override rejected, fallback kept")

    _debug(f"Fallback decision used decision={fallback.get('decision')} reason={fallback.get('reason')}")
    fallback["deterministic_score"] = deterministic_score
    fallback["adaptive_trade_threshold"] = adaptive_trade_threshold
    fallback["adaptive_no_trade_threshold"] = adaptive_no_trade_threshold
    return fallback
