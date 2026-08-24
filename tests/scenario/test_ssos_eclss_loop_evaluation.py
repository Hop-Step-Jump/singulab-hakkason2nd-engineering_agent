"""Deterministic scorecard tests for ssos_eclss_loop."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from scenario.runner import run_scenario
from scenario.ssos_eclss_loop.evaluation import (
    _resource_recovery_axis,
    _tcl_axis,
    evaluate_run,
    select_telemetry_rows,
)


def _config() -> dict:
    path = (
        Path(__file__).parents[2]
        / "src"
        / "scenario"
        / "ssos_eclss_loop"
        / "scenario.yaml"
    )
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_select_telemetry_rows_prefers_post_ops_and_preserves_pre():
    rows = [
        {"step": 0, "co2_storage_kg": 1.0},
        {"step": 1, "co2_storage_kg": 2.0},
        {"step": 1, "post_ops": True, "co2_storage_kg": 1.5},
    ]
    canonical, pre = select_telemetry_rows(rows)
    assert [row["co2_storage_kg"] for row in canonical] == [1.0, 1.5]
    assert pre[1]["co2_storage_kg"] == 2.0


def test_tcl_scores_observed_event_and_right_censors_short_run():
    config = {"tcl": {"reference_seconds": 100.0}}
    rows = [
        {"step": 0, "raw_topics": {"plant_sim": {"simulation_time_s": 0.0}}},
        {"step": 1, "raw_topics": {"plant_sim": {"simulation_time_s": 50.0}}},
    ]
    observed = _tcl_axis(
        rows,
        [
            {
                "step": 1,
                "kind": "/eclss/events/crew_lost",
                "crew_lost_by_cause": {"o2_physics": 1},
            }
        ],
        config,
        50.0,
    )
    assert observed["status"] == "scored"
    assert observed["score"] == pytest.approx(5.0)
    assert observed["metrics"]["tcl_causes"] == {"o2_physics": 1}

    censored = _tcl_axis(rows, [], config, 50.0)
    assert censored["status"] == "right_censored"
    assert censored["score"] is None


def test_resource_recovery_uses_actor_pre_event_values():
    thresholds = {
        "co2_storage_high_kg": 2.0,
        "co2_storage_critical_kg": 8.0,
        "o2_storage_low_kg": 6.0,
        "o2_storage_critical_kg": 1.0,
        "product_water_low_l": 50.0,
        "product_water_critical_l": 25.0,
    }
    rows = [
        {
            "step": 0,
            "co2_storage_kg": 1.0,
            "o2_storage_kg": 8.0,
            "product_water_reserve_l": 80.0,
        },
        {
            "step": 1,
            "co2_storage_kg": 3.0,
            "o2_storage_kg": 5.0,
            "product_water_reserve_l": 45.0,
        },
        {
            "step": 2,
            "co2_storage_kg": 1.5,
            "o2_storage_kg": 7.0,
            "product_water_reserve_l": 60.0,
        },
    ]
    event = {"step": 1, "kind": "subsystem_failure_applied", "enabled": True, "subsystem": "ars"}
    axis = _resource_recovery_axis(
        rows,
        {0: rows[0], 1: rows[1], 2: rows[2]},
        [event],
        thresholds,
        {
            "resource_recovery": {
                "resource_weights": {"co2": 1, "o2": 1, "water": 1},
                "terminal_weight": 0.5,
            }
        },
    )
    resources = axis["metrics"]["resources"]
    assert resources["co2"]["initial"] == pytest.approx(1.0)
    assert resources["co2"]["event"] == pytest.approx(3.0)
    assert resources["co2"]["event_minus_initial"] == pytest.approx(2.0)
    assert resources["o2"]["event"] == pytest.approx(5.0)
    assert resources["water"]["event"] == pytest.approx(45.0)


def test_plant_run_writes_scored_evaluation_and_summary_index(tmp_path: Path):
    run_dir = run_scenario(
        "ssos_eclss_loop",
        output_dir=tmp_path / "plant_eval",
        overrides={
            "backend": {"kind": "plant_sim"},
            "simulation": {"steps": 50},
            "agents": {"actor": {"mode": "none"}, "design": {"mode": "none"}},
        },
        recreate_output=True,
    )
    evaluation = _read_json(run_dir / "evaluation.json")
    summary = _read_json(run_dir / "summary.json")

    assert evaluation["status"] == "scored"
    assert evaluation["physics_gate"]["passed"] is True
    assert evaluation["scores"]["max_score"] == 80
    assert "actor_decision" not in evaluation["scores"]["axes"]
    assert "physical_response" not in evaluation["scores"]["axes"]
    assert summary["evaluation_path"] == str(run_dir / "evaluation.json")
    assert summary["evaluation_html_path"] == str(run_dir / "evaluation.html")
    assert summary["evaluation_status"] == evaluation["status"]
    assert summary["evaluation_score"] == evaluation["scores"]["total"]
    assert summary["physics_gate_passed"] is True
    html = (run_dir / "evaluation.html").read_text(encoding="utf-8")
    assert "ECLSSシミュレーション 評価結果" in html
    assert "物理整合性ゲート" in html


def test_mock_run_writes_not_applicable_evaluation(tmp_path: Path):
    run_dir = run_scenario(
        "ssos_eclss_loop",
        output_dir=tmp_path / "mock_eval",
        overrides={
            "backend": {"kind": "mock"},
            "simulation": {"steps": 2},
            "agents": {"actor": {"mode": "none"}, "design": {"mode": "none"}},
        },
        recreate_output=True,
    )
    evaluation = _read_json(run_dir / "evaluation.json")
    assert evaluation["status"] == "not_applicable"
    assert evaluation["applicability"]["reason"] == "plant_sim_required"
    html = (run_dir / "evaluation.html").read_text(encoding="utf-8")
    assert "適用対象外" in html


def test_actor_run_scores_decision_and_physical_response(tmp_path: Path):
    run_dir = run_scenario(
        "ssos_eclss_loop",
        output_dir=tmp_path / "actor_eval",
        overrides={
            "backend": {"kind": "plant_sim"},
            "simulation": {"steps": 20},
            "agents": {
                "actor": {"mode": "labeled_rule_base"},
                "design": {"mode": "none"},
            },
        },
        recreate_output=True,
    )
    evaluation = _read_json(run_dir / "evaluation.json")
    axes = evaluation["scores"]["axes"]
    assert evaluation["scores"]["max_score"] == 100
    assert axes["actor_decision"]["status"] == "scored"
    assert axes["physical_response"]["status"] == "scored"
    assert axes["physical_response"]["metrics"]["valid_operation_count"] > 0


def test_non_finite_telemetry_invalidates_physics_gate(tmp_path: Path):
    run_dir = run_scenario(
        "ssos_eclss_loop",
        output_dir=tmp_path / "invalid_eval",
        overrides={
            "backend": {"kind": "plant_sim"},
            "simulation": {"steps": 3},
            "agents": {"actor": {"mode": "none"}, "design": {"mode": "none"}},
            "evaluation": {"tcl": {"reference_seconds": 1}},
        },
        recreate_output=True,
    )
    telemetry_path = run_dir / "telemetry.jsonl"
    rows = [
        json.loads(line)
        for line in telemetry_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rows[0]["co2_storage_kg"] = None
    telemetry_path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )
    summary = _read_json(run_dir / "summary.json")
    evaluation = evaluate_run(run_dir, scenario_config=_config(), summary=summary)
    assert evaluation["status"] == "invalid"
    assert evaluation["physics_gate"]["passed"] is False
