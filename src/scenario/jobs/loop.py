"""Multi-run design→verification loop orchestrator."""

from __future__ import annotations

import json
import time
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from scenario.jobs.design_history import crew_target_met, digest_run_for_history
from scenario.jobs.executor import execute_run
from scenario.jobs.resolve import default_results_root
from scenario.jobs.spec import RunResult, RunSpec

DEFAULT_LOOP_ID = "e002loop"
DEFAULT_MAX_LOOPS = 15
DEFAULT_TARGET_CREW = 50
DEFAULT_MAX_ACTIONS_PER_STEP = 2


@dataclass
class LoopSpec:
    """Configuration for an N-run design→verification loop."""

    scenario: str = "ssos_eclss_loop"
    overrides: Optional[Dict[str, Any]] = None
    results_root: Optional[Path] = None
    loop_id: str = DEFAULT_LOOP_ID
    max_loops: int = DEFAULT_MAX_LOOPS
    target_crew: int = DEFAULT_TARGET_CREW
    max_actions_per_step: int = DEFAULT_MAX_ACTIONS_PER_STEP
    seed: Optional[int] = None
    recreate_output: bool = True

    def run_id_for(self, index: int) -> str:
        """1-based index → ``e002loop-run01`` style id."""
        if index < 1:
            raise ValueError(f"loop index must be >= 1, got {index}")
        return f"{self.loop_id}-run{index:02d}"


@dataclass
class LoopResult:
    """Outcome of a multi-run loop."""

    loop_id: str
    scenario: str
    runs: List[RunResult] = field(default_factory=list)
    history: List[Dict[str, Any]] = field(default_factory=list)
    stopped_reason: str = "max_loops"
    target_met: bool = False
    duration_s: float = 0.0
    manifest_path: Optional[Path] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "loop_id": self.loop_id,
            "scenario": self.scenario,
            "stopped_reason": self.stopped_reason,
            "target_met": self.target_met,
            "duration_s": round(self.duration_s, 3),
            "run_count": len(self.runs),
            "runs": [
                {
                    "run_id": (r.summary or {}).get("run_id")
                    or (self.history[i].get("run_id") if i < len(self.history) else None),
                    "run_dir": str(r.run_dir),
                    "exit_code": r.exit_code,
                    "error": r.error,
                    "crew_remaining": (r.summary or {}).get("crew_remaining"),
                    "crew_initial": (r.summary or {}).get("crew_initial"),
                    "design_proposal_count": (r.summary or {}).get("design_proposal_count"),
                }
                for i, r in enumerate(self.runs)
            ],
            "history": self.history,
            "manifest_path": str(self.manifest_path) if self.manifest_path else None,
        }


def _ensure_max_actions(overrides: Optional[Dict[str, Any]], value: int) -> Dict[str, Any]:
    merged = deepcopy(overrides) if overrides else {}
    agents = dict(merged.get("agents") or {})
    actor = dict(agents.get("actor") or {})
    # Only set when absent so explicit CLI --set still wins if already present.
    actor.setdefault("max_actions_per_step", value)
    agents["actor"] = actor
    merged["agents"] = agents
    return merged


def _default_ssos_loop_overrides(overrides: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Prefer plant_sim for crew-target loops when backend is unset."""
    merged = deepcopy(overrides) if overrides else {}
    backend = merged.get("backend")
    if not isinstance(backend, dict):
        backend = {}
    if "kind" not in backend:
        backend["kind"] = "plant_sim"
        merged["backend"] = backend
    return merged


def execute_loop(spec: LoopSpec) -> LoopResult:
    """Run design→verify iterations until crew target or ``max_loops``."""
    start = time.monotonic()
    results_root = Path(spec.results_root) if spec.results_root else default_results_root()
    results_root.mkdir(parents=True, exist_ok=True)

    overrides = _ensure_max_actions(spec.overrides, spec.max_actions_per_step)
    if spec.scenario == "ssos_eclss_loop":
        overrides = _default_ssos_loop_overrides(overrides)

    history: List[Dict[str, Any]] = []
    runs: List[RunResult] = []
    proposal_paths: List[Path] = []
    stopped_reason = "max_loops"
    target_met = False

    for index in range(1, int(spec.max_loops) + 1):
        run_id = spec.run_id_for(index)
        run_spec = RunSpec(
            scenario=spec.scenario,
            overrides=overrides,
            run_id=run_id,
            results_root=results_root,
            recreate_output=spec.recreate_output,
            seed=spec.seed,
            apply_proposals_paths=list(proposal_paths) if proposal_paths else None,
            design_history=list(history),
        )
        result = execute_run(run_spec)
        runs.append(result)
        if result.exit_code != 0:
            stopped_reason = "error"
            break

        digest = digest_run_for_history(
            run_id=run_id,
            run_dir=result.run_dir,
            summary=result.summary or {},
            loop_index=index,
        )
        history.append(digest)

        proposals_file = result.run_dir / "design_proposals.json"
        if proposals_file.is_file():
            proposal_paths.append(proposals_file)

        summary = result.summary or {}
        # Persist loop metadata onto this run's summary.
        summary["loop_id"] = spec.loop_id
        summary["loop_index"] = index
        summary["loop_max"] = spec.max_loops
        summary["loop_target_crew"] = spec.target_crew
        summary["run_id"] = run_id
        (result.run_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        result.summary = summary

        if crew_target_met(summary, target_crew=spec.target_crew):
            target_met = True
            stopped_reason = "target_crew"
            break

        # Scrubber has no crew; stop early when a run emits no further proposals
        # after at least one proposal was applied (stable design).
        if (
            spec.scenario == "scrubber_degradation"
            and index > 1
            and not proposals_file.is_file()
        ):
            stopped_reason = "no_new_proposals"
            break

    duration_s = time.monotonic() - start
    manifest_path = results_root / f"{spec.loop_id}-manifest.json"
    loop_result = LoopResult(
        loop_id=spec.loop_id,
        scenario=spec.scenario,
        runs=runs,
        history=history,
        stopped_reason=stopped_reason,
        target_met=target_met,
        duration_s=duration_s,
        manifest_path=manifest_path,
    )
    manifest_path.write_text(
        json.dumps(loop_result.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return loop_result
