"""Baseline regression guard for scrubber_degradation scenario."""

from __future__ import annotations

import json
from pathlib import Path

from scenario.runner import run_scenario


def _read_jsonl(path: Path) -> list:
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def test_scrubber_degradation_baseline_runs(tmp_path: Path):
    run_dir = run_scenario(
        "scrubber_degradation",
        output_dir=tmp_path / "baseline",
        recreate_output=True,
    )

    telemetry = _read_jsonl(run_dir / "telemetry.jsonl")
    health = _read_jsonl(run_dir / "health_metrics.jsonl")
    events = _read_jsonl(run_dir / "events.jsonl")
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))

    assert len(telemetry) == 50
    assert len(health) == 50
    assert (run_dir / "design_state.jsonl").exists()

    anomaly_steps = [row for row in telemetry if "scrubber_degradation" in row.get("anomaly_flags", [])]
    assert anomaly_steps, "anomaly should activate by step 20"
    assert min(row["step"] for row in anomaly_steps) == 20

    from environment.scrubber.eclss_ops.telemetry import CO2_SAFE_PPM

    assert summary["peak_co2_ppm"] > CO2_SAFE_PPM, "CO2 should exceed safe band for demo narrative"
    assert summary["anomaly_seen"] is True
    assert summary["co2_above_threshold_step"] is not None
    assert (run_dir / "scenario_config.yaml").exists()
    assert summary["scenario_config_path"] == str(run_dir / "scenario_config.yaml")
    assert "agents_config_path" not in summary  # baseline mode is none
    assert summary["co2_above_threshold_step"] >= 20

    assert any("scrubber_degradation" in str(e) for e in events) or len(anomaly_steps) > 0
    injected = [e for e in events if e.get("kind") == "anomaly_injected"]
    assert len(injected) == 1, "anomaly_injected should be logged once per run"
    assert injected[0]["step"] == 0
    assert (run_dir / "provenance.jsonl").exists()
    assert summary["provenance_record_count"] == 0
    assert (run_dir / "eps_telemetry.jsonl").exists()
    eps_rows = _read_jsonl(run_dir / "eps_telemetry.jsonl")
    assert len(eps_rows) == 50
    assert "solar_voltage_v" in eps_rows[0]
    assert summary["min_power_margin_w"] is not None


def test_scrubber_degradation_pre_anomaly_near_equilibrium(tmp_path: Path):
    run_dir = run_scenario(
        "scrubber_degradation",
        output_dir=tmp_path / "pre_anomaly",
        recreate_output=True,
    )
    telemetry = _read_jsonl(run_dir / "telemetry.jsonl")
    pre = [row for row in telemetry if row["step"] < 20]
    assert pre, "need pre-anomaly window"
    co2_values = [row["co2_ppm"] for row in pre]
    assert max(co2_values) - min(co2_values) < 150.0, "CO2 should stay near equilibrium before anomaly"
