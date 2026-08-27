"""Tests for design→verification loop orchestrator and scrubber apply-proposals."""

from __future__ import annotations

import json
from pathlib import Path

from scenario.jobs.design_history import crew_target_met, digest_run_for_history
from scenario.jobs.loop import LoopSpec, execute_loop
from scenario.scrubber_degradation.design_proposals import (
    apply_design_proposals,
)
from scenario.scrubber_degradation.scenario_run import ScrubberDegradationScenario


def test_crew_target_met():
    assert crew_target_met({"crew_remaining": 50}, target_crew=50)
    assert not crew_target_met({"crew_remaining": 49}, target_crew=50)
    assert not crew_target_met({}, target_crew=50)


def test_loop_run_id_format():
    spec = LoopSpec(loop_id="e002loop")
    assert spec.run_id_for(1) == "e002loop-run01"
    assert spec.run_id_for(12) == "e002loop-run12"


def test_scrubber_apply_proposals_closed_loop(tmp_path: Path):
    first = ScrubberDegradationScenario().run(
        output_dir=tmp_path / "first",
        overrides={"agents": {"mode": "labeled_rule_base"}, "simulation": {"steps": 25}},
        recreate_output=True,
    )
    proposals_path = first / "design_proposals.json"
    assert proposals_path.exists()
    proposals = json.loads(proposals_path.read_text(encoding="utf-8"))
    assert proposals.get("changes")

    second = ScrubberDegradationScenario().run(
        output_dir=tmp_path / "second",
        overrides={"agents": {"mode": "labeled_rule_base"}, "simulation": {"steps": 10}},
        apply_proposals_path=proposals_path,
        recreate_output=True,
    )
    summary = json.loads((second / "summary.json").read_text(encoding="utf-8"))
    assert summary["apply_proposals_path"] == str(proposals_path)

    # Seeded bypass should appear in design_state at step 1.
    design_rows = [
        json.loads(line)
        for line in (second / "design_state.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert design_rows
    edges = design_rows[0].get("topology", {}).get("edges") or []
    assert any(e.get("kind") == "bypass" for e in edges)


def test_scrubber_apply_proposals_module_set_parameter():
    config = {"design_parameters": {"scrubber_base_efficiency": 0.95}}
    proposals = {
        "changes": [
            {
                "change_kind": "set_parameter",
                "payload": {"key": "scrubber_base_efficiency", "value": 0.8},
            },
            {
                "change_kind": "add_edge",
                "payload": {"node_a": "manifold", "node_b": "scrubber", "kind": "bypass"},
            },
        ]
    }
    updated, topo = apply_design_proposals(config, proposals)
    assert updated["design_parameters"]["scrubber_base_efficiency"] == 0.8
    assert len(topo) == 1


def test_execute_loop_scrubber_names_and_history(tmp_path: Path):
    result = execute_loop(
        LoopSpec(
            scenario="scrubber_degradation",
            overrides={
                "agents": {"mode": "labeled_rule_base"},
                "simulation": {"steps": 12},
            },
            results_root=tmp_path,
            loop_id="e002loop",
            max_loops=2,
            target_crew=50,
            max_actions_per_step=2,
        )
    )
    assert len(result.runs) >= 1
    assert result.runs[0].run_dir.name == "e002loop-run01"
    assert (tmp_path / "e002loop-manifest.json").exists()
    if len(result.runs) >= 2:
        assert result.runs[1].run_dir.name == "e002loop-run02"
        summary2 = result.runs[1].summary or {}
        assert summary2.get("design_history_runs") == 1


def test_execute_loop_ssos_mock_stops_at_max(tmp_path: Path):
    # mock has no crew_remaining → never hits target; stops at max_loops.
    result = execute_loop(
        LoopSpec(
            scenario="ssos_eclss_loop",
            overrides={
                "agents": {
                    "actor": {"mode": "labeled_rule_base", "max_actions_per_step": 2},
                    "design": {"mode": "labeled_rule_base"},
                },
                "backend": {"kind": "mock"},
                "simulation": {"steps": 3},
            },
            results_root=tmp_path,
            loop_id="e002loop",
            max_loops=2,
            target_crew=50,
        )
    )
    assert result.stopped_reason == "max_loops"
    assert len(result.runs) == 2
    assert result.runs[0].run_dir.name == "e002loop-run01"
    assert result.runs[1].run_dir.name == "e002loop-run02"
    # Second run should have received prior history for designers.
    assert (result.runs[1].summary or {}).get("design_history_runs") == 1


def test_digest_run_for_history_includes_proposals(tmp_path: Path):
    run_dir = tmp_path / "r"
    run_dir.mkdir()
    (run_dir / "design_proposals.json").write_text(
        json.dumps({"changes": [{"change_kind": "add_edge", "payload": {}}]}, indent=2),
        encoding="utf-8",
    )
    digest = digest_run_for_history(
        run_id="e002loop-run01",
        run_dir=run_dir,
        summary={"peak_co2_ppm": 1200, "crew_remaining": 40},
        loop_index=1,
    )
    assert digest["proposals"]["change_count"] == 1
    assert digest["summary"]["crew_remaining"] == 40
