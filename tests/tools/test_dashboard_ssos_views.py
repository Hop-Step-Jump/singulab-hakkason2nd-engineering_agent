"""Tests for ssos_eclss_loop / plant_sim dashboard helpers."""

from pathlib import Path

from tools.dashboard.app import _build_line_plot_figure, _read_jsonl
from tools.dashboard import ssos_views


def test_filter_ssos_operational_events_includes_water_recovery():
    events = [
        {"command": {"kind": "air_revitalisation"}},
        {"command": {"kind": "water_recovery"}},
        {"command": {"kind": "request_eps_boost"}},
        {"command": {"kind": "oxygen_generation"}},
    ]
    filtered = ssos_views.filter_ssos_operational_events(events)
    kinds = [e["command"]["kind"] for e in filtered]
    assert kinds == ["air_revitalisation", "water_recovery", "oxygen_generation"]


def test_plant_sim_series_extracts_ledgers():
    rows = [
        {
            "step": 1,
            "co2_storage_kg": 1.5,
            "grey_water_collected_l": 0.1,
            "raw_topics": {
                "plant_sim": {
                    "captured_co2_kg": 0.2,
                    "urine_buffer_l": 0.3,
                    "total_o2_shortfall_kg": 0.0,
                }
            },
        },
        {
            "step": 1,
            "co2_storage_kg": 1.4,
            "grey_water_collected_l": 0.2,
            "post_ops": True,
            "raw_topics": {
                "plant_sim": {
                    "captured_co2_kg": 0.25,
                    "urine_buffer_l": 0.0,
                    "total_o2_shortfall_kg": 0.01,
                }
            },
        },
        {"step": 2, "co2_storage_kg": 1.3},
    ]
    series = ssos_views.plant_sim_series(rows)
    assert [row["step"] for row in series] == [1]
    assert series[0]["captured_co2_kg"] == 0.25
    assert series[0]["urine_buffer_l"] == 0.0
    assert series[0]["grey_water_collected_l"] == 0.2
    assert series[0]["total_o2_shortfall_kg"] == 0.01


def test_build_line_plot_figure_skips_plant_sim_telemetry():
    run_dir = Path("src/experiments/results/plant-sim-pytest-smoke")
    if not (run_dir / "telemetry.jsonl").exists():
        telemetry = [
            {
                "step": 1,
                "co2_storage_kg": 1.5,
                "o2_storage_kg": 0.5,
                "product_water_reserve_l": 100.0,
                "raw_topics": {"plant_sim": {"captured_co2_kg": 0.0}},
            }
        ]
    else:
        telemetry = _read_jsonl(run_dir / "telemetry.jsonl")
    assert _build_line_plot_figure(telemetry, []) is None


def test_is_ssos_eclss_loop_detects_plant_sim_summary():
    assert ssos_views.is_ssos_eclss_loop(
        {"scenario": "ssos_eclss_loop", "backend": "plant_sim"}
    )
    assert not ssos_views.is_ssos_eclss_loop({"scenario": "scrubber_degradation"})
