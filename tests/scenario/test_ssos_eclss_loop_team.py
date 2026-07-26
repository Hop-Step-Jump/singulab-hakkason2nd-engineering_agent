"""Unit tests for SsosEclssLoopTeam."""

from __future__ import annotations

import pytest

from core.agents.base import Team
from scenario.agents.eclss_loop_types import EclssLoopObservation
from scenario.agents.ssos_eclss_loop_team import SsosEclssLoopTeam
from environment.ssos.eclss.types import ArsGoal, OgsGoal, EclssTelemetrySnapshot
from scenario.ssos_eclss_loop.loop_mock_backend import LoopMockEclssBackend


def _team_config():
    return {
        "mode": "labeled_rule_base",
        "memory_limit": 4,
        "discourse_window": 4,
        "team": {"count": 2, "id_prefix": "op", "persona": "operator"},
        "policy": {
            "co2_storage_high_kg": 1.5,
            "o2_storage_low_kg": 0.45,
            "request_co2_before_ogs": True,
            "request_co2_amount": 0.01,
            "ars_goal": {"initial_co2_mass": 1.8},
            "ogs_goal": {"input_water_mass": 0.015},
        },
    }


def test_team_applies_ars_to_backend():
    team = SsosEclssLoopTeam(_team_config())
    backend = LoopMockEclssBackend(
        {
            "simulation": {"initial_co2_storage_kg": 1.7, "initial_o2_storage_kg": 0.5},
            "mock_dynamics": {},
        }
    )
    snap = backend.poll_telemetry()
    obs = EclssLoopObservation(step=0, telemetry=snap, health={"overall": "warning"})
    outcome = team.run_step(backend, obs)
    assert len(outcome.commands) == 1
    assert outcome.commands[0].kind == "air_revitalisation"

    events = team.apply_outcome(backend, outcome)
    assert len(events) == 1
    assert events[0]["kind"] == "/eclss/events/operational_applied"
    assert backend.last_ars_goal is not None
    assert backend.poll_telemetry().co2_storage_kg < 1.7


def test_team_no_design_change_commands():
    team = SsosEclssLoopTeam(_team_config())
    backend = LoopMockEclssBackend({"simulation": {}, "mock_dynamics": {}})
    snap = EclssTelemetrySnapshot(co2_storage_kg=0.8, o2_storage_kg=0.6)
    obs = EclssLoopObservation(step=0, telemetry=snap, health={"overall": "safe"})
    outcome = team.run_step(backend, obs)
    assert outcome.commands == []


def test_llm_situation_uses_health_status_keys():
    from scenario.agents.ssos_eclss_loop_team import build_llm_situation

    snap = EclssTelemetrySnapshot(co2_storage_kg=1.6, o2_storage_kg=0.42)
    obs = EclssLoopObservation(
        step=2,
        telemetry=snap,
        health={
            "overall": "warning",
            "co2_status": "warning",
            "o2_status": "warning",
            "water_status": "safe",
        },
    )
    situation = build_llm_situation(obs)
    assert "co2_status=warning" in situation
    assert "o2_status=warning" in situation
    assert "water_status=safe" in situation
    assert "co2_storage=unknown" not in situation


def test_ssos_eclss_loop_team_is_team_subclass():
    team = SsosEclssLoopTeam(_team_config())
    assert isinstance(team, Team)


def test_team_rearms_ars_when_ineffective():
    team = SsosEclssLoopTeam(_team_config())
    backend = LoopMockEclssBackend(
        {
            "simulation": {"initial_co2_storage_kg": 1.6, "initial_o2_storage_kg": 0.5},
            "mock_dynamics": {"co2_growth_kg_per_step": 0.0, "ars_co2_reduction_kg": 0.0},
        }
    )
    snap0 = backend.poll_telemetry()
    obs0 = EclssLoopObservation(step=0, telemetry=snap0, health={"overall": "warning"})
    outcome0 = team.run_step(backend, obs0)
    team.apply_outcome(backend, outcome0)
    assert team.state.ars_invoked is True
    assert snap0.co2_storage_kg == backend.poll_telemetry().co2_storage_kg

    backend.advance_step()
    snap1 = backend.poll_telemetry()
    obs1 = EclssLoopObservation(step=1, telemetry=snap1, health={"overall": "warning"})
    outcome1 = team.run_step(backend, obs1)
    assert any(cmd.kind == "air_revitalisation" for cmd in outcome1.commands)


def test_team_rearms_ars_after_co2_drops_below_threshold():
    team = SsosEclssLoopTeam(_team_config())
    backend = LoopMockEclssBackend(
        {
            "simulation": {"initial_co2_storage_kg": 1.7, "initial_o2_storage_kg": 0.5},
            "mock_dynamics": {"co2_growth_kg_per_step": 0.1, "ars_co2_reduction_kg": 0.4},
        }
    )
    co2_high = float(team.policy["co2_storage_high_kg"])

    snap = backend.poll_telemetry()
    obs0 = EclssLoopObservation(step=0, telemetry=snap, health={"overall": "warning"})
    outcome0 = team.run_step(backend, obs0)
    team.apply_outcome(backend, outcome0)
    assert team.state.ars_invoked is True

    backend.advance_step()
    snap1 = backend.poll_telemetry()
    assert snap1.co2_storage_kg < co2_high
    obs1 = EclssLoopObservation(step=1, telemetry=snap1, health={"overall": "safe"})
    team.run_step(backend, obs1)
    assert team.state.ars_invoked is False

    for _ in range(4):
        backend.advance_step()
    snap_high = backend.poll_telemetry()
    assert snap_high.co2_storage_kg >= co2_high
    obs_high = EclssLoopObservation(step=5, telemetry=snap_high, health={"overall": "warning"})
    outcome_high = team.run_step(backend, obs_high)
    assert any(cmd.kind == "air_revitalisation" for cmd in outcome_high.commands)


def test_loop_mock_request_o2_withdraws_plant_storage():
    backend = LoopMockEclssBackend(
        {
            "simulation": {"initial_o2_storage_kg": 0.1},
            "mock_dynamics": {},
        }
    )
    backend.request_o2(0.025)
    assert backend.poll_telemetry().o2_storage_kg == pytest.approx(0.075)


def test_loop_mock_ars_scales_with_goal_mass():
    cfg = {
        "simulation": {"initial_co2_storage_kg": 2.0, "initial_o2_storage_kg": 0.5},
        "mock_dynamics": {"ars_co2_reduction_kg": 0.35, "ars_reference_co2_mass_kg": 1.8},
    }
    low = LoopMockEclssBackend(cfg)
    high = LoopMockEclssBackend(cfg)
    low.send_air_revitalisation_goal(ArsGoal(initial_co2_mass=0.9))
    high.send_air_revitalisation_goal(ArsGoal(initial_co2_mass=1.8))
    # Half reference → half reduction (0.175); full reference → 0.35
    assert low.poll_telemetry().co2_storage_kg == pytest.approx(2.0 - 0.175)
    assert high.poll_telemetry().co2_storage_kg == pytest.approx(2.0 - 0.35)


def test_loop_mock_water_tracks_ogs_without_double_subtract():
    backend = LoopMockEclssBackend(
        {
            "simulation": {"initial_product_water_l": 50.0, "initial_o2_storage_kg": 0.4},
            "mock_dynamics": {},
        }
    )
    before = backend.poll_telemetry().product_water_reserve_l
    backend.send_oxygen_generation_goal(OgsGoal(input_water_mass=5.0))
    after = backend.poll_telemetry()
    assert after.product_water_reserve_l == pytest.approx(before - 5.0)
    assert backend._telemetry.product_water_reserve_l == pytest.approx(after.product_water_reserve_l)


def test_loop_mock_request_co2_withdraws_storage():
    backend = LoopMockEclssBackend(
        {
            "simulation": {"initial_co2_storage_kg": 1.0},
            "mock_dynamics": {},
        }
    )
    result = backend.request_co2(0.25)
    assert result.success
    assert result.response_value == pytest.approx(0.25)
    assert backend.poll_telemetry().co2_storage_kg == pytest.approx(0.75)


def test_loop_mock_request_co2_rejects_partial_insufficient():
    """SSOS /ars/request_co2 rejects when storage cannot cover the full request."""
    backend = LoopMockEclssBackend(
        {
            "simulation": {"initial_co2_storage_kg": 0.1},
            "mock_dynamics": {},
        }
    )
    before = backend.poll_telemetry().co2_storage_kg
    result = backend.request_co2(0.25)
    assert result.success is False
    assert result.response_value == pytest.approx(0.0)
    assert "insufficient" in (result.message or "").lower()
    assert backend.poll_telemetry().co2_storage_kg == pytest.approx(before)


def test_loop_mock_request_co2_exact_amount_succeeds():
    backend = LoopMockEclssBackend(
        {
            "simulation": {"initial_co2_storage_kg": 0.25},
            "mock_dynamics": {},
        }
    )
    result = backend.request_co2(0.25)
    assert result.success
    assert result.response_value == pytest.approx(0.25)
    assert backend.poll_telemetry().co2_storage_kg == pytest.approx(0.0)


def test_loop_mock_failure_blocks_ars_physics():
    backend = LoopMockEclssBackend(
        {
            "simulation": {"initial_co2_storage_kg": 2.0},
            "mock_dynamics": {"ars_co2_reduction_kg": 0.5},
        }
    )
    backend.set_subsystem_failure("ars", True)
    before = backend.poll_telemetry().co2_storage_kg
    result = backend.send_air_revitalisation_goal(ArsGoal(initial_co2_mass=1.8))
    assert result.success is False
    assert backend.poll_telemetry().co2_storage_kg == before


def test_loop_mock_rejects_negative_request_o2():
    backend = LoopMockEclssBackend(
        {"simulation": {"initial_o2_storage_kg": 0.5}, "mock_dynamics": {}}
    )
    before = backend.poll_telemetry().o2_storage_kg
    result = backend.request_o2(-0.1)
    assert result.success is False
    assert backend.poll_telemetry().o2_storage_kg == before


def test_llm_operational_parse_rejects_negative_amount():
    team = SsosEclssLoopTeam({"mode": "llm", "team": {"count": 1, "id_prefix": "op"}, "llm": {}})
    cmd, note = team._parse_llm_operational_command(
        {"kind": "request_o2", "payload": {"amount": -5.0}},
        issued_by="op_1",
    )
    assert cmd is None
    assert note is not None


def test_llm_operational_parse_air_revitalisation_and_request_co2():
    team = SsosEclssLoopTeam({"mode": "llm", "team": {"count": 1, "id_prefix": "op"}, "llm": {}})
    cmd, note = team._parse_llm_operational_command(
        {
            "kind": "air_revitalisation",
            "payload": {"initial_co2_mass": 1200.0, "initial_moisture_content": 20.0},
        },
        issued_by="op_1",
    )
    assert note is None
    assert cmd is not None
    assert cmd.kind == "air_revitalisation"
    assert cmd.payload["initial_co2_mass"] == 1200.0

    cmd2, note2 = team._parse_llm_operational_command(
        {"kind": "request_co2", "payload": {"amount": 15.0}},
        issued_by="op_1",
    )
    assert note2 is None
    assert cmd2 is not None
    assert cmd2.payload["amount"] == 15.0


def test_llm_design_parse_accepts_ssos_change_kinds():
    team = SsosEclssLoopTeam({"mode": "llm", "team": {"count": 1, "id_prefix": "op"}, "llm": {}})
    changes, notes = team._parse_llm_design_proposals(
        [
            {
                "change_kind": "action_profile",
                "payload": {
                    "subsystem": "ars",
                    "action": "air_revitalisation",
                    "fields": {"initial_co2_mass": 2000.0},
                },
            },
            {
                "change_kind": "set_parameter",
                "payload": {"target": "agents.policy.co2_storage_high_kg", "value": 1600.0},
            },
        ]
    )
    assert not notes
    assert len(changes) == 2
    assert changes[0]["change_kind"] == "action_profile"


def test_llm_design_parse_rejects_unknown_action_profile_fields():
    team = SsosEclssLoopTeam({"mode": "llm", "team": {"count": 1, "id_prefix": "op"}, "llm": {}})
    changes, notes = team._parse_llm_design_proposals(
        [
            {
                "change_kind": "action_profile",
                "payload": {
                    "subsystem": "ogs",
                    "fields": {
                        "input_water_mass": 10.0,
                        "duration_steps": 5,
                    },
                },
            }
        ]
    )
    assert changes == []
    assert notes

