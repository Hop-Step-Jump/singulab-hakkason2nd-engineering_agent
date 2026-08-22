"""Run output directory resolution shared across scenarios."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

from core.event_log import EventLog

_DEFAULT_RESULTS_ROOT = Path(__file__).resolve().parents[2] / "experiments" / "results"
RESULTS_ROOT_ENV_VAR = "EA_RESULTS_ROOT"
_RUN_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


def default_results_root() -> Path:
    env_value = os.environ.get(RESULTS_ROOT_ENV_VAR)
    if env_value:
        return Path(env_value)
    return _DEFAULT_RESULTS_ROOT


def sanitize_run_id(run_id: str) -> str:
    """Reject run ids that could escape the results directory."""
    if not run_id or run_id in {".", ".."}:
        raise ValueError(f"Invalid run id: {run_id!r}")
    if "/" in run_id or "\\" in run_id or ".." in run_id:
        raise ValueError(f"Invalid run id (path separators not allowed): {run_id!r}")
    if not _RUN_ID_PATTERN.match(run_id):
        raise ValueError(
            f"Invalid run id: {run_id!r}. Use letters, digits, '.', '_', or '-'."
        )
    return run_id


def resolve_run_id(
    scenario_name: str,
    output_cfg: Dict[str, Any],
    agents_config: Optional[Dict[str, Any]],
    run_id_override: Optional[str] = None,
) -> str:
    if run_id_override:
        return sanitize_run_id(run_id_override)

    run_id = output_cfg.get("run_id", scenario_name)
    if not agents_config:
        return str(run_id)

    mode = _run_id_mode_key(agents_config)
    if mode == "labeled_rule_base":
        return str(
            output_cfg.get("run_id_labeled_rule_base", f"{scenario_name}_labeled_rule_base")
        )
    if mode == "llm":
        return str(output_cfg.get("run_id_llm", f"{scenario_name}_llm"))
    if mode and mode not in {"none"}:
        return f"{scenario_name}_{mode}"
    return str(run_id)


def _run_id_mode_key(agents_config: Dict[str, Any]) -> Optional[str]:
    if isinstance(agents_config.get("actor"), dict) or isinstance(
        agents_config.get("design"), dict
    ):
        from scenario.ssos_eclss_loop.agent_config import (
            normalize_ssos_agents_section,
            ssos_run_id_mode_key,
        )

        return ssos_run_id_mode_key(normalize_ssos_agents_section(agents_config))
    mode = agents_config.get("mode")
    return str(mode) if mode is not None else None


def resolve_run_directory(
    *,
    scenario_name: str,
    output_cfg: Dict[str, Any],
    agents_config: Optional[Dict[str, Any]],
    output_dir: Optional[Path] = None,
    run_id: Optional[str] = None,
    results_root: Optional[Path] = None,
    recreate_output: bool = True,
) -> Path:
    """Resolve (and optionally create) the run output directory."""
    if output_dir is None:
        base = results_root or default_results_root()
        resolved_run_id = resolve_run_id(scenario_name, output_cfg, agents_config, run_id)
        resolved_run_id = sanitize_run_id(resolved_run_id)
        if recreate_output:
            return EventLog.prepare_run_dir(base, run_id=resolved_run_id)
        run_dir = base / resolved_run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    run_dir = Path(output_dir)
    if recreate_output and run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir
