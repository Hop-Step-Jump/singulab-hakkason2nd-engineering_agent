"""Scenario runner — loads YAML and drives Mock ECLSS with EventLog output."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from core.event_log import EventLog
from environment.scrubber.eclss_ops.design_state import DesignStateManager
from environment.protocol import AnomalySpec, SimulatorProtocol
from environment.scrubber.mock_eclss import MockEclssSimulator
from environment.scrubber.station_simulator import StationSimulator
from environment.scrubber.eps.backend import EpsBackend
from environment.scrubber.eps.mock.backend import build_mock_eps_backend
from environment.ssos.eps.ros2.bridge import Ros2EpsBridge
from scenario.agents.scrubber_degradation_team import ScrubberDegradationTeam
from scenario.agents.ssos_eclss_loop_team import SsosEclssLoopTeam
from scenario.jobs.executor import execute_run
from scenario.jobs.spec import RunSpec

SCENARIO_ROOT = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)


def list_scenarios() -> List[str]:
    names = []
    for path in SCENARIO_ROOT.iterdir():
        if path.is_dir() and (path / "scenario.yaml").exists():
            names.append(path.name)
    return sorted(names)


def scenario_config_path(name: str) -> Path:
    path = SCENARIO_ROOT / name / "scenario.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Scenario not found: {name} ({path})")
    return path


def agents_config_path(name: str) -> Path:
    return SCENARIO_ROOT / name / "agents.yaml"


def load_scenario_config(name: str, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    with scenario_config_path(name).open(encoding="utf-8") as f:
        config = yaml.safe_load(f)
    if overrides:
        config = _deep_merge(config, overrides)
    return config


def load_agents_config(name: str, scenario_config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    agents_section = scenario_config.get("agents") or {}
    agents_path = agents_config_path(name)
    if agents_path.exists():
        with agents_path.open(encoding="utf-8") as f:
            agents_yaml = yaml.safe_load(f) or {}
    else:
        agents_yaml = {}

    if name == "ssos_eclss_loop":
        from scenario.ssos_eclss_loop.agent_config import (
            normalize_ssos_agents_section,
            resolve_ssos_modes,
            ssos_agents_enabled,
        )

        normalized = normalize_ssos_agents_section(agents_section)
        merged = _deep_merge(agents_yaml, normalized)
        actor_mode, design_mode = resolve_ssos_modes(merged)
        merged.setdefault("actor", {})["mode"] = actor_mode
        merged.setdefault("design", {})["mode"] = design_mode
        # Legacy alias: apply_design_proposals still accepts agents.policy.*
        # and dual-writes agents.actor.policy.*. Keep lifting so older
        # design_proposals.json files remain effective without this merge.
        applied_policy = agents_section.get("policy")
        if applied_policy:
            actor = merged.setdefault("actor", {})
            actor["policy"] = _deep_merge(actor.get("policy") or {}, applied_policy)
        if not ssos_agents_enabled(merged):
            return None
        return merged

    mode = agents_section.get("mode", "none")
    if mode == "none":
        return None

    merged = _deep_merge(agents_yaml, {k: v for k, v in agents_section.items() if k != "config_file"})
    merged["mode"] = mode
    return merged


def write_effective_configs(
    run_dir: Path,
    *,
    scenario_config: Dict[str, Any],
    agents_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """Persist the YAML configs actually used for a run (after overrides / apply).

    Writes ``scenario_config.yaml`` always, and ``agents_config.yaml`` when agents
    are enabled. Returns a map of logical name → absolute path string for
    ``summary.json``.
    """
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    scenario_path = run_dir / "scenario_config.yaml"
    scenario_path.write_text(
        yaml.safe_dump(scenario_config, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    paths: Dict[str, str] = {"scenario_config_path": str(scenario_path)}

    if agents_config is not None:
        agents_path = run_dir / "agents_config.yaml"
        agents_path.write_text(
            yaml.safe_dump(agents_config, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        paths["agents_config_path"] = str(agents_path)

    return paths


def _deep_merge(base: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(base)
    for key, value in overrides.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def build_eclss(config: Dict[str, Any]) -> MockEclssSimulator:
    sim_cfg = config.get("simulation", {})
    design_params = config.get("design_parameters")
    design = DesignStateManager(parameters=design_params) if design_params else DesignStateManager()

    eclss = MockEclssSimulator(
        initial_co2_ppm=float(sim_cfg.get("initial_co2_ppm", 800.0)),
        initial_power_margin_w=float(sim_cfg.get("initial_power_margin_w", 150.0)),
        design=design,
    )

    for anomaly in config.get("anomalies", []):
        eclss.inject_anomaly(
            AnomalySpec(
                name=anomaly["name"],
                start_step=int(anomaly["start_step"]),
                scrubber_efficiency_decay_per_step=float(
                    anomaly.get("scrubber_efficiency_decay_per_step", 0.01)
                ),
                power_margin_decay_per_step=float(anomaly.get("power_margin_decay_per_step", 5.0)),
                co2_production_multiplier=float(anomaly.get("co2_production_multiplier", 1.0)),
            )
        )
    return eclss


def build_eps_backend(config: Dict[str, Any]) -> EpsBackend:
    eps_cfg = config.get("eps", {}) or {}
    backend = str(eps_cfg.get("backend", "mock")).lower()
    if backend in {"ssos_eps", "ros2", "ssos"}:
        return Ros2EpsBridge()
    sarj_cfg = eps_cfg.get("sarj", {}) or {}
    eclipse_window = sarj_cfg.get("eclipse_window")
    return build_mock_eps_backend(
        beta_angle_deg=float(sarj_cfg.get("beta_angle_deg", 45.0)),
        eclipse_window=tuple(eclipse_window) if eclipse_window else None,
    )


def build_station_simulator(config: Dict[str, Any]) -> StationSimulator:
    return StationSimulator(eclss=build_eclss(config), eps=build_eps_backend(config))


def build_simulator(config: Dict[str, Any]) -> StationSimulator:
    """Build coupled ECLSS + EPS station (default entry point for scenarios)."""
    return build_station_simulator(config)


def build_agent_team(scenario_name: str, agents_config: Optional[Dict[str, Any]]):
    if not agents_config:
        return None
    if scenario_name == "ssos_eclss_loop":
        from scenario.ssos_eclss_loop.agent_config import flatten_actor_config

        actor = flatten_actor_config(agents_config)
        if actor.get("mode") not in {"labeled_rule_base", "llm"}:
            return None
        return SsosEclssLoopTeam(actor)
    mode = agents_config.get("mode")
    if mode not in {"labeled_rule_base", "llm"}:
        return None
    if scenario_name == "scrubber_degradation":
        return ScrubberDegradationTeam(agents_config)
    raise ValueError(f"No agent team for scenario: {scenario_name}")


def _log_sim_events(log: EventLog, sim: SimulatorProtocol, step: int, logged_event_ids: set) -> None:
    for idx, event in enumerate(sim.get_events()):
        if "step" not in event:
            key = ("static", idx, event.get("kind"), json.dumps(event, sort_keys=True, default=str))
            if key in logged_event_ids:
                continue
            logged_event_ids.add(key)
            log.append("events", {"step": 0, **event})
            continue

        event_step = event.get("step")
        if event_step != step:
            continue
        key = (event_step, idx, event.get("kind"), json.dumps(event, sort_keys=True, default=str))
        if key in logged_event_ids:
            continue
        logged_event_ids.add(key)
        log.append("events", {"step": event_step, **{k: v for k, v in event.items() if k != "step"}})


def _scenario_registry() -> Dict[str, Any]:
    from scenario.scrubber_degradation.scenario_run import SCENARIO_REGISTRY as scrubber
    from scenario.ssos_eclss_loop.scenario_run import SCENARIO_REGISTRY as ssos

    return {**scrubber, **ssos}


def scenario_descriptions() -> Dict[str, str]:
    descriptions: Dict[str, str] = {}
    for name in list_scenarios():
        path = scenario_config_path(name)
        with path.open(encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        description = config.get("description", "")
        if isinstance(description, str):
            descriptions[name] = " ".join(description.split())
        else:
            descriptions[name] = str(description)
    return descriptions


def run_scenario(
    name: str,
    output_dir: Optional[Path] = None,
    overrides: Optional[Dict[str, Any]] = None,
    recreate_output: bool = True,
    run_id: Optional[str] = None,
    results_root: Optional[Path] = None,
) -> Path:
    result = execute_run(
        RunSpec(
            scenario=name,
            output_dir=output_dir,
            overrides=overrides,
            recreate_output=recreate_output,
            run_id=run_id,
            results_root=results_root,
        )
    )
    if result.exit_code != 0:
        raise ValueError(result.error or f"Scenario run failed: {name}")
    return result.run_dir
