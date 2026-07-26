"""design_proposals.json — post-run SSOS graph design for the next ssos_eclss_loop run.

Unified with scrubber_degradation naming (``design_proposals.json``). SSOS uses
``design_domain: ssos_graph`` and ROS-oriented ``change_kind`` values. Mock
topology kinds (``add_edge``, ``add_node``) belong to scrubber only.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Callable, Dict, List

DESIGN_DOMAIN = "ssos_graph"

SSOS_CHANGE_KINDS = frozenset(
    {
        "action_profile",
        "service_config",
        "set_parameter",
        "graph_rewire",
    }
)

ACTION_PROFILE_FIELDS_BY_SUBSYSTEM = {
    "ars": frozenset({"initial_co2_mass", "initial_moisture_content", "initial_contaminants"}),
    "ogs": frozenset({"input_water_mass", "iodine_concentration"}),
    "wrs": frozenset({"urine_volume"}),
}

ALLOWED_SET_PARAMETER_TARGETS = frozenset(
    {
        "agents.policy.co2_storage_high_kg",
        "agents.policy.o2_storage_low_kg",
        "agents.policy.product_water_low_l",
        "thresholds.co2_storage_high_kg",
        "thresholds.co2_storage_critical_kg",
        "thresholds.o2_storage_low_kg",
        "thresholds.product_water_low_l",
    }
)

ApplyHandler = Callable[[Dict[str, Any], Dict[str, Any]], None]


def load_design_proposals(path: Path) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("design_proposals.json must be a JSON object")
    return data


def validate_design_proposals(data: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    domain = data.get("design_domain")
    if domain is not None and domain != DESIGN_DOMAIN:
        errors.append(f"design_domain must be {DESIGN_DOMAIN!r}, got {domain!r}")

    changes = data.get("changes")
    if not isinstance(changes, list):
        return errors + ["changes must be a list"]

    for index, change in enumerate(changes):
        if not isinstance(change, dict):
            errors.append(f"changes[{index}] must be an object")
            continue
        kind = change.get("change_kind")
        if kind not in SSOS_CHANGE_KINDS:
            errors.append(
                f"changes[{index}].change_kind must be one of {sorted(SSOS_CHANGE_KINDS)}"
            )
        payload = change.get("payload")
        if payload is not None and not isinstance(payload, dict):
            errors.append(f"changes[{index}].payload must be an object")
    return errors


def _filter_action_profile_fields(subsystem: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    allowed = ACTION_PROFILE_FIELDS_BY_SUBSYSTEM.get(subsystem.lower())
    if allowed is None:
        raise ValueError(f"action_profile subsystem must be ars, ogs, or wrs, got {subsystem!r}")
    unknown = sorted(set(fields) - allowed)
    if unknown:
        raise ValueError(
            f"action_profile.fields contains unsupported keys for {subsystem}: {unknown}"
        )
    filtered = {key: fields[key] for key in fields if key in allowed}
    if not filtered:
        raise ValueError(f"action_profile.fields must include at least one known field for {subsystem!r}")
    return filtered


def _apply_action_profile(config: Dict[str, Any], payload: Dict[str, Any]) -> None:
    subsystem = str(payload.get("subsystem", "")).lower()
    fields = payload.get("fields") or {}
    if not isinstance(fields, dict):
        raise ValueError("action_profile.fields must be an object")
    filtered = _filter_action_profile_fields(subsystem, fields)
    policy = config.setdefault("agents", {}).setdefault("policy", {})
    if subsystem == "ars":
        policy.setdefault("ars_goal", {}).update(filtered)
    elif subsystem == "ogs":
        policy.setdefault("ogs_goal", {}).update(filtered)
    elif subsystem == "wrs":
        policy.setdefault("wrs_goal", {}).update(filtered)
    else:
        raise ValueError(f"action_profile subsystem must be ars, ogs, or wrs, got {subsystem!r}")


def _apply_service_config(config: Dict[str, Any], payload: Dict[str, Any]) -> None:
    service = str(payload.get("service", "")).lower()
    policy = config.setdefault("agents", {}).setdefault("policy", {})
    if service == "request_co2":
        if "amount" in payload:
            policy["request_co2_amount"] = float(payload["amount"])
        if "before_ogs" in payload:
            policy["request_co2_before_ogs"] = bool(payload["before_ogs"])
    elif service == "request_o2":
        if "amount" in payload:
            policy["request_o2_amount"] = float(payload["amount"])
    else:
        raise ValueError(f"unsupported service_config service: {service!r}")


def _apply_set_parameter(config: Dict[str, Any], payload: Dict[str, Any]) -> None:
    target = str(payload.get("target", ""))
    value = payload.get("value")
    if not target:
        raise ValueError("set_parameter.target is required")
    if target not in ALLOWED_SET_PARAMETER_TARGETS:
        allowed = ", ".join(sorted(ALLOWED_SET_PARAMETER_TARGETS))
        raise ValueError(
            f"set_parameter.target {target!r} is not allowed. Allowed targets: {allowed}"
        )

    parts = target.split(".")
    cursor: Any = config
    for part in parts[:-1]:
        if part not in cursor or not isinstance(cursor[part], dict):
            cursor[part] = {}
        cursor = cursor[part]
    cursor[parts[-1]] = value


def _apply_graph_rewire(config: Dict[str, Any], payload: Dict[str, Any]) -> None:
    """Merge launch remapping / gateway manifest for the next run."""
    graph = config.setdefault("ssos_graph", {})
    rewires = graph.setdefault("rewires", [])
    if not isinstance(rewires, list):
        raise ValueError("ssos_graph.rewires must be a list")
    rewires.append(copy.deepcopy(payload))


_APPLY_HANDLERS: Dict[str, ApplyHandler] = {
    "action_profile": _apply_action_profile,
    "service_config": _apply_service_config,
    "set_parameter": _apply_set_parameter,
    "graph_rewire": _apply_graph_rewire,
}


def apply_design_proposals(
    config: Dict[str, Any],
    proposals: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge proposal changes into scenario config for the *next* run."""
    errors = validate_design_proposals(proposals)
    if errors:
        raise ValueError("; ".join(errors))

    merged = copy.deepcopy(config)
    for change in proposals.get("changes", []):
        kind = change["change_kind"]
        payload = change.get("payload") or {}
        handler = _APPLY_HANDLERS.get(kind)
        if handler is None:
            raise ValueError(f"no apply handler for change_kind: {kind!r}")
        handler(merged, payload)
    return merged


def build_design_proposals_from_run(
    *,
    proposed_by: str,
    decision_source: str,
    policy: Dict[str, Any],
    message: str = "SSOS ECLSS design profiles observed during the run.",
    baseline_graph: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Capture labeled-rule policy used at runtime as next-run design proposals."""
    changes: List[Dict[str, Any]] = []

    ars_goal = policy.get("ars_goal") or {}
    if ars_goal:
        changes.append(
            {
                "change_kind": "action_profile",
                "payload": {
                    "subsystem": "ars",
                    "action": "air_revitalisation",
                    "fields": dict(ars_goal),
                },
            }
        )

    ogs_goal = policy.get("ogs_goal") or {}
    if ogs_goal:
        changes.append(
            {
                "change_kind": "action_profile",
                "payload": {
                    "subsystem": "ogs",
                    "action": "oxygen_generation",
                    "fields": dict(ogs_goal),
                },
            }
        )

    wrs_goal = policy.get("wrs_goal") or {}
    if wrs_goal:
        changes.append(
            {
                "change_kind": "action_profile",
                "payload": {
                    "subsystem": "wrs",
                    "action": "water_recovery_systems",
                    "fields": dict(wrs_goal),
                },
            }
        )

    if "request_co2_amount" in policy or "request_co2_before_ogs" in policy:
        # before_ogs true is opt-in; on LoopMock it can double-debit with OGS Sabatier.
        changes.append(
            {
                "change_kind": "service_config",
                "payload": {
                    "service": "request_co2",
                    "amount": float(policy.get("request_co2_amount", 0.025)),
                    "before_ogs": bool(policy.get("request_co2_before_ogs", False)),
                },
            }
        )

    for key in ("co2_storage_high_kg", "o2_storage_low_kg", "product_water_low_l"):
        if key in policy:
            value = float(policy[key])
            changes.append(
                {
                    "change_kind": "set_parameter",
                    "payload": {"target": f"agents.policy.{key}", "value": value},
                }
            )
            changes.append(
                {
                    "change_kind": "set_parameter",
                    "payload": {"target": f"thresholds.{key}", "value": value},
                }
            )

    doc: Dict[str, Any] = {
        "design_domain": DESIGN_DOMAIN,
        "proposed_by": proposed_by,
        "decision_source": decision_source,
        "message": message,
        "changes": changes,
        "parse_notes": [],
    }
    if baseline_graph is not None:
        doc["baseline_graph"] = baseline_graph
    return doc


def write_design_proposals(path: Path, proposals: Dict[str, Any]) -> None:
    errors = validate_design_proposals(proposals)
    if errors:
        raise ValueError("; ".join(errors))
    path.write_text(json.dumps(proposals, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
