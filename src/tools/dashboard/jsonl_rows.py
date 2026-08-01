"""Helpers for reading run JSONL rows that may repeat the same step.

ssos_eclss_loop L5 may append a second telemetry / health_metrics row for a step
with ``post_ops: true`` after operational commands. Readers should prefer that
row (or otherwise the last matching row) so UI matches ``summary.json``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def select_row_for_step(
    rows: List[Dict[str, Any]],
    step: int,
) -> Optional[Dict[str, Any]]:
    """Return the row for ``step``, preferring ``post_ops: true``, else the last match."""
    matches = [r for r in rows if int(r.get("step", -1)) == int(step)]
    if not matches:
        return None
    for row in reversed(matches):
        if row.get("post_ops") is True:
            return row
    return matches[-1]


def series_by_step(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Collapse to one row per step for charts (post_ops / last write wins)."""
    by_step: Dict[int, Dict[str, Any]] = {}
    order: List[int] = []
    for row in rows:
        if "step" not in row:
            continue
        step = int(row["step"])
        prev = by_step.get(step)
        if prev is None:
            by_step[step] = row
            order.append(step)
            continue
        if row.get("post_ops") is True or prev.get("post_ops") is not True:
            by_step[step] = row
    return [by_step[step] for step in sorted(order)]
