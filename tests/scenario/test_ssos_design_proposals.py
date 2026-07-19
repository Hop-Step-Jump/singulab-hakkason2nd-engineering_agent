"""Tests for ssos_eclss_loop design_proposals.json apply/build helpers."""

import json

import pytest

from scenario.ssos_eclss_loop.design_proposals import (
    DESIGN_DOMAIN,
    apply_design_proposals,
    build_design_proposals_from_run,
    validate_design_proposals,
    write_design_proposals,
)


def test_apply_action_profile_and_service_config():
    config = {
        "agents": {"policy": {"ars_goal": {"initial_co2_mass": 1000.0}}},
        "thresholds": {"o2_storage_low_kg": 400.0},
    }
    proposals = {
        "design_domain": DESIGN_DOMAIN,
        "proposed_by": "op_1",
        "decision_source": "rule",
        "changes": [
            {
                "change_kind": "action_profile",
                "payload": {
                    "subsystem": "ogs",
                    "fields": {"input_water_mass": 12.0, "iodine_concentration": 1.5},
                },
            },
            {
                "change_kind": "service_config",
                "payload": {"service": "request_co2", "amount": 30.0, "before_ogs": False},
            },
            {
                "change_kind": "set_parameter",
                "payload": {"target": "thresholds.co2_storage_high_kg", "value": 1600.0},
            },
        ],
    }
    merged = apply_design_proposals(config, proposals)
    assert merged["agents"]["policy"]["ogs_goal"]["input_water_mass"] == 12.0
    assert merged["agents"]["policy"]["request_co2_amount"] == 30.0
    assert merged["agents"]["policy"]["request_co2_before_ogs"] is False
    assert merged["thresholds"]["co2_storage_high_kg"] == 1600.0
    assert merged["agents"]["policy"]["ars_goal"]["initial_co2_mass"] == 1000.0


def test_apply_graph_rewire():
    config = {"agents": {"policy": {}}}
    proposals = {
        "design_domain": DESIGN_DOMAIN,
        "changes": [
            {
                "change_kind": "graph_rewire",
                "payload": {
                    "component": "rclpy_gateway",
                    "public": "/grey_water",
                    "backend": "/grey_water/wrs",
                },
            }
        ],
    }
    merged = apply_design_proposals(config, proposals)
    assert len(merged["ssos_graph"]["rewires"]) == 1
    assert merged["ssos_graph"]["rewires"][0]["public"] == "/grey_water"


def test_build_design_proposals_from_policy():
    policy = {
        "co2_storage_high_kg": 1.5,
        "o2_storage_low_kg": 0.45,
        "request_co2_amount": 0.025,
        "request_co2_before_ogs": True,
        "ars_goal": {"initial_co2_mass": 1.8},
        "ogs_goal": {"input_water_mass": 0.01},
    }
    doc = build_design_proposals_from_run(
        proposed_by="eclss_operator_1",
        decision_source="rule",
        policy=policy,
    )
    assert doc["design_domain"] == DESIGN_DOMAIN
    assert doc["proposed_by"] == "eclss_operator_1"
    kinds = {c["change_kind"] for c in doc["changes"]}
    assert kinds == {"action_profile", "service_config", "set_parameter"}
    assert validate_design_proposals(doc) == []


def test_write_rejects_scrubber_change_kind(tmp_path):
    bad = {
        "design_domain": DESIGN_DOMAIN,
        "changes": [{"change_kind": "add_edge", "payload": {}}],
    }
    with pytest.raises(ValueError, match="change_kind"):
        write_design_proposals(tmp_path / "bad.json", bad)


def test_round_trip_via_json_file(tmp_path):
    proposals = build_design_proposals_from_run(
        proposed_by="rep",
        decision_source="rule",
        policy={"ogs_goal": {"input_water_mass": 9.0}},
    )
    path = tmp_path / "design_proposals.json"
    write_design_proposals(path, proposals)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    merged = apply_design_proposals({"agents": {"policy": {}}}, loaded)
    assert merged["agents"]["policy"]["ogs_goal"]["input_water_mass"] == 9.0


def test_apply_action_profile_rejects_unknown_fields():
    proposals = {
        "design_domain": DESIGN_DOMAIN,
        "changes": [
            {
                "change_kind": "action_profile",
                "payload": {
                    "subsystem": "ars",
                    "fields": {
                        "initial_co2_mass": 1800.0,
                        "duration_steps": 3,
                    },
                },
            }
        ],
    }
    with pytest.raises(ValueError, match="unsupported keys"):
        apply_design_proposals({"agents": {"policy": {}}}, proposals)


def test_apply_set_parameter_rejects_arbitrary_target():
    proposals = {
        "design_domain": DESIGN_DOMAIN,
        "changes": [
            {
                "change_kind": "set_parameter",
                "payload": {"target": "simulation.steps", "value": 999},
            }
        ],
    }
    with pytest.raises(ValueError, match="not allowed"):
        apply_design_proposals({"agents": {"policy": {}}}, proposals)
