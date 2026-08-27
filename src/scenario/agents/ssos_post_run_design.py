"""Post-run ECLSS design agent — separate from in-sim actors."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.agents.memory import TeamMemoryStore
from core.agents.persona import (
    PersonaAgent,
    TeamConfig,
    build_personas,
    eclss_design_proposal_contract,
    load_team,
    message_contract,
    run_parallel,
)
from core.agents.types import AgentMessage, DeliberationPhase
from core.llm.base import LLMClient
from core.llm.factory import build_llm_client
from scenario.ssos_eclss_loop.design_proposals import (
    DESIGN_DOMAIN,
    SSOS_CHANGE_KINDS,
    build_design_proposals_from_run,
    validate_ssos_proposal_change,
)


@dataclass
class ActorTeamSnapshot:
    agent_ids: List[str] = field(default_factory=list)
    mode: str = "none"
    state: Dict[str, Any] = field(default_factory=dict)
    discourse: List[AgentMessage] = field(default_factory=list)
    policy: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DesignReviewBundle:
    summary: Dict[str, Any]
    scenario_config: Dict[str, Any]
    baseline_graph: Dict[str, Any]
    policy: Dict[str, Any]
    actor_snapshot: Optional[ActorTeamSnapshot] = None
    prior_runs: List[Dict[str, Any]] = field(default_factory=list)


def post_run_message_step(summary: Dict[str, Any]) -> int:
    """Last 0-based simulation step (``0 .. steps-1``).

    Designer messages must land on a telemetry step so dashboard replay
    (bounded by telemetry min/max) can show them.
    """
    steps = int(summary.get("steps", 0) or 0)
    return max(steps - 1, 0)


class PostRunDesignAgent:
    """Homogeneous designer team invoked only after the simulation loop."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.mode = config.get("mode", "none")
        self.llm_mode = self.mode == "llm"
        self.llm_client = self._build_llm_client(config.get("llm", {})) if self.llm_mode else None
        team_cfg = dict(config)
        team_raw = dict(team_cfg.get("team") or {})
        team_raw.setdefault("id_prefix", "eclss_designer")
        team_raw.setdefault("count", 4)
        team_cfg["team"] = team_raw
        self.team_cfg: TeamConfig = load_team(team_cfg)
        self.personas = build_personas(self.team_cfg)
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

    def propose(self, bundle: DesignReviewBundle) -> Dict[str, Any]:
        baseline_graph = dict(bundle.baseline_graph or {})
        if self.llm_mode:
            return self._llm_propose(bundle, baseline_graph)
        proposed_by = self.team_cfg.agent_ids[0] if self.team_cfg.agent_ids else "eclss_designer_1"
        proposals = build_design_proposals_from_run(
            proposed_by=proposed_by,
            decision_source="rule",
            policy=bundle.policy,
            summary=bundle.summary,
            baseline_graph=baseline_graph or None,
            prior_runs=bundle.prior_runs,
        )
        proposals["deliberation_messages"] = [
            AgentMessage(
                step=post_run_message_step(bundle.summary),
                from_role=proposed_by,
                to_role="team",
                message=str(proposals.get("message") or ""),
                message_type="comment",
                reasoning=str(proposals.get("reasoning") or ""),
                metadata={
                    "decision_source": "rule",
                    "deliberation_phase": DeliberationPhase.POST_RUN,
                },
            ).to_dict()
        ]
        return proposals

    def _rep_id(self, summary: Dict[str, Any]) -> str:
        # Designers are a separate team from actors. Labeled always uses
        # designer[0] as the rule speaker. LLM rotates on the *designer* roster
        # using the final step index — not TeamConfig.action_rep_index, which
        # addresses in-sim actors.
        steps = post_run_message_step(summary)
        index = steps % self.team_cfg.count
        return self.team_cfg.agent_ids[index]

    def _llm_propose(
        self,
        bundle: DesignReviewBundle,
        baseline_graph: Dict[str, Any],
    ) -> Dict[str, Any]:
        situation = build_llm_post_run_situation(bundle)
        contract = message_contract()
        step = post_run_message_step(bundle.summary)
        actor_discourse = list((bundle.actor_snapshot.discourse if bundle.actor_snapshot else [])[-8:])
        turns = run_parallel(
            [
                self._deliberation_turn(
                    agent_id=agent_id,
                    step=step,
                    situation=situation,
                    team_discourse=actor_discourse,
                    contract=contract,
                )
                for agent_id in self.team_cfg.agent_ids
            ]
        )
        step_discourse: List[AgentMessage] = []
        for agent_id, parsed in zip(self.team_cfg.agent_ids, turns):
            if parsed is None:
                continue
            step_discourse.append(
                AgentMessage(
                    step=step,
                    from_role=agent_id,
                    to_role="team",
                    message=str(parsed.data.get("message", "")),
                    message_type="comment",
                    reasoning=str(parsed.data.get("reasoning", "")),
                    metadata={
                        "decision_source": "llm",
                        "deliberation_phase": DeliberationPhase.DELIBERATION,
                    },
                )
            )

        rep = self._rep_id(bundle.summary)
        design_contract = eclss_design_proposal_contract()
        agent = self.agents[rep]
        ctx = agent.build_context(
            step=step,
            phase=DeliberationPhase.POST_RUN,
            situation=situation,
            step_discourse=step_discourse,
            team_discourse=actor_discourse + step_discourse,
        )
        parsed = agent.deliberate(
            ctx,
            design_contract,
            PersonaAgent.phase_hint(DeliberationPhase.POST_RUN),
            ("message", "reasoning", "changes"),
        )
        if parsed is None:
            fallback = build_design_proposals_from_run(
                proposed_by=rep,
                decision_source="llm_parse_fail",
                policy=bundle.policy,
                summary=bundle.summary,
                message="LLM response could not be parsed; fell back to rule proposals.",
                baseline_graph=baseline_graph or None,
                prior_runs=bundle.prior_runs,
            )
            fallback["reasoning"] = "LLM response could not be parsed."
            fallback["deliberation_messages"] = [
                msg.to_dict() for msg in step_discourse
            ] + [
                AgentMessage(
                    step=step,
                    from_role=rep,
                    to_role="team",
                    message=str(fallback.get("message") or ""),
                    message_type="comment",
                    reasoning="LLM response could not be parsed; using rule fallback.",
                    metadata={
                        "decision_source": "llm_parse_fail",
                        "deliberation_phase": DeliberationPhase.POST_RUN,
                    },
                ).to_dict()
            ]
            return fallback

        changes, parse_notes = parse_llm_design_proposals(parsed.data.get("changes", []))
        return {
            "design_domain": DESIGN_DOMAIN,
            "proposed_by": rep,
            "decision_source": "llm",
            "message": str(parsed.data.get("message", "")),
            "reasoning": str(parsed.data.get("reasoning", "")),
            "changes": changes,
            "baseline_graph": baseline_graph,
            "parse_status": parsed.status,
            "parse_error": parsed.error,
            "parse_notes": parse_notes,
            "raw_response_excerpt": parsed.raw_excerpt,
            "deliberation_messages": [msg.to_dict() for msg in step_discourse]
            + [
                AgentMessage(
                    step=step,
                    from_role=rep,
                    to_role="team",
                    message=str(parsed.data.get("message", "")),
                    message_type="comment",
                    reasoning=str(parsed.data.get("reasoning", "")),
                    metadata={
                        "decision_source": "llm",
                        "deliberation_phase": DeliberationPhase.POST_RUN,
                    },
                ).to_dict()
            ],
        }

    async def _deliberation_turn(
        self,
        *,
        agent_id: str,
        step: int,
        situation: str,
        team_discourse: List[AgentMessage],
        contract: str,
    ):
        agent = self.agents[agent_id]
        ctx = agent.build_context(
            step=step,
            phase=DeliberationPhase.DELIBERATION,
            situation=situation,
            step_discourse=[],
            team_discourse=team_discourse,
        )
        return await agent.deliberate_async(
            ctx,
            contract,
            PersonaAgent.phase_hint(DeliberationPhase.DELIBERATION),
            ("message", "reasoning"),
        )

    @staticmethod
    def _build_llm_client(llm_cfg: Dict[str, Any]) -> LLMClient:
        return build_llm_client(llm_cfg)


def parse_llm_design_proposals(raw_changes: Any) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Accept every valid change. One representative may emit any count."""
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
        if change_kind not in SSOS_CHANGE_KINDS:
            notes.append(f"unsupported change_kind: {change_kind}")
            continue
        if validate_ssos_proposal_change(change_kind, payload) is None:
            notes.append(f"invalid payload for {change_kind}")
            continue
        accepted.append({"change_kind": change_kind, "payload": payload})
    return accepted, notes


def build_llm_post_run_situation(bundle: DesignReviewBundle) -> str:
    from scenario.jobs.design_history import format_prior_runs_for_prompt

    summary = bundle.summary
    sim = bundle.scenario_config.get("simulation") or {}
    thresholds = bundle.scenario_config.get("thresholds") or {}
    snapshot = bundle.actor_snapshot
    telemetry_summary = (
        f"steps={summary.get('steps')}, peak_co2_storage_kg={summary.get('peak_co2_storage_kg')}, "
        f"min_o2_storage_kg={summary.get('min_o2_storage_kg')}, "
        f"final_co2_storage_kg={summary.get('final_co2_storage_kg')}, "
        f"final_o2_storage_kg={summary.get('final_o2_storage_kg')}, "
        f"crew_initial={summary.get('crew_initial')}, "
        f"crew_remaining={summary.get('crew_remaining')}, "
        f"operational_command_count={summary.get('operational_command_count')}, "
        f"ars_invoked_step={summary.get('ars_invoked_step')}, "
        f"ogs_invoked_step={summary.get('ogs_invoked_step')}, "
        f"co2_requested_step={summary.get('co2_requested_step')}"
    )
    initials = (
        f"initial_co2_storage_kg={sim.get('initial_co2_storage_kg')}, "
        f"initial_o2_storage_kg={sim.get('initial_o2_storage_kg')}, "
        f"initial_product_water_l={sim.get('initial_product_water_l')}"
    )
    # Thresholds are supervision stubs for context — not a pass/fail verdict.
    req_stubs = json.dumps(thresholds, ensure_ascii=False)
    final_health = json.dumps(summary.get("final_health") or {}, ensure_ascii=False)
    actor_state = json.dumps(snapshot.state if snapshot else {}, ensure_ascii=False, default=str)
    discourse = snapshot.discourse if snapshot else []
    discourse_lines = (
        "\n".join(f"- {msg.from_role}: {msg.message}" for msg in discourse[-8:]) or "(none)"
    )
    graph = json.dumps(bundle.baseline_graph, ensure_ascii=False)
    prior_block = format_prior_runs_for_prompt(list(bundle.prior_runs or []))
    return (
        "Post-run SSOS graph design review. Simulation complete. "
        "Review prior loop runs and the current run before proposing changes. "
        "Do not judge verification pass/fail. "
        "One representative emits changes; include as many proposals as needed "
        "(no count cap).\n\n"
        f"### Prior loop runs\n{prior_block}\n\n"
        f"### Initial conditions\n{initials}\n\n"
        f"### Verification requirement stubs (context only)\n{req_stubs}\n\n"
        f"### Telemetry (current run)\n{telemetry_summary}\n\n"
        f"### World state\n{final_health}\n\n"
        f"### Actor final state\n{actor_state}\n\n"
        f"### Actor discourse (recent)\n{discourse_lines}\n\n"
        f"Baseline ssos_graph at run end: {graph}"
    )


def actor_snapshot_from_team(team: Any) -> ActorTeamSnapshot:
    state = asdict(team.state) if hasattr(team, "state") else {}
    discourse = []
    if getattr(team, "memory_store", None) is not None:
        discourse = list(team.memory_store.discourse.recent())
    return ActorTeamSnapshot(
        agent_ids=list(getattr(team.team_cfg, "agent_ids", [])),
        mode=str(getattr(team, "mode", "none")),
        state=state,
        discourse=discourse,
        policy=dict(getattr(team, "policy", {}) or {}),
    )
