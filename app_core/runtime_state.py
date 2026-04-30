from __future__ import annotations

from typing import Any, Callable

from app_core.storage import read_json_file, write_json_file


def save_runtime_state(
    runtime_state_file: str,
    snapshot_state: dict,
    ai4trade_state: dict,
    get_gemini_runtime_state: Callable[[], dict],
) -> None:
    from datetime import datetime, timezone

    payload = {
        "snapshot_state": snapshot_state,
        "ai4trade_state": ai4trade_state,
        "gemini_runtime_state": get_gemini_runtime_state(),
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json_file(runtime_state_file, payload)


def load_runtime_state(
    runtime_state_file: str,
    snapshot_state: dict,
    ai4trade_state: dict,
    set_gemini_runtime_state: Callable[[dict], Any],
) -> dict:
    payload = read_json_file(runtime_state_file, default=None)
    if not isinstance(payload, dict):
        return {
            "restored": False,
            "source": None,
            "saved_at": None,
            "error": None,
        }

    if isinstance(payload.get("snapshot_state"), dict):
        snapshot_state.update(payload["snapshot_state"])
    if isinstance(payload.get("ai4trade_state"), dict):
        ai4trade_state.update(payload["ai4trade_state"])
    if isinstance(payload.get("gemini_runtime_state"), dict):
        set_gemini_runtime_state(payload["gemini_runtime_state"])

    return {
        "restored": True,
        "source": runtime_state_file,
        "saved_at": payload.get("saved_at"),
        "error": None,
    }
