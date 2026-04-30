from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Optional


def parse_iso_utc(value: Optional[str]):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def is_signal_fresh(signal: Optional[dict], active_signal_ttl_sec: int) -> bool:
    if not signal:
        return False
    ts = signal.get("timestamp_utc")
    if not ts:
        return False
    signal_dt = parse_iso_utc(ts)
    if signal_dt is None:
        return False
    return (datetime.now(timezone.utc) - signal_dt).total_seconds() <= active_signal_ttl_sec


def current_signal_summary(current_signal: Optional[dict], active_signal_ttl_sec: int) -> dict:
    signal_age_sec = None
    if current_signal:
        ts = parse_iso_utc(current_signal.get("timestamp_utc"))
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
        "fresh": is_signal_fresh(current_signal, active_signal_ttl_sec),
    }


def build_bridge_contract(data: dict):
    return {
        "signal_id": data.get("signal_id"),
        "symbol": data.get("symbol"),
        "side": data.get("side"),
        "timestamp_utc": data.get("timestamp_utc"),
        "stop_loss": data.get("stop_loss"),
        "entry_zone_min": ((data.get("entry_zone") or {}).get("min") if isinstance(data.get("entry_zone"), dict) else None),
        "entry_zone_max": ((data.get("entry_zone") or {}).get("max") if isinstance(data.get("entry_zone"), dict) else None),
        "tp1_price": (((data.get("take_profit") or [])[0] or {}).get("price") if isinstance(data.get("take_profit"), list) and len(data.get("take_profit")) > 0 and isinstance(data.get("take_profit")[0], dict) else None),
        "max_signal_age_sec": data.get("max_signal_age_sec"),
        "break_even_r_mult": (((data.get("market_context") or {}).get("trailing") or {}).get("break_even_r_mult") if isinstance((data.get("market_context") or {}).get("trailing"), dict) else None),
        "break_even_buffer_r_mult": (((data.get("market_context") or {}).get("trailing") or {}).get("break_even_buffer_r_mult") if isinstance((data.get("market_context") or {}).get("trailing"), dict) else None),
        "trailing_start_r_mult": (((data.get("market_context") or {}).get("trailing") or {}).get("trailing_start_r_mult") if isinstance((data.get("market_context") or {}).get("trailing"), dict) else None),
        "trailing_step_r_mult": (((data.get("market_context") or {}).get("trailing") or {}).get("trailing_step_r_mult") if isinstance((data.get("market_context") or {}).get("trailing"), dict) else None),
        "trailing_sl_r_mult": (((data.get("market_context") or {}).get("trailing") or {}).get("trailing_sl_r_mult") if isinstance((data.get("market_context") or {}).get("trailing"), dict) else None),
        "time_based_trailing_after_sec": (((data.get("market_context") or {}).get("trailing") or {}).get("time_based_after_sec") if isinstance((data.get("market_context") or {}).get("trailing"), dict) else None),
        "time_based_trailing_min_r_mult": (((data.get("market_context") or {}).get("trailing") or {}).get("time_based_min_r_mult") if isinstance((data.get("market_context") or {}).get("trailing"), dict) else None),
        "time_based_trailing_sl_r_mult": (((data.get("market_context") or {}).get("trailing") or {}).get("time_based_sl_r_mult") if isinstance((data.get("market_context") or {}).get("trailing"), dict) else None),
        "trailing_enabled": bool((((data.get("market_context") or {}).get("trailing") or {}).get("enabled")) if isinstance((data.get("market_context") or {}).get("trailing"), dict) else False),
    }


def signal_staleness(data: dict):
    signal_age_sec = None
    is_stale = None
    issue = None
    try:
        ts = data.get("timestamp_utc")
        max_age = float(data.get("max_signal_age_sec") or 0)
        if ts:
            signal_dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            signal_age_sec = round((datetime.now(timezone.utc) - signal_dt).total_seconds(), 2)
            is_stale = bool(max_age > 0 and signal_age_sec > max_age)
    except Exception:
        issue = "timestamp_invalid"
    return {"signal_age_sec": signal_age_sec, "is_stale": is_stale, "issue": issue}


def apply_execution_reject(snapshot_state: dict, payload: dict, save_runtime_state: Callable[[], None]) -> dict:
    event = dict(payload)
    event["type"] = "execution_reject"
    event["at"] = datetime.now(timezone.utc).isoformat()
    snapshot_state["last_no_trade_at"] = event["at"]
    snapshot_state["last_no_trade_reason"] = payload.get("reason")
    snapshot_state["last_no_trade_symbol"] = payload.get("symbol")
    save_runtime_state()
    return event


def apply_execution_report(
    snapshot_state: dict,
    payload: dict,
    current_signal: Optional[dict],
    store_signal_payload: Callable[[dict], None],
    save_runtime_state: Callable[[], None],
    parse_iso_utc_fn: Callable[[Optional[str]], Any],
    session_bucket_cooldown_enabled: bool,
    session_bucket_cooldown_threshold: int,
    session_bucket_cooldown_sec: int,
    slippage_cooldown_enabled: bool,
    slippage_cooldown_window_sec: int,
    slippage_cooldown_sec: int,
):
    report_kind = str(payload.get("type", "")).upper()
    event = dict(payload)
    event["event_type"] = "execution_report"
    event["at"] = datetime.now(timezone.utc).isoformat()

    snapshot_state["last_execution_at"] = event["at"]
    snapshot_state["last_execution_signal_id"] = payload.get("signal_id")
    snapshot_state["last_execution_type"] = report_kind
    snapshot_state["last_execution_ticket"] = payload.get("ticket")
    if payload.get("exit_reason") is not None:
        snapshot_state["last_exit_reason"] = payload.get("exit_reason")
    if payload.get("initial_risk_price") is not None:
        snapshot_state["last_trailing_initial_risk_price"] = payload.get("initial_risk_price")
    if payload.get("initial_stop_loss") is not None:
        snapshot_state["last_trailing_initial_stop_loss"] = payload.get("initial_stop_loss")
    if payload.get("initial_tp1") is not None:
        snapshot_state["last_trailing_initial_tp1"] = payload.get("initial_tp1")
    if payload.get("last_applied_stop_loss") is not None:
        snapshot_state["last_trailing_last_applied_stop_loss"] = payload.get("last_applied_stop_loss")
    if payload.get("break_even_activated") is not None:
        snapshot_state["last_break_even_activated"] = payload.get("break_even_activated")
    if payload.get("trailing_activated") is not None:
        snapshot_state["last_trailing_activated"] = payload.get("trailing_activated")

    if current_signal and current_signal.get("signal_id") == payload.get("signal_id"):
        if report_kind == "OPEN":
            current_signal["status"] = "OPEN"
            current_signal["executed_ticket"] = payload.get("ticket")
            current_signal["executed_at"] = event["at"]
            store_signal_payload(current_signal)
        elif report_kind in {"CLOSE", "CLOSED", "EXIT"}:
            current_signal["status"] = "CLOSED"
            current_signal["closed_at"] = event["at"]
            outcome = str(payload.get("outcome", payload.get("result", ""))).upper()
            pnl = payload.get("pnl")
            if outcome:
                current_signal["outcome"] = outcome
            if pnl is not None:
                current_signal["pnl"] = pnl
            if payload.get("exit_reason") is not None:
                current_signal["exit_reason"] = payload.get("exit_reason")
            side = current_signal.get("side")
            if outcome in {"LOSS", "SL", "STOP_LOSS", "NEGATIVE"}:
                snapshot_state["last_trade_outcome"] = outcome
                snapshot_state["last_loss_side"] = side
                snapshot_state["last_loss_at"] = event["at"]
                losses = snapshot_state.setdefault("consecutive_losses", {"BUY": 0, "SELL": 0})
                losses[side] = int(losses.get(side, 0)) + 1
                market_context = current_signal.get("market_context") if isinstance(current_signal.get("market_context"), dict) else {}
                pattern_key = "|".join([
                    str(current_signal.get("side") or ""),
                    str(current_signal.get("pattern_structure_reason") or current_signal.get("structure_reason") or market_context.get("structure_reason") or "unknown_structure"),
                    str(current_signal.get("pattern_trend_regime_reason") or current_signal.get("trend_regime_reason") or market_context.get("trend_regime_reason") or "unknown_trend"),
                ])
                recent_patterns = snapshot_state.setdefault("recent_loss_patterns", [])
                recent_patterns.append({
                    "at": event["at"],
                    "pattern_key": pattern_key,
                    "signal_id": current_signal.get("signal_id"),
                    "side": side,
                    "outcome": outcome,
                })
                snapshot_state["recent_loss_patterns"] = recent_patterns[-50:]
                session_bucket = str((current_signal.get("market_context") or {}).get("trailing", {}).get("session_bucket") or current_signal.get("session_bucket") or "UNKNOWN")
                if session_bucket_cooldown_enabled:
                    losses = snapshot_state.setdefault("consecutive_losses", {"BUY": 0, "SELL": 0})
                    if int(losses.get(side, 0) or 0) >= session_bucket_cooldown_threshold:
                        cooldowns = snapshot_state.setdefault("session_cooldowns", {})
                        cooldowns[session_bucket] = (datetime.now(timezone.utc) + timedelta(seconds=session_bucket_cooldown_sec)).isoformat()
                        snapshot_state["session_cooldowns"] = cooldowns
                exit_reason = str(payload.get("exit_reason") or "").upper()
                if slippage_cooldown_enabled and exit_reason == "GAP_SLIPPAGE_SL":
                    now_dt = datetime.now(timezone.utc)
                    recent_slippage = snapshot_state.setdefault("recent_slippage_events", [])
                    recent_slippage.append({
                        "at": event["at"],
                        "signal_id": current_signal.get("signal_id"),
                        "side": side,
                        "exit_reason": exit_reason,
                    })
                    kept = []
                    for item in recent_slippage:
                        at_dt = parse_iso_utc_fn(item.get("at"))
                        if at_dt is None:
                            continue
                        if (now_dt - at_dt).total_seconds() <= slippage_cooldown_window_sec:
                            kept.append(item)
                    snapshot_state["recent_slippage_events"] = kept[-20:]
                    if len(kept) >= session_bucket_cooldown_threshold:
                        snapshot_state["slippage_cooldown_until"] = (now_dt + timedelta(seconds=slippage_cooldown_sec)).isoformat()
            elif outcome in {"WIN", "TP", "TAKE_PROFIT", "POSITIVE", "BREAKEVEN", "BE"}:
                snapshot_state["last_trade_outcome"] = outcome
                losses = snapshot_state.setdefault("consecutive_losses", {"BUY": 0, "SELL": 0})
                if side in losses:
                    losses[side] = 0
                if outcome in {"WIN", "TP", "TAKE_PROFIT", "POSITIVE"}:
                    snapshot_state["last_loss_side"] = None
                    snapshot_state["last_loss_at"] = None
            current_signal["pattern_structure_reason"] = current_signal.get("pattern_structure_reason") or current_signal.get("structure_reason") or current_signal.get("market_context", {}).get("structure_reason")
            current_signal["pattern_trend_regime_reason"] = current_signal.get("pattern_trend_regime_reason") or current_signal.get("trend_regime_reason") or current_signal.get("market_context", {}).get("trend_regime_reason")
            store_signal_payload(current_signal)

    save_runtime_state()
    return event, current_signal
