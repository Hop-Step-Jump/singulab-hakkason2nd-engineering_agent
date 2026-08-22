"""Pure extractors for ssos_eclss_loop dashboard (run artifacts only)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

SSOS_OPERATIONAL_KINDS = frozenset(
    {
        "air_revitalisation",
        "oxygen_generation",
        "water_recovery",
        "request_co2",
        "request_o2",
    }
)


def plant_sim_topic(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    raw = row.get("raw_topics")
    if not isinstance(raw, dict):
        return None
    topic = raw.get("plant_sim")
    return topic if isinstance(topic, dict) else None

METABOLISM_KEYS = frozenset(
    {
        "co2_generated_kg",
        "o2_demand_kg",
        "o2_consumed_kg",
        "water_demand_kg",
        "water_consumed_kg",
        "hydration_fraction",
        "urine_generated_l",
        "condensate_generated_l",
    }
)

SCHEMATIC_NODES = (
    "crew",
    "cabin",
    "ars",
    "ogs",
    "wrs",
    "co2_tank",
    "buffers",
)


def thresholds_from_summary(summary: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return effective thresholds from summary.json only (no repo YAML)."""
    thresholds = summary.get("thresholds")
    if not isinstance(thresholds, dict) or not thresholds:
        return None
    return dict(thresholds)


def health_inputs_from_summary(summary: Dict[str, Any]) -> Optional[Dict[str, str]]:
    health_inputs = summary.get("health_inputs")
    if not isinstance(health_inputs, dict) or not health_inputs:
        return None
    return {str(k): str(v) for k, v in health_inputs.items()}


def extract_ops_flows(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Operational mass flows from events.jsonl result.details only."""
    flows: List[Dict[str, Any]] = []
    for event in events:
        if event.get("kind") != "/eclss/events/operational_applied":
            continue
        cmd = event.get("command") or {}
        kind = cmd.get("kind")
        if kind not in SSOS_OPERATIONAL_KINDS:
            continue
        result = event.get("result") or {}
        details = result.get("details")
        flow_details: Dict[str, Any] = dict(details) if isinstance(details, dict) else {}
        if "response_value" in result and "response_value" not in flow_details:
            flow_details["response_value"] = result["response_value"]
        flows.append(
            {
                "step": event.get("step"),
                "kind": kind,
                "success": result.get("success"),
                "issued_by": cmd.get("issued_by"),
                "details": flow_details,
            }
        )
    return flows


def extract_metabolism_by_step(telemetry_rows: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    """Rows that contain raw_topics.plant_sim.last_metabolism (one per advance_step)."""
    by_step: Dict[int, Dict[str, Any]] = {}
    for row in telemetry_rows:
        if row.get("post_ops") is True:
            continue
        topic = plant_sim_topic(row)
        if topic is None:
            continue
        metab = topic.get("last_metabolism")
        if not isinstance(metab, dict):
            continue
        step = int(row["step"])
        by_step[step] = {k: metab[k] for k in METABOLISM_KEYS if k in metab}
    return by_step


def ops_flows_for_step(flows: List[Dict[str, Any]], step: int) -> List[Dict[str, Any]]:
    return [f for f in flows if int(f.get("step", -1)) == int(step)]


def _fmt_metric(label: str, value: Any, unit: str = "") -> Optional[str]:
    if not isinstance(value, (int, float)):
        return None
    suffix = f" {unit}" if unit else ""
    return f"{label}: {value:.4g}{suffix}"


def build_step_node_numbers(
    *,
    step: int,
    telemetry_row: Optional[Dict[str, Any]],
    ops_flows: List[Dict[str, Any]],
    metabolism: Optional[Dict[str, Any]],
) -> Dict[str, List[str]]:
    """Map run artifact fields onto fixed schematic nodes. Missing values stay empty."""
    nodes: Dict[str, List[str]] = {name: [] for name in SCHEMATIC_NODES}

    if metabolism:
        for key, label, unit in (
            ("co2_generated_kg", "CO2 generated", "kg"),
            ("o2_consumed_kg", "O2 consumed", "kg"),
            ("water_consumed_kg", "water consumed", "kg"),
            ("urine_generated_l", "urine", "L"),
            ("condensate_generated_l", "condensate", "L"),
        ):
            line = _fmt_metric(label, metabolism.get(key), unit)
            if line:
                nodes["crew"].append(line)

    if telemetry_row:
        topic = plant_sim_topic(telemetry_row)
        # plant_sim maps cabin CO2 → co2_storage_kg; mock/ros2 use /co2_storage tank.
        co2_line = _fmt_metric(
            "cabin CO2" if topic else "CO2 storage",
            telemetry_row.get("co2_storage_kg"),
            "kg",
        )
        if co2_line:
            nodes["cabin" if topic else "co2_tank"].append(co2_line)
        for key, label, unit in (
            ("o2_storage_kg", "available O2", "kg"),
            ("product_water_reserve_l", "product water", "L"),
        ):
            line = _fmt_metric(label, telemetry_row.get(key), unit)
            if line:
                nodes["cabin"].append(line)
        if topic:
            alive = topic.get("crew_alive")
            if isinstance(alive, (int, float)):
                nodes["crew"].insert(0, f"alive {int(alive)}")
            for key, label, unit in (
                ("captured_co2_kg", "captured CO2", "kg"),
            ):
                line = _fmt_metric(label, topic.get(key), unit)
                if line:
                    nodes["co2_tank"].append(line)
            for key, label, unit in (
                ("urine_buffer_l", "urine buffer", "L"),
            ):
                line = _fmt_metric(label, topic.get(key), unit)
                if line:
                    nodes["buffers"].append(line)
            grey = telemetry_row.get("grey_water_collected_l")
            line = _fmt_metric("grey water", grey, "L")
            if line:
                nodes["buffers"].append(line)

    step_flows = ops_flows_for_step(ops_flows, step)
    for flow in step_flows:
        details = flow.get("details") or {}
        kind = flow.get("kind")
        if kind == "air_revitalisation":
            for key, label, unit in (
                ("co2_removed_kg", "CO2 removed", "kg"),
                ("captured_co2_kg", "captured", "kg"),
                ("vented_co2_kg", "vented", "kg"),
            ):
                line = _fmt_metric(label, details.get(key), unit)
                if line:
                    nodes["ars"].append(line)
        elif kind == "oxygen_generation":
            for key, label, unit in (
                ("processed_water_kg", "water in", "kg"),
                ("o2_generated_kg", "O2 out", "kg"),
                ("sabatier_co2_used_kg", "CO2 to Sabatier", "kg"),
                ("h2_vented_kg", "H2 vented", "kg"),
            ):
                line = _fmt_metric(label, details.get(key), unit)
                if line:
                    nodes["ogs"].append(line)
        elif kind == "water_recovery":
            for key, label, unit in (
                ("recovered_water_l", "water out", "L"),
                ("urine_feed_l", "urine in", "L"),
                ("grey_feed_l", "grey in", "L"),
                ("brine_loss_l", "brine loss", "L"),
            ):
                line = _fmt_metric(label, details.get(key), unit)
                if line:
                    nodes["wrs"].append(line)
        elif kind == "request_co2":
            line = _fmt_metric("CO2 delivered", details.get("response_value"), "kg")
            if line:
                nodes["co2_tank"].append(line)
        elif kind == "request_o2":
            line = _fmt_metric("O2 delivered", details.get("response_value"), "kg")
            if line:
                nodes["cabin"].append(line)

    return nodes


def list_design_changes(proposals: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Pass through why/what/how when present; never invent missing fields."""
    changes = proposals.get("changes")
    if not isinstance(changes, list):
        return []
    listed: List[Dict[str, Any]] = []
    for change in changes:
        if not isinstance(change, dict):
            continue
        entry: Dict[str, Any] = {
            "change_kind": change.get("change_kind"),
            "payload": change.get("payload"),
        }
        for field in ("why", "what", "how", "proposed_by", "decision_source"):
            if field in change:
                entry[field] = change[field]
        listed.append(entry)
    return listed


def flatten_flow_table(
    *,
    step: int,
    metabolism: Optional[Dict[str, Any]],
    ops_flows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Rows for per-step flow detail table."""
    rows: List[Dict[str, Any]] = []
    if metabolism:
        for key in sorted(METABOLISM_KEYS):
            if key not in metabolism:
                continue
            rows.append(
                {
                    "step": step,
                    "source": "crew_metabolism",
                    "kind": key,
                    "value": metabolism[key],
                }
            )
    for flow in ops_flows_for_step(ops_flows, step):
        details = flow.get("details") or {}
        for key, value in sorted(details.items()):
            rows.append(
                {
                    "step": step,
                    "source": flow.get("kind"),
                    "kind": key,
                    "value": value,
                    "success": flow.get("success"),
                }
            )
    return rows
