"""
Scrubber degradation agent team — rule-based labeled_rule_base mode + homogeneous LLM mode.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from core.agents.base import Team
from core.agents.memory import TeamMemoryStore
from core.agents.persona import (
    PersonaAgent,
    TeamConfig,
    build_personas,
    design_proposal_contract,
    load_team,
    message_contract,
    operator_action_contract,
)
from core.agents.types import (
    AgentMessage,
    AgentObservation,
    DeliberationPhase,
    StepAgentOutcome,
)
from core.llm.ollama import OllamaClient, resolve_ollama_base_url
from environment.protocol import (
    CommandKind,
    HealthMetrics,
    HealthStatus,
    RecoveryCommand,
    SimulatorProtocol,
)
from environment.scrubber.eclss_ops.telemetry import CO2_RECOVERY_PPM


@dataclass
class ScrubberTeamState:
    fan_boost_applied: bool = False
    bypass_enabled: bool = False
    load_reduced: bool = False
    alert_sent: bool = False
    eps_boost_requested: bool = False


class ScrubberDegradationTeam(Team):
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.mode = config.get("mode", "labeled_rule_base")
        self.state = ScrubberTeamState()
        self.llm_mode = self.mode == "llm"
        self.llm_enabled = self.llm_mode
        self.llm_client = self._build_llm_client(config.get("llm", {})) if self.llm_enabled else None

        self.team_cfg: TeamConfig = load_team(config)
        self.personas = build_personas(self.team_cfg)
        self.policy: Dict[str, Any] = (
            config.get("policy", {}) if self.mode == "labeled_rule_base" else {}
        )

        self.memory_store = TeamMemoryStore(
            agent_ids=list(self.personas.keys()),
            memory_limit=int(config.get("memory_limit", 8)),
            discourse_window=int(config.get("discourse_window", 12)),
        )
        self.agents: Dict[str, PersonaAgent] = {
            agent_id: PersonaAgent(
                persona=persona,
                memory=self.memory_store.agent_memories[agent_id],
                llm_client=self.llm_client,
            )
            for agent_id, persona in self.personas.items()
        }

    def run_step(self, sim: SimulatorProtocol, obs: AgentObservation) -> StepAgentOutcome:
        if self.llm_mode:
            outcome = self._run_step_llm(obs)
            self.memory_store.commit_step(outcome)
            return outcome
        return self._run_step_labeled(obs)

    def apply_outcome(self, sim: SimulatorProtocol, outcome: StepAgentOutcome) -> None:
        for cmd in outcome.commands:
            sim.apply_command(cmd)

    def _run_step_llm(self, obs: AgentObservation) -> StepAgentOutcome:
        outcome = StepAgentOutcome()
        step_discourse: List[AgentMessage] = []
        situation = build_llm_situation(obs)

        for agent_id in self.team_cfg.agent_ids:
            msg = self._llm_deliberation_turn(
                obs=obs,
                agent_id=agent_id,
                to_role="team",
                message_type="comment",
                phase=DeliberationPhase.DELIBERATION,
                situation=situation,
                step_discourse=step_discourse,
                contract=message_contract(),
                required=("message",),
            )
            if msg is not None:
                outcome.messages.append(msg)
                step_discourse.append(msg)
            else:
                outcome.messages.append(
                    self._llm_skip(
                        obs=obs,
                        agent_id=agent_id,
                        phase=DeliberationPhase.DELIBERATION,
                        reason="parse_failed_or_empty_message",
                        decision_source="llm_parse_fail",
                    )
                )

        rep = self.team_cfg.action_rep_id(obs.step)
        action_msgs, action_cmds = self._llm_action_turn(obs, situation, step_discourse, rep)
        outcome.messages.extend(action_msgs)
        outcome.commands.extend(action_cmds)
        return outcome

    def _run_step_labeled(self, obs: AgentObservation) -> StepAgentOutcome:
        outcome = StepAgentOutcome()
        rep = self.team_cfg.action_rep_id(obs.step)
        recovery_ppm = float(self.policy.get("co2_recovery_ppm", CO2_RECOVERY_PPM))
        agent_ids = self.team_cfg.agent_ids
        n = len(agent_ids)

        if obs.telemetry.co2_ppm >= recovery_ppm and not self.state.alert_sent:
            commenter = agent_ids[obs.step % n]
            self.state.alert_sent = True
            outcome.messages.append(
                AgentMessage(
                    step=obs.step,
                    from_role=commenter,
                    to_role="team",
                    message=(
                        f"CO2 at {obs.telemetry.co2_ppm:.0f} ppm exceeds recovery band "
                        f"{recovery_ppm:.0f} ppm."
                    ),
                    message_type="alert",
                    reasoning="Telemetry threshold crossed.",
                    metadata=self._rule_metadata(),
                )
            )

        if obs.telemetry.anomaly_flags:
            commenter = agent_ids[(obs.step + 1) % n]
            eff = obs.telemetry.scrubber_efficiency
            outcome.messages.append(
                AgentMessage(
                    step=obs.step,
                    from_role=commenter,
                    to_role="team",
                    message=(
                        f"Active anomalies: {', '.join(obs.telemetry.anomaly_flags)}. "
                        f"Scrubber efficiency {eff:.2f}; suspect degradation with rising cabin load."
                    ),
                    message_type="diagnosis",
                    reasoning="Anomaly flags present in telemetry.",
                    metadata=self._rule_metadata(),
                )
            )

        messages, commands = self._labeled_recovery(obs, rep, recovery_ppm)
        outcome.messages.extend(messages)
        outcome.commands.extend(commands)
        return outcome

    def _labeled_recovery(
        self,
        obs: AgentObservation,
        rep: str,
        recovery_ppm: float,
    ) -> Tuple[List[AgentMessage], List[RecoveryCommand]]:
        messages: List[AgentMessage] = []
        commands: List[RecoveryCommand] = []

        if obs.telemetry.co2_ppm >= recovery_ppm and not self.state.fan_boost_applied:
            fan = float(self.policy.get("fan_speed", 1.0))
            commands.append(
                RecoveryCommand(kind=CommandKind.SET_FAN_SPEED, value=fan, issued_by=rep)
            )
            self.state.fan_boost_applied = True
            messages.append(
                AgentMessage(
                    step=obs.step,
                    from_role=rep,
                    to_role="team",
                    message=f"Increasing fan speed to {fan} to boost scrub rate.",
                    message_type="recovery_command",
                    reasoning=f"CO2 {obs.telemetry.co2_ppm:.0f} ppm >= {recovery_ppm:.0f}.",
                    metadata=self._rule_metadata(),
                )
            )

        if (
            self.policy.get("reduce_load_on_power_critical", True)
            and obs.health.power_status == HealthStatus.CRITICAL
            and not self.state.load_reduced
        ):
            commands.append(
                RecoveryCommand(kind=CommandKind.REDUCE_LOAD, value=True, issued_by=rep)
            )
            self.state.load_reduced = True
            messages.append(
                AgentMessage(
                    step=obs.step,
                    from_role=rep,
                    to_role="team",
                    message="Reducing cabin metabolic load to lower CO2 production.",
                    message_type="recovery_command",
                    reasoning="Power margin critical; load shedding.",
                    metadata=self._rule_metadata(),
                )
            )

        if (
            self.policy.get("reduce_load_on_co2_high", True)
            and obs.telemetry.co2_ppm >= recovery_ppm
            and not self.state.load_reduced
        ):
            commands.append(
                RecoveryCommand(kind=CommandKind.REDUCE_LOAD, value=True, issued_by=rep)
            )
            self.state.load_reduced = True
            messages.append(
                AgentMessage(
                    step=obs.step,
                    from_role=rep,
                    to_role="team",
                    message="Reducing cabin metabolic load to drive CO2 below recovery band.",
                    message_type="recovery_command",
                    reasoning=f"CO2 {obs.telemetry.co2_ppm:.0f} ppm >= {recovery_ppm:.0f}; load shedding.",
                    metadata=self._rule_metadata(),
                )
            )

        if (
            self.policy.get("request_eps_boost_on_power_critical", True)
            and obs.health.power_status == HealthStatus.CRITICAL
            and obs.telemetry.eps_support_steps_remaining == 0
        ):
            eps_boost_w = float(self.policy.get("eps_boost_w", 120.0))
            commands.append(
                RecoveryCommand(kind=CommandKind.REQUEST_EPS_BOOST, value=eps_boost_w, issued_by=rep)
            )
            self.state.eps_boost_requested = True
            messages.append(
                AgentMessage(
                    step=obs.step,
                    from_role=rep,
                    to_role="team",
                    message=f"Requesting EPS support boost of {eps_boost_w:.0f} W.",
                    message_type="recovery_command",
                    reasoning="Power margin critical; requesting temporary EPS assist.",
                    metadata=self._rule_metadata(),
                )
            )

        if (
            self.policy.get("enable_bypass", True)
            and obs.telemetry.co2_ppm >= recovery_ppm
            and self.state.fan_boost_applied
            and not self.state.bypass_enabled
        ):
            commands.append(
                RecoveryCommand(kind=CommandKind.ENABLE_BYPASS, value=True, issued_by=rep)
            )
            self.state.bypass_enabled = True
            messages.append(
                AgentMessage(
                    step=obs.step,
                    from_role=rep,
                    to_role="team",
                    message="Enabling temporary bypass flow to increase scrub throughput.",
                    message_type="recovery_command",
                    reasoning="Fan boost insufficient; engaging bypass.",
                    metadata=self._rule_metadata(),
                )
            )

        return messages, commands

    def propose_post_run_design(
        self,
        sim: SimulatorProtocol,
        summary: Dict[str, Any],
    ) -> Dict[str, Any]:
        baseline = sim.get_design_state().to_dict()
        steps = int(summary.get("steps", 0))
        rep = self.team_cfg.action_rep_id(steps)
        if self.llm_mode:
            return self._llm_post_run_design_proposal(summary, baseline, rep)
        return self._rule_post_run_design_proposal(summary, baseline, rep)

    def _llm_deliberation_turn(
        self,
        *,
        obs: AgentObservation,
        agent_id: str,
        to_role: str,
        message_type: str,
        phase: str,
        situation: str,
        step_discourse: List[AgentMessage],
        contract: str,
        required: tuple[str, ...],
    ) -> Optional[AgentMessage]:
        agent = self.agents[agent_id]
        ctx = agent.build_context(
            step=obs.step,
            phase=phase,
            situation=situation,
            step_discourse=step_discourse,
            team_discourse=self.memory_store.discourse.recent(),
        )
        parsed = agent.deliberate(
            ctx,
            contract,
            PersonaAgent.phase_hint(phase),
            required,
        )
        if parsed is None:
            return None
        message = str(parsed.data.get("message", "")).strip()
        if not message:
            return None
        metadata: Dict[str, Any] = {
            "decision_source": "llm",
            "deliberation_phase": phase,
            "parse_status": parsed.status,
            "parse_error": parsed.error,
            "raw_response_excerpt": parsed.raw_excerpt,
        }
        llm_memory = parsed.data.get("memory")
        if llm_memory:
            metadata["llm_memory"] = str(llm_memory)
        return AgentMessage(
            step=obs.step,
            from_role=agent_id,
            to_role=to_role,
            message=message,
            message_type=message_type,
            reasoning=str(parsed.data.get("reasoning", "")),
            metadata=metadata,
        )

    def _llm_action_turn(
        self,
        obs: AgentObservation,
        situation: str,
        step_discourse: List[AgentMessage],
        rep: str,
    ) -> Tuple[List[AgentMessage], List[RecoveryCommand]]:
        contract = operator_action_contract()
        agent = self.agents[rep]
        ctx = agent.build_context(
            step=obs.step,
            phase=DeliberationPhase.ACTION,
            situation=situation,
            step_discourse=step_discourse,
            team_discourse=self.memory_store.discourse.recent(),
        )
        parsed = agent.deliberate(
            ctx,
            contract,
            PersonaAgent.phase_hint(DeliberationPhase.ACTION),
            ("commands",),
        )
        if parsed is None:
            return [
                self._llm_skip(
                    obs=obs,
                    agent_id=rep,
                    phase=DeliberationPhase.ACTION,
                    reason="parse_failed",
                    decision_source="llm_parse_fail",
                )
            ], []

        message = parsed.data.get("message", "Assessed current state.")
        reasoning = parsed.data.get("reasoning", "")
        commands: List[RecoveryCommand] = []
        parse_notes: List[str] = []
        raw_commands = parsed.data.get("commands", [])
        if not isinstance(raw_commands, list):
            raw_commands = []

        for item in raw_commands:
            cmd, note = self._parse_llm_operator_command(item, issued_by=rep)
            if note:
                parse_notes.append(note)
            if cmd is not None:
                commands.append(cmd)

        base_meta: Dict[str, Any] = {
            "decision_source": "llm",
            "deliberation_phase": DeliberationPhase.ACTION,
            "parse_status": parsed.status,
            "parse_error": parsed.error,
            "raw_response_excerpt": parsed.raw_excerpt,
            "parse_notes": parse_notes,
        }
        if parsed.data.get("memory"):
            base_meta["llm_memory"] = str(parsed.data["memory"])

        if not commands:
            return [
                self._llm_skip(
                    obs=obs,
                    agent_id=rep,
                    phase=DeliberationPhase.ACTION,
                    reason="empty_commands",
                    decision_source="llm_no_action",
                    parse_status=parsed.status,
                    parse_error=parsed.error,
                )
            ], []

        llm_msg = AgentMessage(
            step=obs.step,
            from_role=rep,
            to_role="team",
            message=str(message),
            message_type="recovery_command",
            reasoning=str(reasoning),
            metadata=base_meta,
        )
        return [llm_msg], commands

    def _llm_post_run_design_proposal(
        self,
        summary: Dict[str, Any],
        baseline: Dict[str, Any],
        rep: str,
    ) -> Dict[str, Any]:
        steps = int(summary.get("steps", 0))
        final_health_raw = summary.get("final_health") or {}
        final_health = HealthMetrics(
            step=int(final_health_raw.get("step", steps)),
            co2_status=HealthStatus(final_health_raw.get("co2_status", "SAFE")),
            power_status=HealthStatus(final_health_raw.get("power_status", "SAFE")),
            overall=HealthStatus(final_health_raw.get("overall", "SAFE")),
        )
        situation = build_llm_post_run_situation(
            summary,
            final_health,
            self.memory_store.discourse.recent(),
            baseline,
        )
        contract = design_proposal_contract()
        agent = self.agents[rep]
        ctx = agent.build_context(
            step=steps,
            phase=DeliberationPhase.POST_RUN,
            situation=situation,
            step_discourse=[],
            team_discourse=self.memory_store.discourse.recent(),
        )
        parsed = agent.deliberate(
            ctx,
            contract,
            PersonaAgent.phase_hint(DeliberationPhase.POST_RUN),
            ("message", "reasoning", "changes"),
        )
        if parsed is None:
            return {
                "proposed_by": rep,
                "decision_source": "llm_parse_fail",
                "message": "",
                "reasoning": "LLM response could not be parsed.",
                "changes": [],
                "baseline_topology": baseline.get("topology", {}),
            }

        changes, parse_notes = self._parse_llm_design_proposals(parsed.data.get("changes", []), rep)
        return {
            "proposed_by": rep,
            "decision_source": "llm",
            "message": str(parsed.data.get("message", "")),
            "reasoning": str(parsed.data.get("reasoning", "")),
            "changes": changes,
            "baseline_topology": baseline.get("topology", {}),
            "parse_status": parsed.status,
            "parse_error": parsed.error,
            "parse_notes": parse_notes,
            "raw_response_excerpt": parsed.raw_excerpt,
        }

    def _rule_post_run_design_proposal(
        self,
        summary: Dict[str, Any],
        baseline: Dict[str, Any],
        rep: str,
    ) -> Dict[str, Any]:
        co2_threshold = float(self.policy.get("co2_recovery_ppm", CO2_RECOVERY_PPM))
        peak = float(summary.get("peak_co2_ppm", 0))
        anomaly_seen = bool(summary.get("anomaly_seen"))
        if peak < co2_threshold and not anomaly_seen:
            return {
                "proposed_by": rep,
                "decision_source": "rule",
                "message": "No structural topology changes recommended after this run.",
                "reasoning": (
                    f"Peak CO2 {peak:.0f} ppm stayed below recovery threshold "
                    f"{co2_threshold:.0f} ppm with no sustained anomaly."
                ),
                "changes": [],
                "baseline_topology": baseline.get("topology", {}),
            }

        edge = self.policy.get("bypass_edge", {})
        changes = [
            {
                "change_kind": "add_edge",
                "payload": {
                    "node_a": edge.get("node_a", "manifold"),
                    "node_b": edge.get("node_b", "scrubber"),
                    "kind": edge.get("kind", "bypass"),
                },
            }
        ]
        return {
            "proposed_by": rep,
            "decision_source": "rule",
            "message": "Propose permanent bypass plumbing between manifold and scrubber.",
            "reasoning": (
                "Repeated anomaly and high CO2 during the run; temporary ops may be insufficient "
                "for long-term resilience."
            ),
            "changes": changes,
            "baseline_topology": baseline.get("topology", {}),
        }

    def _parse_llm_design_proposals(
        self,
        raw_changes: Any,
        proposed_by: str,
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        if not isinstance(raw_changes, list):
            return [], ["changes is not a list"]
        accepted: List[Dict[str, Any]] = []
        notes: List[str] = []
        for item in raw_changes:
            if not isinstance(item, dict):
                notes.append("change item is not an object")
                continue
            change_kind = str(item.get("change_kind", "")).strip()
            payload = item.get("payload", {})
            if not isinstance(payload, dict):
                payload = {}
            if self._validate_proposal_change(
                change_kind=change_kind,
                payload=payload,
            ) is None:
                notes.append(f"unparsed change: {change_kind}")
                continue
            accepted.append({"change_kind": change_kind, "payload": payload})
        return accepted, notes

    def _llm_skip(
        self,
        *,
        obs: AgentObservation,
        agent_id: str,
        phase: str,
        reason: str,
        decision_source: str,
        **extra: Any,
    ) -> AgentMessage:
        metadata: Dict[str, Any] = {
            "decision_source": decision_source,
            "deliberation_phase": phase,
            "skip_reason": reason,
        }
        metadata.update(extra)
        return AgentMessage(
            step=obs.step,
            from_role=agent_id,
            to_role="team",
            message="",
            message_type="skip",
            reasoning=reason,
            metadata=metadata,
        )

    @staticmethod
    def _coerce_boolean(value: Any) -> Tuple[Optional[bool], Optional[str]]:
        if isinstance(value, bool):
            return value, None
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized == "true":
                return True, None
            if normalized in {"false", "0", "no"}:
                return False, None
        return None, 'value must be boolean or "true"/"false" string'

    def _parse_llm_operator_command(
        self,
        item: Any,
        *,
        issued_by: str,
    ) -> Tuple[Optional[RecoveryCommand], Optional[str]]:
        """Parse LLM operator JSON into a command without team-level policy guards."""
        if not isinstance(item, dict):
            return None, "operator command is not an object"
        kind = str(item.get("kind", "")).strip()
        value = item.get("value")
        if kind == "set_fan_speed":
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                return None, "invalid fan speed value"
            return (
                RecoveryCommand(kind=CommandKind.SET_FAN_SPEED, value=numeric, issued_by=issued_by),
                None,
            )
        if kind == "enable_bypass":
            coerced, coerce_error = self._coerce_boolean(value)
            if coerce_error is not None:
                return None, coerce_error
            return (
                RecoveryCommand(kind=CommandKind.ENABLE_BYPASS, value=coerced, issued_by=issued_by),
                None,
            )
        if kind == "reduce_load":
            coerced, coerce_error = self._coerce_boolean(value)
            if coerce_error is not None:
                return None, coerce_error
            return (
                RecoveryCommand(kind=CommandKind.REDUCE_LOAD, value=coerced, issued_by=issued_by),
                None,
            )
        if kind == "request_eps_boost":
            try:
                watts = float(value)
            except (TypeError, ValueError):
                return None, "eps boost value must be numeric"
            return (
                RecoveryCommand(kind=CommandKind.REQUEST_EPS_BOOST, value=watts, issued_by=issued_by),
                None,
            )
        return None, f"unsupported operator command kind: {kind}"

    def _validate_proposal_change(
        self,
        change_kind: str,
        payload: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Validate post-run proposal dict (scrubber frozen schema)."""
        if change_kind == "add_node":
            node_id = str(payload.get("id", "")).strip()
            if not node_id:
                return None
            return {
                "change_kind": change_kind,
                "payload": {
                    "id": node_id,
                    "name": str(payload.get("name", node_id)),
                    "kind": str(payload.get("kind", "volume")),
                },
            }
        if change_kind == "add_edge":
            node_a = payload.get("node_a")
            node_b = payload.get("node_b")
            if not node_a or not node_b:
                return None
            return {
                "change_kind": change_kind,
                "payload": {
                    "node_a": node_a,
                    "node_b": node_b,
                    "kind": payload.get("kind", "bypass"),
                },
            }
        if change_kind == "set_parameter":
            key = str(payload.get("key", "")).strip()
            if not key:
                return None
            try:
                value = float(payload.get("value"))
            except (TypeError, ValueError):
                return None
            return {
                "change_kind": change_kind,
                "payload": {"key": key, "value": value},
            }
        return None

    @staticmethod
    def _build_llm_client(llm_cfg: Dict[str, Any]) -> OllamaClient:
        return OllamaClient(
            base_url=resolve_ollama_base_url(llm_cfg),
            model=str(llm_cfg.get("model", "llama3.2")),
            temperature=float(llm_cfg.get("temperature", 0.45)),
            max_tokens=int(llm_cfg.get("max_tokens", 512)),
            repeat_penalty=float(llm_cfg.get("repeat_penalty", 1.1)),
            repeat_last_n=int(llm_cfg.get("repeat_last_n", 128)),
            min_p=float(llm_cfg.get("min_p", 0.05)),
            think=llm_cfg.get("think", False),
            api_timeout=int(llm_cfg.get("api_timeout", 10)),
        )

    @staticmethod
    def _rule_metadata() -> Dict[str, Any]:
        return {"decision_source": "rule"}


# Scenario facility specs (physics / design defaults — not labeled policy).
_SCRUBBER_RECOVERY_LEVERS = """\
### Recovery levers (facility reference)
- set_fan_speed: command value 0.0–1.0 (fraction of max). Full speed draws ~80 W scrubber fan load.
- enable_bypass: true/false. Temporary bypass adds ~40 W and increases scrub throughput (bypass_flow_bonus).
- reduce_load: true/false. Cuts cabin metabolic CO2 production to ~60% of normal while active.
- request_eps_boost: value is support_watts (W). Arms BCDU battery discharge for 5 steps at that wattage;
  applied support appears in eps_support_w / eps_support_steps_remaining.
- Plant baseline bus draw ~200 W and fan ~80 W (nameplate). Each step converts
  total load watts to power_margin_w via power_draw_to_margin_factor (single scale).
- power_margin_w is the running margin after that conversion (negative = shortfall).
- Size EPS support to the shortfall you observe in power_margin_w; token wattages barely move this plant."""


def build_llm_situation(obs: AgentObservation) -> str:
    telemetry = (
        f"step={obs.step}, co2_ppm={obs.telemetry.co2_ppm:.2f}, "
        f"scrubber_efficiency={obs.telemetry.scrubber_efficiency:.4f}, "
        f"power_margin_w={obs.telemetry.power_margin_w:.2f}, "
        f"fan_speed={obs.telemetry.fan_speed:.2f}, bypass_enabled={obs.telemetry.bypass_enabled}, "
        f"load_reduced={obs.telemetry.load_reduced}, anomaly_flags={obs.telemetry.anomaly_flags}, "
        f"eps_support_w={obs.telemetry.eps_support_w:.2f}, "
        f"eps_support_steps_remaining={obs.telemetry.eps_support_steps_remaining}"
    )
    world_state = (
        f"co2_status={obs.health.co2_status.value}, "
        f"power_status={obs.health.power_status.value}, "
        f"overall={obs.health.overall.value}\n"
        "(Descriptive assessment from the facility monitoring layer — not a command.)"
    )
    return (
        "Scenario: scrubber_degradation. Closed-habitat ECLSS ops.\n\n"
        f"### Telemetry\n{telemetry}\n\n"
        f"### World state\n{world_state}\n\n"
        f"{_SCRUBBER_RECOVERY_LEVERS}"
    )


def build_llm_post_run_situation(
    summary: Dict[str, Any],
    final_health: HealthMetrics,
    discourse: List[AgentMessage],
    baseline: Dict[str, Any],
) -> str:
    steps = int(summary.get("steps", 0))
    telemetry_summary = (
        f"steps={steps}, peak_co2_ppm={summary.get('peak_co2_ppm')}, "
        f"final_co2_ppm={summary.get('final_co2_ppm')}, "
        f"min_power_margin_w={summary.get('min_power_margin_w')}, "
        f"anomaly_seen={summary.get('anomaly_seen')}, "
        f"eps_boost_applied_step={summary.get('eps_boost_applied_step')}"
    )
    world_state = (
        f"co2_status={final_health.co2_status.value}, "
        f"power_status={final_health.power_status.value}, "
        f"overall={final_health.overall.value}\n"
        "(Descriptive assessment from the facility monitoring layer — not a command.)"
    )
    discourse_lines = "\n".join(
        f"- {msg.from_role}: {msg.message}" for msg in discourse[-8:]
    ) or "(none)"
    topology = json.dumps(baseline.get("topology", {}), ensure_ascii=False)
    return (
        "Post-run design review. Simulation complete.\n\n"
        f"### Telemetry\n{telemetry_summary}\n\n"
        f"### World state\n{world_state}\n\n"
        f"### Team discourse (recent)\n{discourse_lines}\n\n"
        f"Baseline topology at run end: {topology}"
    )
