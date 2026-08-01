"""ScrubberDegradationScenario — config, sim build, and run loop."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from core.agents.base import Team
from core.agents.types import AgentObservation
from core.event_log import EventLog
from core.scenario import Scenario
from environment.scrubber.eclss_ops.telemetry import CO2_RECOVERY_PPM, compute_health_metrics
from environment.protocol import HealthStatus, SimulatorProtocol
from environment.scrubber.station_simulator import StationSimulator
from environment.scrubber.topics import EVENT_RECOVERY
from integrations.one_piece import export_run_provenance
from scenario.agents.scrubber_degradation_team import ScrubberDegradationTeam
from scenario.jobs.resolve import resolve_run_directory
from scenario.runner import (
    _deep_merge,
    _log_sim_events,
    agents_config_path,
    build_simulator,
    scenario_config_path,
)

logger = logging.getLogger(__name__)


def load_agents_config(name: str, scenario_config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    agents_section = scenario_config.get("agents") or {}
    mode = agents_section.get("mode", "none")
    if mode == "none":
        return None

    agents_path = agents_config_path(name)
    if agents_path.exists():
        with agents_path.open(encoding="utf-8") as f:
            agents_yaml = yaml.safe_load(f) or {}
    else:
        agents_yaml = {}

    merged = _deep_merge(agents_yaml, {k: v for k, v in agents_section.items() if k != "config_file"})
    merged["mode"] = mode
    return merged


class ScrubberDegradationScenario(Scenario):
    @property
    def name(self) -> str:
        return "scrubber_degradation"

    def load_config(self, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        with scenario_config_path(self.name).open(encoding="utf-8") as f:
            config = yaml.safe_load(f)
        if overrides:
            config = _deep_merge(config, overrides)
        return config

    def build_simulator(self, config: Dict[str, Any]) -> SimulatorProtocol:
        return build_simulator(config)

    def build_team(self, config: Dict[str, Any]) -> Optional[Team]:
        agents_config = load_agents_config(self.name, config)
        if not agents_config:
            return None
        mode = agents_config.get("mode")
        if mode not in {"labeled_rule_base", "llm"}:
            return None
        return ScrubberDegradationTeam(agents_config)

    def run(
        self,
        output_dir: Optional[Path] = None,
        overrides: Optional[Dict[str, Any]] = None,
        recreate_output: bool = True,
        run_id: Optional[str] = None,
        results_root: Optional[Path] = None,
    ) -> Path:
        config = self.load_config(overrides)
        agents_config = load_agents_config(self.name, config)
        sim_cfg = config.get("simulation", {})
        steps = int(sim_cfg.get("steps", 50))
        output_cfg = config.get("output", {})

        run_dir = resolve_run_directory(
            scenario_name=self.name,
            output_cfg=output_cfg,
            agents_config=agents_config,
            output_dir=output_dir,
            run_id=run_id,
            results_root=results_root,
            recreate_output=recreate_output,
        )

        sim = self.build_simulator(config)
        team = self.build_team(config)
        log = EventLog(run_dir)

        peak_co2 = 0.0
        min_power_margin_w: Optional[float] = None
        anomaly_seen = False
        co2_above_threshold_step: Optional[int] = None
        co2_recovered_below_threshold_step: Optional[int] = None
        eps_boost_applied_step: Optional[int] = None
        power_recovered_above_critical_step: Optional[int] = None
        message_count = 0
        last_snap = None
        last_health = None
        logged_event_ids: set = set()
        was_power_critical = False
        station = sim if isinstance(sim, StationSimulator) else None

        for _ in range(steps):
            snap = sim.step()
            last_snap = snap
            peak_co2 = max(peak_co2, snap.co2_ppm)
            min_power_margin_w = (
                snap.power_margin_w
                if min_power_margin_w is None
                else min(min_power_margin_w, snap.power_margin_w)
            )
            health = compute_health_metrics(snap)
            last_health = health

            if health.power_status == HealthStatus.CRITICAL:
                was_power_critical = True
            elif was_power_critical and power_recovered_above_critical_step is None:
                power_recovered_above_critical_step = snap.step

            if station is not None:
                log.append("eps_telemetry", station.eps_telemetry_dict(snap.step))

            if snap.anomaly_flags:
                anomaly_seen = True
            if snap.co2_ppm >= CO2_RECOVERY_PPM and co2_above_threshold_step is None:
                co2_above_threshold_step = snap.step
            if snap.co2_ppm < CO2_RECOVERY_PPM and co2_above_threshold_step is not None:
                if co2_recovered_below_threshold_step is None:
                    co2_recovered_below_threshold_step = snap.step

            log.append("telemetry", snap.to_dict())
            log.append("health_metrics", health.to_dict())
            log.append("design_state", {"step": snap.step, **sim.get_design_state().to_dict()})
            _log_sim_events(log, sim, snap.step, logged_event_ids)

            if team is not None:
                obs = AgentObservation(step=snap.step, telemetry=snap, health=health)
                outcome = team.run_step(sim, obs)
                team.apply_outcome(sim, outcome)
                for msg in outcome.messages:
                    log.append("messages", msg.to_dict())
                    message_count += 1
                _log_sim_events(log, sim, snap.step, logged_event_ids)

                # L5: refresh actuator / EPS fields after ops (same step, no physics advance).
                # Append post_ops rows so JSONL matches summary / dashboard (ssos L5 parity).
                if outcome.commands and last_snap is not None:
                    from dataclasses import replace

                    plant = station.eclss if station is not None else sim
                    updates = {
                        "fan_speed": getattr(plant, "fan_speed", last_snap.fan_speed),
                        "bypass_enabled": getattr(plant, "bypass_enabled", last_snap.bypass_enabled),
                        "load_reduced": getattr(plant, "load_reduced", last_snap.load_reduced),
                    }
                    if station is not None:
                        updates["eps_support_w"] = round(station.eps.support_w, 2)
                        updates["eps_support_steps_remaining"] = station.eps.support_steps_remaining
                    last_snap = replace(last_snap, **updates)
                    last_health = compute_health_metrics(last_snap)
                    log.append("telemetry", {"post_ops": True, **last_snap.to_dict()})
                    log.append("health_metrics", {"post_ops": True, **last_health.to_dict()})
                    if station is not None:
                        log.append(
                            "eps_telemetry",
                            {"post_ops": True, **station.eps_telemetry_dict(last_snap.step)},
                        )

        for event in sim.get_events():
            if event.get("kind") != EVENT_RECOVERY:
                continue
            command = event.get("command") or {}
            if command.get("kind") != "request_eps_boost":
                continue
            step = event.get("step")
            if step is not None and eps_boost_applied_step is None:
                eps_boost_applied_step = int(step)

        summary = {
            "scenario": self.name,
            "simulator": "mock_station",
            "agents_mode": (agents_config or {}).get("mode", "none"),
            "steps": steps,
            "peak_co2_ppm": round(peak_co2, 2),
            "final_co2_ppm": last_snap.co2_ppm if last_snap else None,
            "final_power_margin_w": last_snap.power_margin_w if last_snap else None,
            "min_power_margin_w": round(min_power_margin_w, 2) if min_power_margin_w is not None else None,
            "eps_boost_applied_step": eps_boost_applied_step,
            "power_recovered_above_critical_step": power_recovered_above_critical_step,
            "final_health": last_health.to_dict() if last_health else None,
            "anomaly_seen": anomaly_seen,
            "co2_above_threshold_step": co2_above_threshold_step,
            "co2_recovered_below_threshold_step": co2_recovered_below_threshold_step,
            "message_count": message_count,
            "design_change_count": sum(
                1 for e in sim.get_events() if "design_change" in str(e.get("kind", "")).lower()
            ),
        }

        design_proposals_path = run_dir / "design_proposals.json"
        if isinstance(team, ScrubberDegradationTeam):
            summary["team_count"] = team.team_cfg.count
            summary["agent_ids"] = list(team.team_cfg.agent_ids)
            summary["archetypes"] = {aid: lens for aid, lens in team.team_cfg.archetypes}
            design_proposal = team.propose_post_run_design(sim, summary)
            design_proposals_path.write_text(
                json.dumps(design_proposal, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            summary["design_proposal_count"] = len(design_proposal.get("changes", []))
            summary["design_proposals_path"] = str(design_proposals_path)

        log.write_summary(summary)

        provenance_path = run_dir / "provenance.jsonl"
        provenance_count = 0
        try:
            provenance_path = export_run_provenance(run_dir)
            with provenance_path.open(encoding="utf-8") as f:
                provenance_count = sum(1 for line in f if line.strip())
        except Exception as exc:
            logger.warning("One Piece provenance export failed: %s", exc)
        summary["provenance_path"] = str(provenance_path)
        summary["provenance_record_count"] = provenance_count
        log.write_summary(summary)
        return run_dir


SCENARIO_REGISTRY: Dict[str, Scenario] = {
    "scrubber_degradation": ScrubberDegradationScenario(),
}
