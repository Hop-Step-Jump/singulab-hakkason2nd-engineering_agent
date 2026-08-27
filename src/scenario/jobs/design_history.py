"""Shared digests of prior loop runs for post-run design review."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


_SUMMARY_KEYS = (
    "scenario",
    "backend",
    "steps",
    "crew_initial",
    "crew_remaining",
    "crew_lost",
    "crew_lost_by_cause",
    "peak_co2_storage_kg",
    "min_o2_storage_kg",
    "final_co2_storage_kg",
    "final_o2_storage_kg",
    "peak_co2_ppm",
    "final_co2_ppm",
    "min_power_margin_w",
    "final_power_margin_w",
    "anomaly_seen",
    "operational_command_count",
    "design_proposal_count",
    "evaluation_status",
    "evaluation_score",
    "apply_proposals_path",
)


def digest_run_for_history(
    *,
    run_id: str,
    run_dir: Path,
    summary: Dict[str, Any],
    loop_index: int,
) -> Dict[str, Any]:
    """Compact prior-run record for designer prompts and loop manifests."""
    slim_summary = {k: summary[k] for k in _SUMMARY_KEYS if k in summary}
    proposals_path = run_dir / "design_proposals.json"
    proposals_excerpt: Optional[Dict[str, Any]] = None
    if proposals_path.is_file():
        try:
            raw = json.loads(proposals_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = None
        if isinstance(raw, dict):
            changes = raw.get("changes") or []
            proposals_excerpt = {
                "proposed_by": raw.get("proposed_by"),
                "decision_source": raw.get("decision_source"),
                "message": raw.get("message"),
                "change_count": len(changes) if isinstance(changes, list) else 0,
                "changes": changes if isinstance(changes, list) else [],
            }
    return {
        "loop_index": loop_index,
        "run_id": run_id,
        "run_dir": str(run_dir),
        "summary": slim_summary,
        "proposals": proposals_excerpt,
    }


def format_prior_runs_for_prompt(prior_runs: List[Dict[str, Any]]) -> str:
    """Render prior loop digests for LLM / rule design situation text."""
    if not prior_runs:
        return "(none — this is the first loop iteration)"
    blocks: List[str] = []
    for entry in prior_runs:
        idx = entry.get("loop_index", "?")
        run_id = entry.get("run_id", "?")
        summary = entry.get("summary") or {}
        proposals = entry.get("proposals")
        lines = [
            f"#### Prior run {idx}: {run_id}",
            f"- summary: {json.dumps(summary, ensure_ascii=False, default=str)}",
        ]
        if proposals:
            lines.append(
                f"- proposals ({proposals.get('change_count', 0)}): "
                f"{json.dumps(proposals.get('changes') or [], ensure_ascii=False, default=str)}"
            )
            if proposals.get("message"):
                lines.append(f"- proposal message: {proposals.get('message')}")
        else:
            lines.append("- proposals: (none written)")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def crew_target_met(summary: Dict[str, Any], *, target_crew: int) -> bool:
    """True when surviving crew equals the target (initial keep)."""
    remaining = summary.get("crew_remaining")
    if remaining is None:
        return False
    try:
        return int(remaining) == int(target_crew)
    except (TypeError, ValueError):
        return False
