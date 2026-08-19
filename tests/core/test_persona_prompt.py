from core.agents.base import DeliberationContext, Persona
from core.agents.persona import (
    MESSAGE_WORD_LIMIT,
    REASONING_WORD_LIMIT,
    PersonaAgent,
    PersonaPromptBuilder,
    load_team,
    message_contract,
)
from core.agents.types import AgentMessage, DeliberationPhase
from scenario.agents.scrubber_degradation_team import build_llm_situation
from scenario.agents.types import AgentObservation
from environment.protocol import HealthMetrics, HealthStatus, TelemetrySnapshot


def test_persona_prompt_includes_memory_discourse_and_markers():
    persona = Persona(
        agent_id="engineer_1",
        persona="Speak when CO2 drifts.",
    )
    ctx = DeliberationContext(
        step=5,
        phase=DeliberationPhase.DELIBERATION,
        situation="### Telemetry\nstep=5, co2_ppm=950",
        step_discourse=[],
        team_discourse=[
            AgentMessage(
                step=4,
                from_role="engineer_2",
                to_role="team",
                message="degradation suspected",
                message_type="comment",
            )
        ],
        agent_memory=["step 3: noted rising CO2"],
    )
    prompt = PersonaPromptBuilder.build(
        persona,
        ctx,
        message_contract(),
        "Open forum.",
    )
    assert "agent_id: engineer_1" in prompt
    assert "phase: deliberation" in prompt
    assert "Main role:" not in prompt
    assert "Speak when CO2 drifts." in prompt
    assert "degradation suspected" in prompt
    assert "noted rising CO2" in prompt
    assert "## Your memory" in prompt
    assert "## Team discourse" in prompt
    assert f"at most {MESSAGE_WORD_LIMIT} words" in prompt
    assert f"at most {REASONING_WORD_LIMIT} words" in prompt


def test_load_team_builds_engineer_ids():
    team = load_team({"team": {"count": 3, "id_prefix": "engineer"}})
    assert team.agent_ids == ("engineer_1", "engineer_2", "engineer_3")
    assert team.action_rep_id(1) == "engineer_1"
    assert team.action_rep_id(2) == "engineer_2"


def test_action_round_hint_default_matches_single_rep():
    assert "team representative" in PersonaAgent.action_round_hint()
    assert PersonaAgent.phase_hint(DeliberationPhase.ACTION) == PersonaAgent.action_round_hint()


def test_action_round_hint_names_slot_when_multiple_reps():
    hint = PersonaAgent.action_round_hint(n_reps=8, slot=2)
    assert "action representative 3 of 8" in hint
    assert "simultaneous" in hint


def test_llm_situation_has_telemetry_and_world_state_without_policy():
    obs = AgentObservation(
        step=3,
        telemetry=TelemetrySnapshot(
            step=3,
            co2_ppm=1100.0,
            scrubber_efficiency=0.8,
            power_margin_w=10.0,
            fan_speed=0.9,
            bypass_enabled=False,
            load_reduced=False,
            anomaly_flags=["scrubber_degradation"],
            eps_support_w=0.0,
            eps_support_steps_remaining=0,
        ),
        health=HealthMetrics(
            step=3,
            co2_status=HealthStatus.WARNING,
            power_status=HealthStatus.SAFE,
            overall=HealthStatus.WARNING,
        ),
    )
    situation = build_llm_situation(obs)
    assert "### Telemetry" in situation
    assert "### World state" in situation
    assert "### Recovery levers" in situation
    assert "request_eps_boost: value is support_watts" in situation
    assert "power_margin_w is the running margin" in situation
    assert "co2_status=warning" in situation
    assert "Rule thresholds" not in situation
    assert "co2_recovery_ppm" not in situation
    assert "eps_boost_w" not in situation
