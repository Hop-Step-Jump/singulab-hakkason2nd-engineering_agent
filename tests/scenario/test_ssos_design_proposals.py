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
    assert merged["agents"]["actor"]["policy"]["ogs_goal"]["input_water_mass"] == 12.0
    assert merged["agents"]["policy"]["request_co2_amount"] == 30.0
    assert merged["agents"]["actor"]["policy"]["request_co2_amount"] == 30.0
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


def test_apply_graph_rewire_rejects_empty_payload():
    proposals = {
        "design_domain": DESIGN_DOMAIN,
        "changes": [{"change_kind": "graph_rewire", "payload": {}}],
    }
    with pytest.raises(ValueError, match="non-empty"):
        apply_design_proposals({"agents": {"policy": {}}}, proposals)


def test_build_design_proposals_from_policy():
    policy = {
        "co2_storage_high_kg": 1.5,
        "o2_storage_low_kg": 0.45,
        "request_co2_amount": 0.025,
        "request_co2_before_ogs": True,
        "ars_goal": {"initial_co2_mass": 1.8},
        "ogs_goal": {"input_water_mass": 0.01},
    }
    # Without summary stress, still emit a non-no-op ARS bump (L8).
    doc = build_design_proposals_from_run(
        proposed_by="eclss_operator_1",
        decision_source="rule",
        policy=policy,
    )
    assert doc["design_domain"] == DESIGN_DOMAIN
    assert doc["proposed_by"] == "eclss_operator_1"
    assert doc["changes"]
    assert any(c.get("change_kind") == "action_profile" for c in doc["changes"])
    ars = next(c for c in doc["changes"] if c["change_kind"] == "action_profile")
    assert ars["payload"]["fields"]["initial_co2_mass"] == pytest.approx(1.98)
    assert validate_design_proposals(doc) == []


def test_build_design_proposals_from_policy_includes_why_what_how():
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
    change = next(c for c in doc["changes"] if c["change_kind"] == "action_profile")
    assert change.get("why")
    assert change.get("what")
    assert change.get("how")


def test_build_design_proposals_from_stressed_summary_includes_why_what_how():
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
        summary={
            "final_health": {"co2_status": "warning", "o2_status": "warning"},
            "final_co2_storage_kg": 1.7,
            "min_o2_storage_kg": 0.4,
        },
    )
    kinds = {c["change_kind"] for c in doc["changes"]}
    assert "action_profile" in kinds
    assert "set_parameter" in kinds
    assert "service_config" in kinds
    for change in doc["changes"]:
        assert change.get("why")
        assert change.get("what")
        assert change.get("how")


def test_build_design_proposals_fallback_without_goals_uses_threshold():
    """L8/A: missing ars/ogs goals still yields a non-no-op threshold bump."""
    doc = build_design_proposals_from_run(
        proposed_by="eclss_operator_1",
        decision_source="rule",
        policy={"co2_storage_high_kg": 1.5, "o2_storage_low_kg": 0.45},
    )
    assert doc["changes"]
    assert all(c["change_kind"] == "set_parameter" for c in doc["changes"])
    values = {c["payload"]["target"]: c["payload"]["value"] for c in doc["changes"]}
    assert values["agents.actor.policy.co2_storage_high_kg"] == pytest.approx(1.35)
    assert values["thresholds.co2_storage_high_kg"] == pytest.approx(1.35)


def test_build_design_proposals_defaults_before_ogs_false_when_absent():
    """Absent request_co2_before_ogs must not embed before_ogs: true in proposals."""
    policy = {
        "co2_storage_high_kg": 1.5,
        "o2_storage_low_kg": 0.45,
        "request_co2_amount": 0.025,
        "ogs_goal": {"input_water_mass": 0.01},
    }
    doc = build_design_proposals_from_run(
        proposed_by="eclss_operator_1",
        decision_source="rule",
        policy=policy,
        summary={
            "final_health": {"o2_status": "warning"},
            "min_o2_storage_kg": 0.4,
        },
    )
    service = next(c for c in doc["changes"] if c["change_kind"] == "service_config")
    assert service["payload"]["before_ogs"] is False


def test_build_design_proposals_ars_zero_mass_falls_through_to_ogs():
    """ARS fallback with non-positive bump must not block OGS / later fallbacks."""
    doc = build_design_proposals_from_run(
        proposed_by="eclss_operator_1",
        decision_source="rule",
        policy={
            "co2_storage_high_kg": 1.5,
            "o2_storage_low_kg": 0.45,
            "ars_goal": {"initial_co2_mass": 0.0},
            "ogs_goal": {"input_water_mass": 0.01},
        },
    )
    assert doc["changes"]
    ogs = next(c for c in doc["changes"] if c["change_kind"] == "action_profile")
    assert ogs["payload"]["subsystem"] == "ogs"
    assert ogs["payload"]["fields"]["input_water_mass"] == pytest.approx(0.011)


def test_build_design_proposals_ars_tiny_mass_falls_through():
    """Rounded-to-zero ARS bump must fall through instead of writing a no-op profile."""
    doc = build_design_proposals_from_run(
        proposed_by="eclss_operator_1",
        decision_source="rule",
        policy={
            "co2_storage_high_kg": 1.5,
            "o2_storage_low_kg": 0.45,
            "ars_goal": {"initial_co2_mass": 1e-7},
            "ogs_goal": {"input_water_mass": 0.01},
        },
    )
    assert doc["changes"]
    profiles = [c for c in doc["changes"] if c["change_kind"] == "action_profile"]
    assert profiles
    assert profiles[0]["payload"]["subsystem"] == "ogs"
    assert all(
        c["payload"]["fields"].get("initial_co2_mass", 1.0) > 0.0
        for c in profiles
        if c["payload"]["subsystem"] == "ars"
    )


def test_build_design_proposals_fallback_empty_policy_uses_default_threshold():
    """Even with empty policy, labeled builder uses default CO₂ high band."""
    doc = build_design_proposals_from_run(
        proposed_by="rep",
        decision_source="rule",
        policy={},
    )
    assert doc["changes"]
    assert any(
        c["payload"]["target"] == "thresholds.co2_storage_high_kg" for c in doc["changes"]
    )


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
    assert merged["agents"]["policy"]["ogs_goal"]["input_water_mass"] == pytest.approx(9.9)
    assert merged["agents"]["actor"]["policy"]["ogs_goal"]["input_water_mass"] == pytest.approx(9.9)


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


def test_apply_set_parameter_canonical_target_dual_writes_legacy_alias():
    proposals = {
        "design_domain": DESIGN_DOMAIN,
        "changes": [
            {
                "change_kind": "set_parameter",
                "payload": {
                    "target": "agents.actor.policy.co2_storage_high_kg",
                    "value": 1.1,
                },
            }
        ],
    }
    merged = apply_design_proposals({"agents": {}}, proposals)
    assert merged["agents"]["actor"]["policy"]["co2_storage_high_kg"] == 1.1
    assert merged["agents"]["policy"]["co2_storage_high_kg"] == 1.1


def test_apply_without_legacy_policy_key_still_loads_actor_policy():
    from scenario.runner import load_agents_config, load_scenario_config

    config = load_scenario_config(
        "ssos_eclss_loop",
        {"agents": {"actor": {"mode": "labeled_rule_base"}}},
    )
    config.get("agents", {}).pop("policy", None)
    merged = apply_design_proposals(
        config,
        {
            "design_domain": DESIGN_DOMAIN,
            "changes": [
                {
                    "change_kind": "action_profile",
                    "payload": {
                        "subsystem": "ars",
                        "fields": {"initial_co2_mass": 2.5},
                    },
                }
            ],
        },
    )
    merged["agents"].pop("policy", None)
    agents = load_agents_config("ssos_eclss_loop", merged)
    assert agents is not None
    assert agents["actor"]["policy"]["ars_goal"]["initial_co2_mass"] == 2.5
