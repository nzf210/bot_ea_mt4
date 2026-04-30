from __future__ import annotations

from app_core.contracts.terminal import BridgeSignal, ExecutionReject, ExecutionReport, MarketSnapshot, SnapshotBatch


def upgrade_signal_payload(payload: dict) -> dict:
    data = dict(payload)
    data.setdefault("terminal", {})
    data["terminal"].setdefault("platform", "mt4")
    return BridgeSignal.model_validate(data).model_dump()


def upgrade_snapshot_batch_payload(payload: dict) -> dict:
    data = dict(payload)
    snapshots = []
    for item in data.get("snapshots", []) or []:
        row = dict(item)
        row.setdefault("terminal", {})
        row["terminal"].setdefault("platform", "mt4")
        snapshots.append(row)
    data["snapshots"] = snapshots
    return SnapshotBatch.model_validate(data).model_dump()


def upgrade_execution_report_payload(payload: dict) -> dict:
    data = dict(payload)
    data.setdefault("terminal", {})
    data["terminal"].setdefault("platform", "mt4")
    return ExecutionReport.model_validate(data).model_dump(exclude_none=True)


def upgrade_execution_reject_payload(payload: dict) -> dict:
    data = dict(payload)
    data.setdefault("terminal", {})
    data["terminal"].setdefault("platform", "mt4")
    return ExecutionReject.model_validate(data).model_dump(exclude_none=True)
