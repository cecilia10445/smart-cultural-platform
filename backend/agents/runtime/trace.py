"""In-memory, summary-only runtime audit trail."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .models import RuntimeUsage, TraceRecord, ToolRisk


def canonical_arguments(arguments: dict[str, Any]) -> str:
    return json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def arguments_hash(arguments: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_arguments(arguments).encode("utf-8")).hexdigest()


def fields_summary(value: Any) -> dict[str, Any]:
    """Return types and field names only, never parameter or output values."""
    if isinstance(value, dict):
        return {"kind": "object", "fields": sorted(str(key) for key in value)}
    if isinstance(value, list):
        return {"kind": "list", "length": len(value)}
    return {"kind": type(value).__name__}


class TraceRecorder:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self._records: list[TraceRecord] = []

    @property
    def records(self) -> list[TraceRecord]:
        return list(self._records)

    def add(self, event_type: str, usage: RuntimeUsage, **details: Any) -> TraceRecord:
        record = TraceRecord(
            run_id=self.run_id,
            step=len(self._records) + 1,
            event_type=event_type,
            budget_snapshot=usage.snapshot(),
            **details,
        )
        self._records.append(record)
        return record
