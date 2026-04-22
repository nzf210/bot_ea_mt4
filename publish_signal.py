import json
import os
import sys
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(__file__)
load_dotenv(os.path.join(BASE_DIR, ".env"))

AI4TRADE_TOKEN = os.getenv("AI4TRADE_TOKEN", "")
AI4TRADE_PUBLISH_URL = os.getenv("AI4TRADE_PUBLISH_URL", "https://ai4trade.ai/api/signals/realtime")
DEFAULT_MARKET = os.getenv("AI4TRADE_PUBLISH_MARKET", "forex")
DEFAULT_QUANTITY = float(os.getenv("AI4TRADE_PUBLISH_QUANTITY", "0.01"))


def build_payload(signal: dict) -> dict:
    symbol = str(signal.get("symbol", "")).upper()
    side = str(signal.get("side", signal.get("action", ""))).lower()
    price = signal.get("price")
    if price is None:
        entry_zone = signal.get("entry_zone") or {}
        if isinstance(entry_zone, dict):
            lo = entry_zone.get("min")
            hi = entry_zone.get("max")
            if lo is not None and hi is not None:
                price = (float(lo) + float(hi)) / 2.0
    if price is None:
        raise ValueError("signal price missing")

    executed_at = signal.get("executed_at") or signal.get("timestamp_utc") or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    quantity = float(signal.get("quantity", DEFAULT_QUANTITY))

    content_parts = []
    for key in ["timeframe", "stop_loss", "confidence", "invalidation"]:
        if signal.get(key) is not None:
            content_parts.append(f"{key}={signal.get(key)}")
    take_profit = signal.get("take_profit")
    if isinstance(take_profit, list) and take_profit:
        for idx, tp in enumerate(take_profit, start=1):
            if isinstance(tp, dict) and tp.get("price") is not None:
                content_parts.append(f"TP{idx}={tp.get('price')}")

    return {
        "market": signal.get("market", DEFAULT_MARKET),
        "action": side,
        "symbol": symbol,
        "price": float(price),
        "quantity": quantity,
        "content": " | ".join(content_parts) if content_parts else signal.get("content"),
        "executed_at": executed_at,
        "token_id": signal.get("token_id"),
        "outcome": signal.get("outcome"),
    }


def main():
    if not AI4TRADE_TOKEN:
        raise SystemExit("AI4TRADE_TOKEN is not set in .env")
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python publish_signal.py <signal.json>")

    input_path = sys.argv[1]
    with open(input_path, "r", encoding="utf-8") as f:
        signal = json.load(f)

    payload = build_payload(signal)
    headers = {
        "Authorization": f"Bearer {AI4TRADE_TOKEN}",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=20) as client:
        response = client.post(AI4TRADE_PUBLISH_URL, headers=headers, json=payload)
        print(response.status_code)
        print(response.text)
        response.raise_for_status()


if __name__ == "__main__":
    main()
