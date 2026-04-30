from __future__ import annotations

from typing import List, Literal, Optional
from pydantic import BaseModel, Field


TerminalPlatform = Literal["mt4", "mt5", "unknown"]
SignalSide = Literal["BUY", "SELL"]
ExecutionType = Literal["OPEN", "CLOSE", "CLOSED", "EXIT", "REJECT"]


class TerminalMeta(BaseModel):
    platform: TerminalPlatform = "unknown"
    terminal_id: Optional[str] = None
    adapter_version: Optional[str] = None
    broker: Optional[str] = None
    account_login: Optional[str] = None
    symbol_raw: Optional[str] = None


class EntryZone(BaseModel):
    min: float
    max: float


class TakeProfit(BaseModel):
    label: str
    price: float
    close_pct: float = Field(gt=0, le=1)


class MarketContext(BaseModel):
    spread_max_points: int = 35
    session: str = "LONDON_NY_OVERLAP"
    news_block_minutes: int = 30


class BridgeSignal(BaseModel):
    signal_id: str
    timestamp_utc: str
    symbol: str
    timeframe: str
    side: SignalSide
    entry_zone: EntryZone
    stop_loss: float
    take_profit: List[TakeProfit]
    confidence: float = Field(ge=0, le=1)
    invalidation: Optional[str] = ""
    max_signal_age_sec: int = 180
    market_context: MarketContext = MarketContext()
    terminal: TerminalMeta = TerminalMeta()


class OHLC(BaseModel):
    open: float
    high: float
    low: float
    close: float


class SnapshotCandle(BaseModel):
    shift: int = 0
    open: float
    high: float
    low: float
    close: float
    volume: float = 0


class MarketSnapshot(BaseModel):
    symbol: str
    timeframe: str = "M1"
    bid: float
    ask: float
    spread_points: int
    ohlc: OHLC
    volume: float = 0
    recent_candles: List[SnapshotCandle] = []
    terminal: TerminalMeta = TerminalMeta()


class SnapshotBatch(BaseModel):
    timestamp_utc: str
    snapshots: List[MarketSnapshot]


class ExecutionReport(BaseModel):
    signal_id: str
    type: ExecutionType
    ticket: Optional[int] = None
    symbol: Optional[str] = None
    side: Optional[str] = None
    lot: Optional[float] = None
    price: Optional[float] = None
    outcome: Optional[str] = None
    result: Optional[str] = None
    pnl: Optional[float] = None
    exit_reason: Optional[str] = None
    initial_risk_price: Optional[float] = None
    initial_stop_loss: Optional[float] = None
    initial_tp1: Optional[float] = None
    last_applied_stop_loss: Optional[float] = None
    break_even_activated: Optional[bool] = None
    trailing_activated: Optional[bool] = None
    terminal: TerminalMeta = TerminalMeta()


class ExecutionReject(BaseModel):
    signal_id: str
    symbol: Optional[str] = None
    side: Optional[str] = None
    reason: str
    price: Optional[float] = None
    entry_zone_min: Optional[float] = None
    entry_zone_max: Optional[float] = None
    terminal: TerminalMeta = TerminalMeta()
