"""
Parse/clean core for the CCC traffic-count ETL.

Turns one downloaded workbook into cleaned records, and — crucially — handles the
non-vehicle files the Drive folder mixes in (pedestrian counts, blank "Turning
Count Template" workbooks, summaries) that the parser legitimately can't read.
The probe showed 10/11 sampled years parse cleanly; the misses are those other
file types, so one odd file must never break a batch.

Wraps ``traffic_counts_parser.parse_xlsx`` (validated across 2016-2026 for the
standard intersection vehicle-count workbooks). ``parse_xlsx`` raises when a
workbook has no vehicle metric grid; ``clean_workbook`` catches that and returns
a REJECTED result carrying the reason, instead of raising.

Design notes:
- ``parse_xlsx`` is *injectable* so this module is unit-testable with a fake and
  no openpyxl/parser import (see tests/test_counts_etl.py). The real parser is
  imported lazily inside ``_load_parser`` only when actually parsing.
- The real parser module runs a venv re-exec at import; the Lambda packaging step
  (Step 3) neutralises that. This module doesn't trigger it until parse time.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class CleanResult:
    """Outcome of cleaning one workbook."""

    path: str
    status: str                              # "ok" | "rejected"
    rows: list[dict[str, Any]] = field(default_factory=list)
    row_count: int = 0
    reason: str = ""                         # populated when status == "rejected"

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def _load_parser() -> Callable[..., list[dict[str, Any]]]:
    """Import the real parser lazily (keeps this module import-light/testable)."""
    from traffic_counts_parser import parse_xlsx

    return parse_xlsx


def _first_line(text: str) -> str:
    return (text.splitlines()[0] if text else "").strip()[:200]


def clean_workbook(
    path,
    *,
    parse_xlsx: Callable[..., list[dict[str, Any]]] | None = None,
) -> CleanResult:
    """Parse one workbook into records, or reject it with a reason.

    A standard vehicle-count workbook yields rows -> ``status="ok"``. A file the
    parser can't read (pedestrian count, template, summary, corrupt) is returned
    as ``status="rejected"`` with the reason — never raised — so a batch run can
    quarantine it and carry on.

    ``parse_xlsx`` is injectable for testing; defaults to the real parser.
    """
    p = Path(path)
    fn = parse_xlsx or _load_parser()
    try:
        rows = fn(p)
    except Exception as exc:  # noqa: BLE001 - parser raises ValueError on layout mismatch
        return CleanResult(path=str(p), status="rejected", reason=_first_line(str(exc)))
    if not rows:
        return CleanResult(path=str(p), status="rejected", reason="parser returned 0 rows")
    return CleanResult(path=str(p), status="ok", rows=rows, row_count=len(rows))


def to_processed_payload(result: CleanResult, *, source: dict[str, Any] | None = None) -> dict[str, Any]:
    """Shape an OK result into the processed-data document written to S3."""
    return {
        "source": source or {},          # drive id/name/folder/modifiedTime, set by the Lambda
        "rowCount": result.row_count,
        "rows": result.rows,
    }


def to_json_bytes(result: CleanResult, *, source: dict[str, Any] | None = None) -> bytes:
    """Serialise the processed payload to compact UTF-8 JSON bytes (for S3)."""
    return json.dumps(
        to_processed_payload(result, source=source), separators=(",", ":"), default=str
    ).encode("utf-8")
