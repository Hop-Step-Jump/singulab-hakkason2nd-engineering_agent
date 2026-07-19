"""Tests for ssos_eclss_loop scenario (mock backend, no ROS2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scenario.runner import list_scenarios, run_scenario
from scenario.ssos_eclss_loop.scenario_run import (
    BACKEND_ENV_VAR,
    build_eclss_backend,
    resolve_backend_kind,
)
from scenario.ssos_eclss_loop.loop_mock_backend import LoopMockEclssBackend


def _read_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def test_ssos_eclss_loop_steps_are_one_based(tmp_path: Path):
    run_dir = run_scenario(
        "ssos_eclss_loop",
        output_dir=tmp_path / "steps",
        overrides={"simulation": {"steps": 10}},
        recreate_output=True,
    )
    telemetry = _read_jsonl(run_dir / "telemetry.jsonl")
    steps = [row["step"] for row in telemetry]
    assert steps == list(range(1, 11))
    assert "ssos_eclss_loop" in list_scenarios()


def test_ssos_eclss_loop_baseline_runs(tmp_path: Path):
    run_dir = run_scenario(
        "ssos_eclss_loop",
        output_dir=tmp_path / "baseline",
        recreate_output=True,
    )

    telemetry = _read_jsonl(run_dir / "telemetry.jsonl")
    health = _read_jsonl(run_dir / "health_metrics.jsonl")
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))

    assert summary["scenario"] == "ssos_eclss_loop"
    assert summary["backend"] == "mock"
    assert summary["agents_mode"] == "none"
    assert summary["steps"] == 8
    assert len(telemetry) == 8
    assert len(health) == 8
    assert summary["operational_command_count"] == 0
    assert summary["message_count"] == 0
    assert summary.get("ars_invoked_step") is None
    assert (run_dir / "provenance.jsonl").exists()
    assert (run_dir / "design_state.jsonl").exists() is False
    assert not (run_dir / "design_proposals.json").exists()

    co2_series = [row["co2_storage_kg"] for row in telemetry]
    assert co2_series[0] == pytest.approx(1.5)
    assert co2_series[-1] > co2_series[0], "CO2 should rise without agent intervention"


def test_ssos_eclss_loop_labeled_agents_invoke_ars(tmp_path: Path):
    run_dir = run_scenario(
        "ssos_eclss_loop",
        output_dir=tmp_path / "labeled",
        overrides={"agents": {"mode": "labeled_rule_base"}},
        recreate_output=True,
    )

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    messages = _read_jsonl(run_dir / "messages.jsonl")
    events = _read_jsonl(run_dir / "events.jsonl")
    telemetry = _read_jsonl(run_dir / "telemetry.jsonl")

    assert summary["agents_mode"] == "labeled_rule_base"
    assert summary["team_count"] == 3
    assert summary["agent_ids"] == [
        "eclss_operator_1",
        "eclss_operator_2",
        "eclss_operator_3",
    ]
    assert summary["message_count"] > 0
    assert summary["operational_command_count"] >= 1
    assert summary["ars_invoked_step"] == 1

    message_types = {m["message_type"] for m in messages}
    assert "alert" in message_types
    assert "operational_command" in message_types
    assert "design_change" not in message_types

    applied = [e for e in events if e.get("kind") == "/eclss/events/operational_applied"]
    assert any(
        (e.get("command") or {}).get("kind") == "air_revitalisation" for e in applied
    )

    assert telemetry[0]["step"] == 1
    assert telemetry[0]["co2_storage_kg"] == pytest.approx(1.5)
    assert telemetry[1]["co2_storage_kg"] < telemetry[0]["co2_storage_kg"], (
        "ARS should reduce CO2 storage after step 1"
    )
    assert (run_dir / "design_proposals.json").exists()
    assert summary.get("design_proposal_count", 0) >= 1
    proposals = json.loads((run_dir / "design_proposals.json").read_text(encoding="utf-8"))
    assert proposals.get("design_domain") == "ssos_graph"


def test_ssos_eclss_loop_labeled_policy_matches_thresholds(tmp_path: Path):
    run_dir = run_scenario(
        "ssos_eclss_loop",
        output_dir=tmp_path / "policy_thresholds",
        overrides={
            "agents": {"mode": "labeled_rule_base"},
            "thresholds": {"co2_storage_high_kg": 1.6, "o2_storage_low_kg": 0.43},
            "simulation": {"initial_co2_storage_kg": 1.65},
        },
        recreate_output=True,
    )
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["ars_invoked_step"] == 1


def test_ssos_eclss_loop_labeled_reinvokes_ars_when_co2_reexceeds(tmp_path: Path):
    run_dir = run_scenario(
        "ssos_eclss_loop",
        output_dir=tmp_path / "labeled_rearm",
        overrides={"agents": {"mode": "labeled_rule_base"}},
        recreate_output=True,
    )

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    events = _read_jsonl(run_dir / "events.jsonl")
    ars_steps = [
        e["step"]
        for e in events
        if e.get("kind") == "/eclss/events/operational_applied"
        and (e.get("command") or {}).get("kind") == "air_revitalisation"
    ]

    assert summary["operational_command_count"] >= 2
    assert 1 in ars_steps
    assert any(step > 1 for step in ars_steps), "ARS should re-fire after CO2 regrows past threshold"


def test_ssos_eclss_loop_provenance_includes_operational_records(tmp_path: Path):
    run_dir = run_scenario(
        "ssos_eclss_loop",
        output_dir=tmp_path / "labeled_prov",
        overrides={"agents": {"mode": "labeled_rule_base"}},
        recreate_output=True,
    )

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    provenance = _read_jsonl(run_dir / "provenance.jsonl")
    operational = [p for p in provenance if p.get("record_type") == "operational"]

    assert summary["provenance_record_count"] >= 1
    assert operational, "expected SSOS operational provenance records"
    assert any(p.get("change_kind") == "air_revitalisation" for p in operational)
    assert operational[0]["trace"]["event_kind"] == "/eclss/events/operational_applied"
    assert operational[0]["trace"]["decision_source"] == "rule"


def test_ssos_eclss_loop_apply_proposals(tmp_path: Path):
    first = run_scenario(
        "ssos_eclss_loop",
        output_dir=tmp_path / "first",
        overrides={"agents": {"mode": "labeled_rule_base"}},
        recreate_output=True,
    )
    proposals_path = first / "design_proposals.json"
    assert proposals_path.exists()

    from scenario.ssos_eclss_loop.scenario_run import SsosEclssLoopScenario

    second = SsosEclssLoopScenario().run(
        output_dir=tmp_path / "second",
        overrides={"agents": {"mode": "labeled_rule_base"}},
        apply_proposals_path=proposals_path,
    )
    summary = json.loads((second / "summary.json").read_text(encoding="utf-8"))
    assert summary["operational_command_count"] >= 1


def test_ssos_eclss_loop_labeled_agents_ogs_when_o2_low(tmp_path: Path):
    run_dir = run_scenario(
        "ssos_eclss_loop",
        output_dir=tmp_path / "ogs",
        overrides={
            "agents": {"mode": "labeled_rule_base"},
            "simulation": {"initial_o2_storage_kg": 0.42},
        },
        recreate_output=True,
    )

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    events = _read_jsonl(run_dir / "events.jsonl")

    assert summary["ogs_invoked_step"] == 1
    assert summary["co2_requested_step"] == 1
    applied_kinds = {
        (e.get("command") or {}).get("kind")
        for e in events
        if e.get("kind") == "/eclss/events/operational_applied"
    }
    assert "oxygen_generation" in applied_kinds
    assert "request_co2" in applied_kinds


def test_resolve_backend_kind_from_env(monkeypatch):
    config = {"backend": {"kind": "mock"}}
    monkeypatch.setenv(BACKEND_ENV_VAR, "ros2")
    assert resolve_backend_kind(config) == "ros2"


def test_resolve_backend_kind_override_wins(monkeypatch):
    config = {"backend": {"kind": "mock"}}
    monkeypatch.setenv(BACKEND_ENV_VAR, "ros2")
    assert resolve_backend_kind(config, overrides={"backend": {"kind": "mock"}}) == "mock"


def test_build_eclss_backend_mock():
    backend = build_eclss_backend({"simulation": {}, "mock_dynamics": {}}, kind="mock")
    assert isinstance(backend, LoopMockEclssBackend)


def test_build_eclss_backend_unknown_raises():
    with pytest.raises(ValueError, match="Unknown ECLSS backend"):
        build_eclss_backend({}, kind="invalid")


def test_ssos_eclss_loop_llm_agents_invoke_ars(tmp_path: Path, monkeypatch):
    from scenario.agents.ssos_eclss_loop_team import SsosEclssLoopTeam

    class FakeClient:
        def generate(self, prompt: str) -> str:
            lower = prompt.lower()
            if "phase: deliberation" in lower and "eclss_operator_1" in lower:
                return json.dumps(
                    {
                        "message": "CO2 storage at band edge; ARS may be warranted.",
                        "reasoning": "co2_storage_kg telemetry elevated",
                    }
                )
            if "phase: deliberation" in lower and "eclss_operator_2" in lower:
                return json.dumps(
                    {
                        "message": "Agree — vent CO2 before reserve fills further.",
                        "reasoning": "storage trend unfavorable",
                    }
                )
            if "phase: deliberation" in lower and "eclss_operator_3" in lower:
                return json.dumps(
                    {
                        "message": "Monitoring O2; focus ARS this step.",
                        "reasoning": "o2 still adequate",
                    }
                )
            if "phase: action" in lower:
                return json.dumps(
                    {
                        "message": "LLM action rep: start ARS air_revitalisation.",
                        "reasoning": "team consensus on high CO2 storage",
                        "commands": [
                            {
                                "kind": "air_revitalisation",
                                "payload": {
                                    "initial_co2_mass": 1.8,
                                    "initial_moisture_content": 25.0,
                                    "initial_contaminants": 5.0,
                                },
                            }
                        ],
                    }
                )
            if "phase: post_run_proposal" in lower:
                return json.dumps(
                    {
                        "message": "LLM design: raise ARS CO2 mass setpoint for next run.",
                        "reasoning": "operational intervention indicates margin gap",
                        "changes": [
                            {
                                "change_kind": "action_profile",
                                "payload": {
                                    "subsystem": "ars",
                                    "action": "air_revitalisation",
                                    "fields": {"initial_co2_mass": 2.0},
                                },
                            }
                        ],
                    }
                )
            return "{}"

    monkeypatch.setattr(SsosEclssLoopTeam, "_build_llm_client", staticmethod(lambda _: FakeClient()))

    run_dir = run_scenario(
        "ssos_eclss_loop",
        output_dir=tmp_path / "llm",
        overrides={"agents": {"mode": "llm"}},
        recreate_output=True,
    )

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    messages = _read_jsonl(run_dir / "messages.jsonl")
    design_proposals = json.loads((run_dir / "design_proposals.json").read_text(encoding="utf-8"))

    assert summary["agents_mode"] == "llm"
    assert summary["team_count"] == 3
    assert summary["operational_command_count"] >= 1
    assert summary["ars_invoked_step"] == 1
    assert any(m.get("decision_source") == "llm" for m in messages)
    assert any(m.get("deliberation_phase") == "deliberation" for m in messages)
    assert any(m.get("deliberation_phase") == "action" for m in messages)
    assert design_proposals.get("decision_source") == "llm"
    assert design_proposals.get("design_domain") == "ssos_graph"
    assert any(c.get("change_kind") == "action_profile" for c in design_proposals.get("changes", []))

