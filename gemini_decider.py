import json
import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(__file__)
load_dotenv(os.path.join(BASE_DIR, ".env"))

ALLOWED_SYMBOLS = {s.strip().upper() for s in os.getenv("AI4TRADE_ALLOWED_SYMBOLS", "XAUUSD,GBPUSD,EURUSD").split(",") if s.strip()}
SYMBOL_ALIASES = {
    "GOLD": "XAUUSD",
}


def normalize_symbol(symbol: str) -> str:
    return SYMBOL_ALIASES.get((symbol or "").upper(), (symbol or "").upper())


def prefilter(snapshot: dict):
    bid = float(snapshot["bid"])
    ask = float(snapshot["ask"])
    close = float(snapshot["ohlc"]["close"])
    open_ = float(snapshot["ohlc"]["open"])
    spread = int(snapshot.get("spread_points", 999))
    symbol = normalize_symbol(snapshot["symbol"])

    if symbol not in ALLOWED_SYMBOLS:
        return {"pass": False, "reason": "symbol_not_allowed"}
    if spread > 35:
        return {"pass": False, "reason": "spread_too_high"}

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
