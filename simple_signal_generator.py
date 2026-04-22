import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(__file__)
load_dotenv(os.path.join(BASE_DIR, ".env"))

DEFAULT_SYMBOL = os.getenv("GENERATOR_SYMBOL", "XAUUSD")
DEFAULT_TIMEFRAME = os.getenv("GENERATOR_TIMEFRAME", "M15")
DEFAULT_QUANTITY = float(os.getenv("AI4TRADE_PUBLISH_QUANTITY", "0.01"))
DEFAULT_CONFIDENCE = float(os.getenv("GENERATOR_CONFIDENCE", "0.6"))


def build_signal(symbol: str, side: str, price: float) -> dict:
    symbol = symbol.upper()
    side = side.upper()
    if symbol == "XAUUSD":
        stop_offset = 5.0
        tp1_offset = 8.0
        tp2_offset = 12.0
        zone = 0.3
        round_digits = 2
    else:
        stop_offset = 0.0030
        tp1_offset = 0.0050
        tp2_offset = 0.0080
        zone = 0.0005
        round_digits = 5

    stop_loss = price - stop_offset if side == "BUY" else price + stop_offset
    tp1 = price + tp1_offset if side == "BUY" else price - tp1_offset
    tp2 = price + tp2_offset if side == "BUY" else price - tp2_offset

    return {
        "symbol": symbol,
        "side": side,
        "timeframe": DEFAULT_TIMEFRAME,
        "entry_zone": {
            "min": round(price - zone, round_digits),
            "max": round(price + zone, round_digits),
        },
        "stop_loss": round(stop_loss, round_digits),
        "take_profit": [
            {"label": "TP1", "price": round(tp1, round_digits), "close_pct": 0.5},
            {"label": "TP2", "price": round(tp2, round_digits), "close_pct": 0.5},
        ],
        "confidence": DEFAULT_CONFIDENCE,
        "invalidation": f"Auto-generated simple signal for {symbol}",
        "quantity": DEFAULT_QUANTITY,
        "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def main():
    if len(sys.argv) < 3:
        raise SystemExit("Usage: python simple_signal_generator.py <BUY|SELL> <price> [symbol]")

    side = sys.argv[1].upper()
    if side not in {"BUY", "SELL"}:
        raise SystemExit("side must be BUY or SELL")

    price = float(sys.argv[2])
    symbol = sys.argv[3].upper() if len(sys.argv) > 3 else DEFAULT_SYMBOL

    signal = build_signal(symbol, side, price)
    out_path = Path(BASE_DIR) / "generated_signal.json"
    out_path.write_text(json.dumps(signal, indent=2), encoding="utf-8")

    print(f"Generated signal saved to {out_path}")
    print(json.dumps(signal, indent=2))

    publisher = Path(BASE_DIR) / "publish_signal.py"
    cmd = [sys.executable, str(publisher), str(out_path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    print("\n=== publish_signal.py output ===")
    print(result.stdout)
    if result.stderr:
        print(result.stderr)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
