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
    assert (run_dir / "design_state.jsonl").exists()
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
    assert "thresholds" in summary
    assert summary["thresholds"]["co2_storage_high_kg"] == pytest.approx(1.5)
    assert "health_inputs" in summary
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
    assert summary["apply_proposals_path"] == str(proposals_path)
    assert (second / "scenario_config.yaml").exists()
    assert (second / "agents_config.yaml").exists()

    import yaml

    proposals = json.loads(proposals_path.read_text(encoding="utf-8"))
    effective_agents = yaml.safe_load((second / "agents_config.yaml").read_text(encoding="utf-8"))
    effective_scenario = yaml.safe_load((second / "scenario_config.yaml").read_text(encoding="utf-8"))
    assert effective_scenario.get("agents", {}).get("mode") == "labeled_rule_base"

    # At least one applied change must appear in the dumped effective agents policy.
    applied_kinds = {c["change_kind"] for c in proposals.get("changes", [])}
    policy = effective_agents.get("policy") or {}
    if "action_profile" in applied_kinds:
        assert "ars_goal" in policy or "ogs_goal" in policy or "wrs_goal" in policy
    if "service_config" in applied_kinds:
        assert "request_co2_amount" in policy or "request_o2_amount" in policy
    if "set_parameter" in applied_kinds:
        # set_parameter may land in scenario thresholds and/or agents.policy
        assert "thresholds" in effective_scenario or any(
            k.endswith("_kg") or k.endswith("_l") for k in policy
        )


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
    # Default policy leaves CO₂ feedstock to OGS-internal Sabatier (no explicit request_co2).
    assert summary.get("co2_requested_step") is None
    applied_kinds = {
        (e.get("command") or {}).get("kind")
        for e in events
        if e.get("kind") == "/eclss/events/operational_applied"
    }
    assert "oxygen_generation" in applied_kinds
    assert "request_co2" not in applied_kinds


def test_resolve_backend_kind_from_env(monkeypatch):
    config = {"backend": {"kind": "mock"}}
    monkeypatch.setenv(BACKEND_ENV_VAR, "ros2")
    assert resolve_backend_kind(config) == "ros2"


def test_effective_config_records_env_resolved_backend(tmp_path: Path, monkeypatch):
    """scenario_config.yaml must match the backend actually used (not stale YAML)."""
    import yaml

    monkeypatch.setenv(BACKEND_ENV_VAR, "plant_sim")
    run_dir = run_scenario(
        "ssos_eclss_loop",
        output_dir=tmp_path / "env_backend",
        overrides={"simulation": {"steps": 2}},
        recreate_output=True,
    )
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    effective = yaml.safe_load((run_dir / "scenario_config.yaml").read_text(encoding="utf-8"))
    assert summary["backend"] == "plant_sim"
    assert effective["backend"]["kind"] == "plant_sim"


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


def test_ssos_eclss_loop_skips_empty_design_proposals_file(tmp_path: Path, monkeypatch):
    """L8/B: do not write design_proposals.json when changes is empty."""
    from scenario.agents.ssos_eclss_loop_team import SsosEclssLoopTeam

    monkeypatch.setattr(
        SsosEclssLoopTeam,
        "propose_post_run_design",
        lambda self, summary: {
            "design_domain": "ssos_graph",
            "proposed_by": "op_1",
            "decision_source": "rule",
            "message": "",
            "changes": [],
        },
    )
    run_dir = run_scenario(
        "ssos_eclss_loop",
        output_dir=tmp_path / "empty_proposals",
        overrides={"agents": {"mode": "labeled_rule_base"}},
        recreate_output=True,
    )
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary.get("design_proposal_count") == 0
    assert "design_proposals_path" not in summary
    assert not (run_dir / "design_proposals.json").exists()


def test_ssos_eclss_loop_plant_sim_writes_thresholds_and_metabolism(tmp_path: Path):
    run_dir = run_scenario(
        "ssos_eclss_loop",
        output_dir=tmp_path / "plant_sim",
        overrides={
            "backend": {"kind": "plant_sim"},
            "agents": {"mode": "labeled_rule_base"},
            "simulation": {"steps": 3},
        },
        recreate_output=True,
    )
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    telemetry = _read_jsonl(run_dir / "telemetry.jsonl")

    assert summary["backend"] == "plant_sim"
    assert "thresholds" in summary
    assert summary["thresholds"]["o2_storage_critical_kg"] == pytest.approx(
        summary["thresholds"]["o2_storage_low_kg"] * 0.75
    )

    metabolism_rows = [
        row
        for row in telemetry
        if isinstance((row.get("raw_topics") or {}).get("plant_sim"), dict)
        and "last_metabolism" in (row["raw_topics"]["plant_sim"])
        and row.get("post_ops") is not True
    ]
    assert len(metabolism_rows) == 2  # steps 2 and 3 (advance before poll)

    proposals_path = run_dir / "design_proposals.json"
    if proposals_path.exists():
        proposals = json.loads(proposals_path.read_text(encoding="utf-8"))
        for change in proposals.get("changes", []):
            assert change.get("why")
            assert change.get("what")
            assert change.get("how")

