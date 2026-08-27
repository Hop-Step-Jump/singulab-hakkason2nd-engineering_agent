"""design_proposals.json — post-run scrubber topology/params for the next run."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from environment.scrubber.eclss_ops.design_state import DesignStateManager
from environment.scrubber.mock_eclss import MockEclssSimulator
from environment.scrubber.station_simulator import StationSimulator

SCRUBBER_CHANGE_KINDS = frozenset({"add_edge", "add_node", "set_parameter"})


def load_design_proposals(path: Path) -> Dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"design_proposals must be an object: {path}")
    validate_design_proposals(data)
    return data


def validate_design_proposals(data: Dict[str, Any]) -> None:
    if data.get("design_domain") not in (None, "scrubber"):
        raise ValueError(
            f"scrubber apply expects design_domain scrubber or omitted, "
            f"got {data.get('design_domain')!r}"
        )
    changes = data.get("changes")
    if changes is None:
        return
    if not isinstance(changes, list):
        raise ValueError("design_proposals.changes must be a list")
    for item in changes:
        if not isinstance(item, dict):
            raise ValueError("each change must be an object")
        kind = str(item.get("change_kind", "")).strip()
        if kind not in SCRUBBER_CHANGE_KINDS:
            raise ValueError(f"unsupported scrubber change_kind: {kind}")
        payload = item.get("payload", {})
        if not isinstance(payload, dict):
            raise ValueError(f"payload for {kind} must be an object")
        if validate_scrubber_proposal_change(kind, payload) is None:
            raise ValueError(f"invalid payload for {kind}: {payload}")


def validate_scrubber_proposal_change(
    change_kind: str, payload: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    if change_kind == "add_node":
        node_id = str(payload.get("id", "")).strip()
        if not node_id:
            return None
        return payload
    if change_kind == "add_edge":
        if not payload.get("node_a") or not payload.get("node_b"):
            return None
        return payload
    if change_kind == "set_parameter":
        key = str(payload.get("key", "")).strip()
        if not key:
            return None
        try:
            float(payload.get("value"))
        except (TypeError, ValueError):
            return None
        return payload
    return None


def apply_design_proposals(
    config: Dict[str, Any],
    proposals: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Merge proposals into config; return (config, topology_changes for DesignStateManager).

    ``set_parameter`` updates ``design_parameters``. Topology kinds are returned
    for application after the simulator is built (``DesignStateManager``).
    """
    updated = copy.deepcopy(config)
    design_params = dict(updated.get("design_parameters") or {})
    topology_changes: List[Dict[str, Any]] = []
    for item in proposals.get("changes") or []:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("change_kind", "")).strip()
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        if kind == "set_parameter":
            key = str(payload.get("key", "")).strip()
            if key:
                design_params[key] = float(payload["value"])
        elif kind in {"add_edge", "add_node"}:
            topology_changes.append({"change_kind": kind, "payload": payload})
    if design_params:
        updated["design_parameters"] = design_params
    return updated, topology_changes


def apply_topology_changes_to_simulator(
    sim: StationSimulator | MockEclssSimulator,
    topology_changes: List[Dict[str, Any]],
) -> None:
    """Seed permanent topology from prior ``design_proposals`` before step 0."""
    if not topology_changes:
        return
    eclss = sim.eclss if isinstance(sim, StationSimulator) else sim
    design: DesignStateManager = eclss.design
    for item in topology_changes:
        design.apply_dict_change(item["change_kind"], item["payload"])


def write_design_proposals(path: Path, proposals: Dict[str, Any]) -> None:
    validate_design_proposals(proposals)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(proposals, ensure_ascii=False, indent=2), encoding="utf-8")
