"""Tests for dashboard JSONL row selection (post_ops / last-row preference)."""

from tools.dashboard.jsonl_rows import select_row_for_step, series_by_step


def test_select_row_for_step_prefers_post_ops():
    rows = [
        {"step": 2, "co2_storage_kg": 1.0},
        {"step": 2, "co2_storage_kg": 0.7, "post_ops": True},
        {"step": 3, "co2_storage_kg": 0.9},
    ]
    chosen = select_row_for_step(rows, 2)
    assert chosen is not None
    assert chosen["co2_storage_kg"] == 0.7
    assert chosen.get("post_ops") is True


def test_select_row_for_step_falls_back_to_last_match():
    rows = [
        {"step": 1, "value": "a"},
        {"step": 1, "value": "b"},
    ]
    chosen = select_row_for_step(rows, 1)
    assert chosen is not None
    assert chosen["value"] == "b"


def test_series_by_step_dedupes_preferring_post_ops():
    rows = [
        {"step": 0, "co2_storage_kg": 1.5},
        {"step": 0, "co2_storage_kg": 1.2, "post_ops": True},
        {"step": 1, "co2_storage_kg": 1.1},
        {"step": 1, "co2_storage_kg": 1.0, "post_ops": True},
    ]
    series = series_by_step(rows)
    assert [r["step"] for r in series] == [0, 1]
    assert [r["co2_storage_kg"] for r in series] == [1.2, 1.0]
