"""Deterministic post-run evaluation for ``ssos_eclss_loop``.

The evaluator consumes persisted run artifacts rather than live model objects.
This keeps every score auditable and prevents an LLM from participating in
verification pass/fail.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from scenario.ssos_eclss_loop.evaluation_html import render_evaluation_html
from scenario.ssos_eclss_loop.health import build_effective_thresholds

SCHEMA_VERSION = "1.0"
CREW_LOST_EVENT = "/eclss/events/crew_lost"
OPERATIONAL_APPLIED = "/eclss/events/operational_applied"
OPERATIONAL_REJECTED = "/eclss/events/operational_rejected"
FAILURE_EVENT = "subsystem_failure_applied"

RESOURCE_KEYS = ("co2", "o2", "water")
TELEMETRY_FIELDS = {
    "co2": "co2_storage_kg",
    "o2": "o2_storage_kg",
    "water": "product_water_reserve_l",
}
COMMAND_RESOURCE = {
    "air_revitalisation": "co2",
    "oxygen_generation": "o2",
    "water_recovery": "water",
}
COMMAND_SUBSYSTEM = {
    "air_revitalisation": "ars",
    "oxygen_generation": "ogs",
    "water_recovery": "wrs",
}


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        value = json.loads(raw)
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _number(value: Any, default: float = 0.0) -> float:
    return float(value) if _finite_number(value) else default


def _clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _round(value: Optional[float], digits: int = 6) -> Optional[float]:
    return None if value is None else round(float(value), digits)


def _plant_topic(row: Mapping[str, Any]) -> Dict[str, Any]:
    raw = row.get("raw_topics")
    if not isinstance(raw, Mapping):
        return {}
    plant = raw.get("plant_sim")
    return dict(plant) if isinstance(plant, Mapping) else {}


def select_telemetry_rows(
    rows: Sequence[Mapping[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[int, Dict[str, Any]]]:
    """Return one canonical row per step and actor-operation pre rows.

    Canonical state prefers ``post_ops`` and otherwise the last row. The pre row
    is the first non-post row, used for event-at-step and actor-decision checks.
    """

    grouped: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for raw in rows:
        step = raw.get("step")
        if isinstance(step, bool) or not isinstance(step, int):
            continue
        grouped[step].append(dict(raw))

    canonical: List[Dict[str, Any]] = []
    pre_by_step: Dict[int, Dict[str, Any]] = {}
    for step in sorted(grouped):
        step_rows = grouped[step]
        pre = next((row for row in step_rows if row.get("post_ops") is not True), step_rows[0])
        post = next((row for row in reversed(step_rows) if row.get("post_ops") is True), None)
        pre_by_step[step] = pre
        canonical.append(post or step_rows[-1])
    return canonical, pre_by_step


def _time_s(row: Mapping[str, Any], step_seconds: float) -> float:
    value = _plant_topic(row).get("simulation_time_s")
    if _finite_number(value):
        return float(value)
    return float(row.get("step") or 0) * step_seconds


def _normalized_weights(raw: Mapping[str, Any], keys: Iterable[str]) -> Dict[str, float]:
    weights = {key: max(0.0, _number(raw.get(key), 0.0)) for key in keys}
    total = sum(weights.values())
    if total <= 0.0:
        keys_tuple = tuple(keys)
        return {key: 1.0 / len(keys_tuple) for key in keys_tuple}
    return {key: value / total for key, value in weights.items()}


def _severity(resource: str, value: float, thresholds: Mapping[str, float]) -> float:
    if resource == "co2":
        safe = thresholds["co2_storage_high_kg"]
        critical = thresholds["co2_storage_critical_kg"]
        return _clip((value - safe) / max(critical - safe, 1e-12))
    if resource == "o2":
        safe = thresholds["o2_storage_low_kg"]
        critical = thresholds["o2_storage_critical_kg"]
        return _clip((safe - value) / max(safe - critical, 1e-12))
    safe = thresholds["product_water_low_l"]
    critical = thresholds["product_water_critical_l"]
    return _clip((safe - value) / max(safe - critical, 1e-12))


def _status(resource: str, value: float, thresholds: Mapping[str, float]) -> str:
    severity = _severity(resource, value, thresholds)
    if severity >= 1.0:
        return "critical"
    if severity > 0.0:
        return "warning"
    return "safe"


def _physics_gate(
    canonical: Sequence[Mapping[str, Any]],
    events: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
    simulation: Mapping[str, Any],
    *,
    observations: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    gate_cfg = dict(config.get("physics_gate") or {})
    inventory_tolerance = float(gate_cfg.get("inventory_tolerance", 1e-9))
    ledger_tolerance = float(gate_cfg.get("ledger_tolerance", 2e-6))
    checks: List[Dict[str, Any]] = []

    required = tuple(TELEMETRY_FIELDS.values())
    invalid_samples: List[Dict[str, Any]] = []
    negative_samples: List[Dict[str, Any]] = []
    ledger_fields = (
        "captured_co2_kg",
        "urine_buffer_l",
        "crew_alive",
    )
    for row in observations if observations is not None else canonical:
        step = row.get("step")
        for field in required:
            value = row.get(field)
            if not _finite_number(value):
                invalid_samples.append({"step": step, "field": field, "value": value})
            elif float(value) < -inventory_tolerance:
                negative_samples.append({"step": step, "field": field, "value": value})
        plant = _plant_topic(row)
        for field in ledger_fields:
            value = plant.get(field)
            if not _finite_number(value):
                invalid_samples.append({"step": step, "field": f"plant_sim.{field}", "value": value})
            elif float(value) < -inventory_tolerance:
                negative_samples.append(
                    {"step": step, "field": f"plant_sim.{field}", "value": value}
                )
    checks.append(
        {
            "name": "required_finite_observations",
            "passed": not invalid_samples,
            "details": invalid_samples,
        }
    )
    checks.append(
        {"name": "non_negative_inventories", "passed": not negative_samples, "details": negative_samples}
    )

    final = _plant_topic(canonical[-1]) if canonical else {}
    residuals: Dict[str, Optional[float]] = {"o2_kg": None, "co2_kg": None, "water_l": None}
    if final:
        initial_o2 = _number(simulation.get("initial_o2_storage_kg"))
        initial_co2 = _number(simulation.get("initial_co2_storage_kg"))
        initial_water = _number(simulation.get("initial_product_water_l"))
        initial_captured = _number(final.get("initial_captured_co2_kg"))
        initial_urine = _number(final.get("initial_urine_buffer_l"))
        initial_grey = _number(final.get("initial_grey_water_l"))

        o2_in = initial_o2 + _number(final.get("total_o2_generated_kg"))
        o2_out = (
            _number(canonical[-1].get("o2_storage_kg"))
            + _number(final.get("total_o2_consumed_kg"))
            + _number(final.get("total_o2_delivered_kg"))
        )
        residuals["o2_kg"] = o2_in - o2_out

        co2_in = initial_co2 + initial_captured + _number(final.get("total_co2_generated_kg"))
        co2_out = (
            _number(canonical[-1].get("co2_storage_kg"))
            + _number(final.get("captured_co2_kg"))
            + _number(final.get("total_co2_vented_kg"))
            + _number(final.get("total_co2_delivered_kg"))
            + _number(final.get("total_sabatier_co2_used_kg"))
        )
        residuals["co2_kg"] = co2_in - co2_out

        water_in = (
            initial_water
            + initial_urine
            + initial_grey
            + _number(final.get("total_external_grey_water_submitted_l"))
            + _number(final.get("total_water_regenerated_l"))
        )
        water_out = (
            _number(canonical[-1].get("product_water_reserve_l"))
            + _number(final.get("urine_buffer_l"))
            + _number(canonical[-1].get("grey_water_collected_l"))
            + _number(final.get("total_unrecoverable_crew_water_l"))
            + _number(final.get("total_wrs_brine_loss_l"))
            + _number(final.get("total_electrolysis_water_kg"))
            + _number(final.get("total_product_water_delivered_l"))
        )
        residuals["water_l"] = water_in - water_out
    ledger_passed = bool(final) and all(
        residual is not None and abs(residual) <= ledger_tolerance
        for residual in residuals.values()
    )
    checks.append(
        {
            "name": "mass_balance_ledgers",
            "passed": ledger_passed,
            "tolerance": ledger_tolerance,
            "residuals": {key: _round(value, 12) for key, value in residuals.items()},
        }
    )

    action_violations: List[Dict[str, Any]] = []
    _, pre_by_step = select_telemetry_rows(
        observations if observations is not None else canonical
    )
    failure_gating_violations: List[Dict[str, Any]] = []
    for event in events:
        if event.get("kind") not in {OPERATIONAL_APPLIED, OPERATIONAL_REJECTED}:
            continue
        command = event.get("command") or {}
        kind = command.get("kind")
        subsystem = COMMAND_SUBSYSTEM.get(str(kind))
        step = int(event.get("step") or 0)
        if (
            event.get("kind") == OPERATIONAL_APPLIED
            and subsystem is not None
            and pre_by_step.get(step, {}).get(f"{subsystem}_failure_enabled") is True
        ):
            failure_gating_violations.append({"step": step, "kind": kind, "subsystem": subsystem})
        result = event.get("result") or {}
        details = result.get("details") if isinstance(result, Mapping) else {}
        details = details if isinstance(details, Mapping) else {}
        if kind == "air_revitalisation":
            removed = details.get("co2_removed_kg")
            maximum = details.get("max_removable_kg")
            if event.get("kind") == OPERATIONAL_APPLIED and (
                not _finite_number(removed)
                or not _finite_number(maximum)
                or float(removed) < -inventory_tolerance
                or float(removed) > float(maximum) + inventory_tolerance
            ):
                action_violations.append({"step": event.get("step"), "kind": kind})
        elif kind == "oxygen_generation":
            requested = details.get("requested_water_kg")
            processed = details.get("processed_water_kg")
            generated = details.get("o2_generated_kg")
            if event.get("kind") == OPERATIONAL_APPLIED and (
                not all(_finite_number(v) for v in (requested, processed, generated))
                or float(processed) < -inventory_tolerance
                or float(processed) > float(requested) + inventory_tolerance
                or float(generated) < -inventory_tolerance
            ):
                action_violations.append({"step": event.get("step"), "kind": kind})
        elif kind == "water_recovery":
            recovered = details.get("recovered_water_l")
            if event.get("kind") == OPERATIONAL_APPLIED and (
                not _finite_number(recovered) or float(recovered) < -inventory_tolerance
            ):
                action_violations.append({"step": event.get("step"), "kind": kind})
    checks.append(
        {"name": "operational_physical_bounds", "passed": not action_violations, "details": action_violations}
    )
    checks.append(
        {
            "name": "failed_subsystems_do_not_process",
            "passed": not failure_gating_violations,
            "details": failure_gating_violations,
        }
    )

    passed = bool(canonical) and all(bool(check.get("passed")) for check in checks)
    return {"passed": passed, "checks": checks}


def _crew_axis(summary: Mapping[str, Any]) -> Dict[str, Any]:
    initial = summary.get("crew_initial")
    remaining = summary.get("crew_remaining")
    if not _finite_number(initial) or float(initial) <= 0 or not _finite_number(remaining):
        return {"status": "incomplete", "score": None, "max_score": 50}
    ratio = _clip(float(remaining) / float(initial))
    causes = dict(summary.get("crew_lost_by_cause") or {})
    physics = {key: int(value or 0) for key, value in causes.items() if key.endswith("_physics")}
    dwell = {key: int(value or 0) for key, value in causes.items() if not key.endswith("_physics")}
    return {
        "status": "scored",
        "score": _round(50.0 * ratio),
        "max_score": 50,
        "metrics": {
            "crew_initial": int(initial),
            "crew_remaining": int(remaining),
            "crew_lost": int(summary.get("crew_lost") or int(initial) - int(remaining)),
            "survival_ratio": _round(ratio),
            "lost_by_cause": causes,
            "physical_floor_losses": physics,
            "band_dwell_losses": dwell,
        },
    }


def _tcl_axis(
    canonical: Sequence[Mapping[str, Any]],
    events: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
    step_seconds: float,
) -> Dict[str, Any]:
    tcl_cfg = dict(config.get("tcl") or {})
    reference = float(tcl_cfg.get("reference_seconds", 0.0))
    if reference <= 0.0 or not canonical:
        return {"status": "incomplete", "score": None, "max_score": 10}
    first_loss = next((event for event in events if event.get("kind") == CREW_LOST_EVENT), None)
    end_time = _time_s(canonical[-1], step_seconds)
    if first_loss is None:
        if end_time + 1e-9 >= reference:
            score: Optional[float] = 10.0
            status = "scored"
        else:
            score = None
            status = "right_censored"
        return {
            "status": status,
            "score": score,
            "max_score": 10,
            "metrics": {
                "event_observed": False,
                "tcl_seconds": None,
                "tcl_step": None,
                "survived_through_seconds": _round(end_time),
                "reference_seconds": reference,
            },
        }
    step = int(first_loss.get("step") or 0)
    row = next((item for item in canonical if item.get("step") == step), None)
    tcl = _time_s(row or {"step": step}, step_seconds)
    causes = dict(first_loss.get("crew_lost_by_cause") or {})
    return {
        "status": "scored",
        "score": _round(10.0 * _clip(tcl / reference)),
        "max_score": 10,
        "metrics": {
            "event_observed": True,
            "tcl_seconds": _round(tcl),
            "tcl_step": step,
            "tcl_causes": causes,
            "reference_seconds": reference,
        },
    }


def _trajectory_axis(
    canonical: Sequence[Mapping[str, Any]],
    thresholds: Mapping[str, float],
    config: Mapping[str, Any],
    step_seconds: float,
) -> Dict[str, Any]:
    trajectory_cfg = dict(config.get("trajectory") or {})
    weights = _normalized_weights(dict(trajectory_cfg.get("resource_weights") or {}), RESOURCE_KEYS)
    if len(canonical) < 2:
        return {"status": "incomplete", "score": None, "max_score": 10}
    auc = {key: 0.0 for key in RESOURCE_KEYS}
    band_steps = {key: {"safe": 0, "warning": 0, "critical": 0} for key in RESOURCE_KEYS}
    longest_critical = {key: 0 for key in RESOURCE_KEYS}
    current_critical = {key: 0 for key in RESOURCE_KEYS}

    for row in canonical:
        for resource, field in TELEMETRY_FIELDS.items():
            value = _number(row.get(field))
            status = _status(resource, value, thresholds)
            band_steps[resource][status] += 1
            current_critical[resource] = current_critical[resource] + 1 if status == "critical" else 0
            longest_critical[resource] = max(
                longest_critical[resource], current_critical[resource]
            )

    for left, right in zip(canonical, canonical[1:]):
        dt = _time_s(right, step_seconds) - _time_s(left, step_seconds)
        if dt <= 0.0:
            continue
        for resource, field in TELEMETRY_FIELDS.items():
            a = _severity(resource, _number(left.get(field)), thresholds)
            b = _severity(resource, _number(right.get(field)), thresholds)
            auc[resource] += (a + b) * 0.5 * dt

    duration = _time_s(canonical[-1], step_seconds) - _time_s(canonical[0], step_seconds)
    if duration <= 0.0:
        return {"status": "incomplete", "score": None, "max_score": 10}
    mean_severity = {key: auc[key] / duration for key in RESOURCE_KEYS}
    weighted = sum(weights[key] * mean_severity[key] for key in RESOURCE_KEYS)
    zero_score = max(1e-12, float(trajectory_cfg.get("zero_score_mean_severity", 1.0)))
    score = 10.0 * _clip(1.0 - weighted / zero_score)
    return {
        "status": "scored",
        "score": _round(score),
        "max_score": 10,
        "metrics": {
            "duration_seconds": _round(duration),
            "severity_auc_seconds": {key: _round(value) for key, value in auc.items()},
            "mean_normalized_severity": {
                key: _round(value) for key, value in mean_severity.items()
            },
            "band_steps": band_steps,
            "longest_critical_streak_steps": longest_critical,
            "resource_weights": weights,
        },
    }


def _resource_recovery_axis(
    canonical: Sequence[Mapping[str, Any]],
    pre_by_step: Mapping[int, Mapping[str, Any]],
    events: Sequence[Mapping[str, Any]],
    thresholds: Mapping[str, float],
    config: Mapping[str, Any],
) -> Dict[str, Any]:
    recovery_cfg = dict(config.get("resource_recovery") or {})
    weights = _normalized_weights(dict(recovery_cfg.get("resource_weights") or {}), RESOURCE_KEYS)
    terminal_weight = _clip(float(recovery_cfg.get("terminal_weight", 0.5)))
    if not canonical:
        return {"status": "incomplete", "score": None, "max_score": 10}
    first_step = min(pre_by_step) if pre_by_step else int(canonical[0].get("step") or 0)
    initial = pre_by_step.get(first_step, canonical[0])
    final = canonical[-1]
    failure = next(
        (
            event
            for event in events
            if event.get("kind") == FAILURE_EVENT and event.get("enabled") is True
        ),
        None,
    )
    event_step = int(failure["step"]) if failure is not None else None
    event_row = pre_by_step.get(event_step) if event_step is not None else None
    segment = [row for row in canonical if event_step is None or int(row.get("step", -1)) >= event_step]
    if not segment:
        segment = list(canonical)

    resource_metrics: Dict[str, Any] = {}
    qualities: Dict[str, float] = {}
    for resource, field in TELEMETRY_FIELDS.items():
        values = [_number(row.get(field)) for row in segment]
        initial_value = _number(initial.get(field))
        event_value = _number(event_row.get(field)) if event_row is not None else None
        final_value = _number(final.get(field))
        worst = max(values) if resource == "co2" else min(values)
        if resource == "co2":
            safe = thresholds["co2_storage_high_kg"]
            critical = thresholds["co2_storage_critical_kg"]
            band = max(critical - safe, 1e-12)
            margin = safe - final_value
            terminal_quality = _clip(margin / band)
            recovery_quality = (
                1.0 if worst <= safe else _clip((worst - final_value) / max(worst - safe, 1e-12))
            )
        elif resource == "o2":
            safe = thresholds["o2_storage_low_kg"]
            critical = thresholds["o2_storage_critical_kg"]
            band = max(safe - critical, 1e-12)
            margin = final_value - safe
            terminal_quality = _clip(margin / band)
            recovery_quality = (
                1.0 if worst >= safe else _clip((final_value - worst) / max(safe - worst, 1e-12))
            )
        else:
            safe = thresholds["product_water_low_l"]
            critical = thresholds["product_water_critical_l"]
            band = max(safe - critical, 1e-12)
            margin = final_value - safe
            terminal_quality = _clip(margin / band)
            recovery_quality = (
                1.0 if worst >= safe else _clip((final_value - worst) / max(safe - worst, 1e-12))
            )
        quality = terminal_weight * terminal_quality + (1.0 - terminal_weight) * recovery_quality
        qualities[resource] = quality
        resource_metrics[resource] = {
            "initial": _round(initial_value),
            "event": _round(event_value),
            "event_minus_initial": _round(event_value - initial_value)
            if event_value is not None
            else None,
            "worst_after_event": _round(worst),
            "final": _round(final_value),
            "terminal_safe_margin": _round(margin),
            "terminal_quality": _round(terminal_quality),
            "recovery_quality": _round(recovery_quality),
        }
    score = 10.0 * sum(weights[key] * qualities[key] for key in RESOURCE_KEYS)
    return {
        "status": "scored",
        "score": _round(score),
        "max_score": 10,
        "metrics": {
            "failure_event_step": event_step,
            "failure_subsystem": failure.get("subsystem") if failure else None,
            "terminal_weight": terminal_weight,
            "resource_weights": weights,
            "resources": resource_metrics,
        },
    }


def _command_within_bounds(
    kind: str, payload: Mapping[str, Any], decision_cfg: Mapping[str, Any]
) -> bool:
    bounds = dict(decision_cfg.get("command_bounds") or {})
    fields = dict(bounds.get(kind) or {})
    for field, limits in fields.items():
        if not isinstance(limits, Sequence) or isinstance(limits, (str, bytes)) or len(limits) != 2:
            return False
        value = payload.get(field)
        if not _finite_number(value):
            return False
        if not float(limits[0]) <= float(value) <= float(limits[1]):
            return False
    return True


def _decision_event_validity(
    event: Mapping[str, Any],
    pre: Mapping[str, Any],
    thresholds: Mapping[str, float],
    decision_cfg: Mapping[str, Any],
) -> Tuple[bool, List[str]]:
    command = event.get("command") or {}
    kind = str(command.get("kind") or "")
    payload = command.get("payload") or {}
    reasons: List[str] = []
    if not isinstance(payload, Mapping) or not _command_within_bounds(kind, payload, decision_cfg):
        reasons.append("payload_out_of_bounds")
    subsystem = COMMAND_SUBSYSTEM.get(kind)
    if subsystem and pre.get(f"{subsystem}_failure_enabled") is True:
        reasons.append("observed_subsystem_failure")
    resource = COMMAND_RESOURCE.get(kind)
    if resource is not None:
        value = _number(pre.get(TELEMETRY_FIELDS[resource]))
        if resource in {"co2", "o2"} and _status(resource, value, thresholds) == "safe":
            reasons.append("no_resource_hazard")
        if resource == "water":
            plant = _plant_topic(pre)
            feed = _number(plant.get("urine_buffer_l")) + _number(pre.get("grey_water_collected_l"))
            if feed <= 0.0:
                reasons.append("no_water_feed")
    elif kind == "request_co2":
        amount = _number(payload.get("amount"), -1.0)
        if amount <= 0.0 or _number(_plant_topic(pre).get("captured_co2_kg")) + 1e-12 < amount:
            reasons.append("insufficient_captured_co2")
    elif kind == "request_o2":
        amount = _number(payload.get("amount"), -1.0)
        if amount <= 0.0 or _number(pre.get("o2_storage_kg")) + 1e-12 < amount:
            reasons.append("insufficient_o2")
    else:
        reasons.append("unsupported_command")
    return not reasons, reasons


def _decision_axis(
    canonical: Sequence[Mapping[str, Any]],
    pre_by_step: Mapping[int, Mapping[str, Any]],
    events: Sequence[Mapping[str, Any]],
    thresholds: Mapping[str, float],
    config: Mapping[str, Any],
) -> Tuple[Dict[str, Any], Dict[int, bool]]:
    decision_cfg = dict(config.get("actor_decision") or {})
    max_latency = max(1, int(decision_cfg.get("max_latency_steps", 2)))
    latency_weight = _clip(float(decision_cfg.get("latency_weight", 0.5)))
    operation_events = [
        event
        for event in events
        if event.get("kind") in {OPERATIONAL_APPLIED, OPERATIONAL_REJECTED}
    ]
    validity_by_id: Dict[int, bool] = {}
    attempts: List[Dict[str, Any]] = []
    for event in operation_events:
        step = int(event.get("step") or 0)
        valid, reasons = _decision_event_validity(
            event, pre_by_step.get(step, {}), thresholds, decision_cfg
        )
        validity_by_id[id(event)] = valid
        attempts.append(
            {
                "step": step,
                "kind": (event.get("command") or {}).get("kind"),
                "valid": valid,
                "reasons": reasons,
            }
        )

    episodes: List[Dict[str, Any]] = []
    previous = {key: "safe" for key in RESOURCE_KEYS}
    decision_rows = [pre_by_step[step] for step in sorted(pre_by_step)]
    for row in decision_rows:
        step = int(row.get("step") or 0)
        for resource, field in TELEMETRY_FIELDS.items():
            status = _status(resource, _number(row.get(field)), thresholds)
            if status != "safe" and previous[resource] == "safe":
                command_kind = {
                    "co2": "air_revitalisation",
                    "o2": "oxygen_generation",
                    "water": "water_recovery",
                }[resource]
                response = next(
                    (
                        int(event.get("step") or 0)
                        for event in operation_events
                        if int(event.get("step") or 0) >= step
                        and (event.get("command") or {}).get("kind") == command_kind
                    ),
                    None,
                )
                latency = response - step if response is not None else None
                quality = (
                    _clip(1.0 - float(latency) / max_latency)
                    if latency is not None and latency <= max_latency
                    else 0.0
                )
                episodes.append(
                    {
                        "resource": resource,
                        "start_step": step,
                        "response_step": response,
                        "latency_steps": latency,
                        "quality": _round(quality),
                    }
                )
            previous[resource] = status

    latency_quality = (
        sum(float(item["quality"] or 0.0) for item in episodes) / len(episodes)
        if episodes
        else 1.0
    )
    validity_quality = (
        sum(1 for item in attempts if item["valid"]) / len(attempts) if attempts else 1.0
    )
    score = 10.0 * (
        latency_weight * latency_quality + (1.0 - latency_weight) * validity_quality
    )
    return (
        {
            "status": "scored",
            "score": _round(score),
            "max_score": 10,
            "metrics": {
                "latency_quality": _round(latency_quality),
                "validity_quality": _round(validity_quality),
                "episodes": episodes,
                "attempts": attempts,
            },
        },
        validity_by_id,
    )


def _response_quality(event: Mapping[str, Any], config: Mapping[str, Any]) -> Dict[str, Any]:
    response_cfg = dict(config.get("physical_response") or {})
    weights = _normalized_weights(
        {
            "success": response_cfg.get("success_weight", 1.0),
            "conversion": response_cfg.get("conversion_weight", 1.0),
            "sign": response_cfg.get("sign_weight", 1.0),
        },
        ("success", "conversion", "sign"),
    )
    command = event.get("command") or {}
    kind = str(command.get("kind") or "")
    payload = command.get("payload") or {}
    result = event.get("result") or {}
    details = result.get("details") if isinstance(result, Mapping) else {}
    details = details if isinstance(details, Mapping) else {}
    success = 1.0 if event.get("kind") == OPERATIONAL_APPLIED and result.get("success") else 0.0
    conversion = 0.0
    sign = 0.0
    if kind == "air_revitalisation":
        removed = _number(details.get("co2_removed_kg"), -1.0)
        maximum = _number(details.get("max_removable_kg"), 0.0)
        conversion = _clip(removed / maximum) if maximum > 0.0 else float(removed == 0.0)
        sign = float(removed >= 0.0)
    elif kind == "oxygen_generation":
        processed = _number(details.get("processed_water_kg"), -1.0)
        requested = _number(details.get("requested_water_kg"), 0.0)
        generated = _number(details.get("o2_generated_kg"), -1.0)
        conversion = _clip(processed / requested) if requested > 0.0 else float(processed == 0.0)
        sign = float(processed >= 0.0 and generated >= 0.0)
    elif kind == "water_recovery":
        requested = _number(payload.get("urine_volume"), 0.0)
        fed = _number(details.get("urine_feed_l"), -1.0)
        recovered = _number(details.get("recovered_water_l"), -1.0)
        conversion = _clip(fed / requested) if requested > 0.0 else float(fed == 0.0)
        sign = float(fed >= 0.0 and recovered >= 0.0)
    elif kind in {"request_co2", "request_o2"}:
        requested = _number(payload.get("amount"), 0.0)
        granted = _number(result.get("response_value"), -1.0)
        conversion = _clip(granted / requested) if requested > 0.0 else float(granted == 0.0)
        sign = float(granted >= 0.0)
    quality = weights["success"] * success + weights["conversion"] * conversion + weights["sign"] * sign
    return {
        "step": event.get("step"),
        "kind": kind,
        "success": success,
        "conversion": _round(conversion),
        "sign": sign,
        "quality": _round(quality),
    }


def _response_axis(
    events: Sequence[Mapping[str, Any]],
    validity_by_id: Mapping[int, bool],
    config: Mapping[str, Any],
) -> Dict[str, Any]:
    valid_events = [
        event
        for event in events
        if event.get("kind") in {OPERATIONAL_APPLIED, OPERATIONAL_REJECTED}
        and validity_by_id.get(id(event), False)
    ]
    if not valid_events:
        return {
            "status": "not_observed",
            "score": None,
            "max_score": 10,
            "metrics": {"valid_operation_count": 0, "operations": []},
        }
    operations = [_response_quality(event, config) for event in valid_events]
    score = 10.0 * sum(float(item["quality"] or 0.0) for item in operations) / len(operations)
    return {
        "status": "scored",
        "score": _round(score),
        "max_score": 10,
        "metrics": {"valid_operation_count": len(operations), "operations": operations},
    }


def evaluate_run(
    run_dir: Path,
    *,
    scenario_config: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> Dict[str, Any]:
    """Evaluate a completed run and write no files."""

    evaluation_cfg = dict(scenario_config.get("evaluation") or {})
    actor_mode = str(summary.get("actor_mode") or "none")
    max_score = 80 if actor_mode == "none" else 100
    backend = str(summary.get("backend") or "")
    survival_enabled = bool(
        ((scenario_config.get("plant_sim") or {}).get("survival") or {}).get("enabled", False)
    )
    base: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "scenario": summary.get("scenario"),
        "status": "not_applicable",
        "applicability": {
            "backend": backend,
            "survival_enabled": survival_enabled,
            "actor_mode": actor_mode,
            "applicable_max_score": max_score,
        },
        "requirements": {
            "thresholds": build_effective_thresholds(dict(scenario_config.get("thresholds") or {})),
            "evaluation": evaluation_cfg,
        },
        "physics_gate": {"passed": False, "checks": []},
        "scores": {"total": None, "max_score": max_score, "axes": {}},
        "evidence": {
            "telemetry": "telemetry.jsonl",
            "events": "events.jsonl",
            "canonical_row_rule": "post_ops row, otherwise final row per step",
            "event_row_rule": "actor-operation pre row at event step",
        },
    }
    if not bool(evaluation_cfg.get("enabled", True)):
        base["applicability"]["reason"] = "evaluation_disabled"
        return base
    if backend != "plant_sim":
        base["applicability"]["reason"] = "plant_sim_required"
        return base
    if not survival_enabled:
        base["applicability"]["reason"] = "survival_enabled_required"
        return base

    telemetry = _read_jsonl(Path(run_dir) / "telemetry.jsonl")
    events = _read_jsonl(Path(run_dir) / "events.jsonl")
    canonical, pre_by_step = select_telemetry_rows(telemetry)
    step_seconds = float(
        ((scenario_config.get("plant_sim") or {}).get("time") or {}).get("step_seconds", 1200)
    )
    thresholds = build_effective_thresholds(dict(scenario_config.get("thresholds") or {}))
    gate = _physics_gate(
        canonical,
        events,
        evaluation_cfg,
        dict(scenario_config.get("simulation") or {}),
        observations=telemetry,
    )
    base["physics_gate"] = gate
    if not gate["passed"]:
        base["status"] = "invalid"
        return base

    axes: Dict[str, Dict[str, Any]] = {
        "actor_survival": _crew_axis(summary),
        "tcl": _tcl_axis(canonical, events, evaluation_cfg, step_seconds),
        "environment_trajectory": _trajectory_axis(
            canonical, thresholds, evaluation_cfg, step_seconds
        ),
        "resource_recovery": _resource_recovery_axis(
            canonical, pre_by_step, events, thresholds, evaluation_cfg
        ),
    }
    if actor_mode != "none":
        decision, validity = _decision_axis(
            canonical, pre_by_step, events, thresholds, evaluation_cfg
        )
        axes["actor_decision"] = decision
        axes["physical_response"] = _response_axis(events, validity, evaluation_cfg)

    scores = [axis.get("score") for axis in axes.values()]
    complete = all(_finite_number(score) for score in scores)
    total = sum(float(score) for score in scores) if complete else None
    base["scores"] = {"total": _round(total), "max_score": max_score, "axes": axes}
    base["status"] = "scored" if complete else "incomplete"
    return base


def write_evaluation(
    run_dir: Path,
    *,
    scenario_config: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> Tuple[Path, Path, Dict[str, Any]]:
    """Evaluate and persist ``evaluation.json`` plus ``evaluation.html``."""

    run_path = Path(run_dir)
    json_path = run_path / "evaluation.json"
    html_path = run_path / "evaluation.html"
    payload = evaluate_run(run_dir, scenario_config=scenario_config, summary=summary)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(render_evaluation_html(payload), encoding="utf-8")
    return json_path, html_path, payload


__all__ = [
    "evaluate_run",
    "select_telemetry_rows",
    "write_evaluation",
]
