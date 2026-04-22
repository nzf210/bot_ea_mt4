import json
import os
import time
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
from gemini_decider import decide_trade

BASE_DIR = os.path.dirname(__file__)
load_dotenv(os.path.join(BASE_DIR, ".env"))

SNAPSHOT_STORE = os.getenv("MARKET_SNAPSHOT_STORE", os.path.join(BASE_DIR, "latest_market_snapshot.json"))
LOOP_SECONDS = int(os.getenv("AI_SIGNAL_LOOP_SECONDS", "30"))
STATE_FILE = os.getenv("AI_SIGNAL_STATE_FILE", os.path.join(BASE_DIR, "ai_signal_state.json"))
PUBLISH_ON_VALID = os.getenv("AI_SIGNAL_PUBLISH_ENABLED", "true").lower() in {"1", "true", "yes", "on"}


def load_state():
    p = Path(STATE_FILE)
    if not p.exists():
        return {"last_keys": {}}
    return json.loads(p.read_text(encoding="utf-8"))


def save_state(state):
    Path(STATE_FILE).write_text(json.dumps(state, indent=2), encoding="utf-8")


def build_signal(symbol: str, decision: str, entry: float, timeframe: str, confidence: float, reason: str):
    if symbol == "XAUUSD":
        zone = 0.3
        sl_offset = 5.0
        tp1_offset = 8.0
        tp2_offset = 12.0
        digits = 2
    else:
        zone = 0.0005
        sl_offset = 0.0030
        tp1_offset = 0.0050
        tp2_offset = 0.0080
        digits = 5

    sl = entry - sl_offset if decision == "BUY" else entry + sl_offset
    tp1 = entry + tp1_offset if decision == "BUY" else entry - tp1_offset
    tp2 = entry + tp2_offset if decision == "BUY" else entry - tp2_offset

    return {
        "symbol": symbol,
        "side": decision,
        "timeframe": timeframe,
        "entry_zone": {"min": round(entry - zone, digits), "max": round(entry + zone, digits)},
        "stop_loss": round(sl, digits),
        "take_profit": [
            {"label": "TP1", "price": round(tp1, digits), "close_pct": 0.5},
            {"label": "TP2", "price": round(tp2, digits), "close_pct": 0.5},
        ],
        "confidence": confidence,
        "invalidation": f"AI loop: {reason}",
        "quantity": 0.01,
        "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def main():
    print(f"AI signal loop started, every {LOOP_SECONDS}s")
    state = load_state()
    while True:
        try:
            if os.path.exists(SNAPSHOT_STORE):
                data = json.loads(Path(SNAPSHOT_STORE).read_text(encoding='utf-8'))
                for snap in data.get("snapshots", []):
                    result = decide_trade(snap)
                    if result.get("decision") in {"BUY", "SELL"}:
                        normalized_symbol = result.get("symbol", snap["symbol"])
                        key = f"{normalized_symbol}:{result['decision']}:{result['entry']}"
                        if state["last_keys"].get(normalized_symbol) == key:
                            continue
                        signal = build_signal(normalized_symbol, result['decision'], result['entry'], result['timeframe'], result['confidence'], result['reason'])
                        out = Path(BASE_DIR) / "generated_ai_signal.json"
                        out.write_text(json.dumps(signal, indent=2), encoding='utf-8')
                        print(f"Generated valid signal for {normalized_symbol}: {result['decision']}")
                        if PUBLISH_ON_VALID:
                            cmd = [sys.executable, str(Path(BASE_DIR) / 'publish_signal.py'), str(out)]
                            r = subprocess.run(cmd, capture_output=True, text=True)
                            print(r.stdout)
                            if r.stderr:
                                print(r.stderr)
                        state["last_keys"][normalized_symbol] = key
                        save_state(state)
        except Exception as e:
            print(f"AI loop error: {e}")
        time.sleep(LOOP_SECONDS)


if __name__ == '__main__':
    main()
