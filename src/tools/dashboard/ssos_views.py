"""Dashboard views for ssos_eclss_loop run outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import matplotlib.pyplot as plt
import streamlit as st

from tools.dashboard.jsonl_rows import select_row_for_step, series_by_step
from tools.dashboard.run_status import (
    build_anomaly_timeline_lanes,
    build_status_timeline_lanes,
    extract_anomaly_status,
    extract_design_drivers,
    extract_operator_step,
)
from tools.dashboard.ssos_flow import (
    SSOS_OPERATIONAL_KINDS,
    build_step_node_numbers,
    extract_metabolism_by_step,
    extract_ops_flows,
    flatten_flow_table,
    health_inputs_from_summary,
    list_design_changes,
    plant_sim_topic,
    thresholds_from_summary,
)


def scenario_name(summary: Dict[str, Any]) -> str:
    return str(summary.get("scenario", ""))


def is_ssos_eclss_loop(summary: Dict[str, Any]) -> bool:
    return scenario_name(summary) == "ssos_eclss_loop"


def has_plant_sim_topics(telemetry_rows: List[Dict[str, Any]]) -> bool:
    return any(plant_sim_topic(row) is not None for row in telemetry_rows)


def plant_sim_series(telemetry_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One row per step with selected plant_sim ledger fields (if present)."""
    rows: List[Dict[str, Any]] = []
    for row in series_by_step(telemetry_rows):
        topic = plant_sim_topic(row)
        if topic is None:
            continue
        rows.append(
            {
                "step": int(row["step"]),
                "captured_co2_kg": topic.get("captured_co2_kg"),
                "urine_buffer_l": topic.get("urine_buffer_l"),
                "grey_water_collected_l": row.get("grey_water_collected_l"),
                "total_o2_shortfall_kg": topic.get("total_o2_shortfall_kg"),
                "total_water_shortfall_l": topic.get("total_water_shortfall_l"),
                "total_co2_vented_kg": topic.get("total_co2_vented_kg"),
                "total_h2_vented_kg": topic.get("total_h2_vented_kg"),
                "total_ch4_vented_kg": topic.get("total_ch4_vented_kg"),
                "total_wrs_brine_loss_l": topic.get("total_wrs_brine_loss_l"),
                "crew_alive": topic.get("crew_alive"),
                "crew_initial": topic.get("crew_initial"),
                "crew_lost_total": topic.get("crew_lost_total"),
            }
        )
    return rows


def filter_ssos_operational_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        e
        for e in events
        if (e.get("command") or {}).get("kind") in SSOS_OPERATIONAL_KINDS
    ]


def render_ssos_status_strip(
    summary: Dict[str, Any],
    health_rows: List[Dict[str, Any]],
    telemetry_rows: List[Dict[str, Any]],
    current_step: int,
) -> None:
    """Status from health_metrics, failure flags, and shortfall ledgers."""
    st.subheader("Status")
    current_health = select_row_for_step(health_rows, current_step) or {}
    current_telemetry = select_row_for_step(telemetry_rows, current_step) or {}
    topic = plant_sim_topic(current_telemetry) if current_telemetry else None

    health_inputs = health_inputs_from_summary(summary)
    if health_inputs:
        inputs_text = ", ".join(f"{k}={v}" for k, v in health_inputs.items())
        st.caption(f"Health reads: {inputs_text}")
    else:
        st.caption(
            "Health reads telemetry.co2_storage_kg, o2_storage_kg, product_water_reserve_l "
            "(threshold numbers not recorded in this run)."
        )
    st.caption(
        "Bands use the post-ops health row when a step has pre/post_ops duplicates "
        "(final state after commands). Anomaly / stress below uses the worst band for the step."
    )

    cols = st.columns(7)
    with cols[0]:
        st.metric("Overall", current_health.get("overall", "—"))
    with cols[1]:
        st.metric("CO2 band", current_health.get("co2_status", "—"))
    with cols[2]:
        st.metric("O2 band", current_health.get("o2_status", "—"))
    with cols[3]:
        st.metric("Water band", current_health.get("water_status", "—"))
    with cols[4]:
        failures = []
        if current_telemetry.get("ars_failure_enabled"):
            failures.append("ARS")
        if current_telemetry.get("ogs_failure_enabled"):
            failures.append("OGS")
        if current_telemetry.get("wrs_failure_enabled"):
            failures.append("WRS")
        st.metric("Subsystem failures", ", ".join(failures) if failures else "none")
    with cols[5]:
        alive = topic.get("crew_alive") if topic else None
        initial = topic.get("crew_initial") if topic else None
        if isinstance(alive, int) or (isinstance(alive, float) and alive == int(alive)):
            label = f"{int(alive)}"
            if isinstance(initial, (int, float)):
                label = f"{int(alive)} / {int(initial)}"
            st.metric("Crew alive", label)
        else:
            remaining = summary.get("crew_remaining")
            st.metric("Crew alive", remaining if remaining is not None else "—")
    with cols[6]:
        o2_short = topic.get("total_o2_shortfall_kg") if topic else None
        water_short = topic.get("total_water_shortfall_l") if topic else None
        if isinstance(o2_short, (int, float)) or isinstance(water_short, (int, float)):
            parts = []
            if isinstance(o2_short, (int, float)):
                parts.append(f"O2 {o2_short:.3g} kg")
            if isinstance(water_short, (int, float)):
                parts.append(f"H2O {water_short:.3g} L")
            st.metric("Crew shortfalls", " / ".join(parts))
        else:
            st.metric("Crew shortfalls", "—")


def render_ssos_health_card(
    telemetry_rows: List[Dict[str, Any]],
    health_rows: List[Dict[str, Any]],
    current_step: int,
) -> None:
    current_telemetry = select_row_for_step(telemetry_rows, current_step)
    current_health = select_row_for_step(health_rows, current_step)
    cabin_co2 = has_plant_sim_topics(telemetry_rows)

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        st.metric("Step", current_step)
    with col2:
        co2 = (current_telemetry or {}).get("co2_storage_kg")
        st.metric(
            "Cabin CO2 (kg)" if cabin_co2 else "CO2 storage (kg)",
            f"{co2:.1f}" if isinstance(co2, (int, float)) else "—",
        )
    with col3:
        o2 = (current_telemetry or {}).get("o2_storage_kg")
        st.metric("O2 storage (kg)", f"{o2:.1f}" if isinstance(o2, (int, float)) else "—")
    with col4:
        water = (current_telemetry or {}).get("product_water_reserve_l")
        st.metric("Product water (L)", f"{water:.1f}" if isinstance(water, (int, float)) else "—")
    with col5:
        st.metric("Overall health", (current_health or {}).get("overall", "—"))
    with col6:
        st.metric(
            "Subsystem status",
            f"CO2 {(current_health or {}).get('co2_status', '—')} / "
            f"O2 {(current_health or {}).get('o2_status', '—')}",
        )


def _draw_threshold_bands(ax, thresholds: Dict[str, Any], *, co2: bool, o2: bool, water: bool) -> None:
    if co2:
        for key, color, style in (
            ("co2_storage_high_kg", "#f0ad4e", "--"),
            ("co2_storage_critical_kg", "#d9534f", "-"),
        ):
            value = thresholds.get(key)
            if isinstance(value, (int, float)):
                ax.axhline(value, color=color, linestyle=style, linewidth=1.0, alpha=0.8, label=key)
    if o2:
        for key, color, style in (
            ("o2_storage_low_kg", "#f0ad4e", "--"),
            ("o2_storage_critical_kg", "#d9534f", "-"),
        ):
            value = thresholds.get(key)
            if isinstance(value, (int, float)):
                ax.axhline(value, color=color, linestyle=style, linewidth=1.0, alpha=0.8, label=key)
    if water:
        for key, color, style in (
            ("product_water_low_l", "#f0ad4e", "--"),
            ("product_water_critical_l", "#d9534f", "-"),
        ):
            value = thresholds.get(key)
            if isinstance(value, (int, float)):
                ax.axhline(value, color=color, linestyle=style, linewidth=1.0, alpha=0.8, label=key)


def render_ssos_storage_plot(
    telemetry_rows: List[Dict[str, Any]],
    *,
    summary: Optional[Dict[str, Any]] = None,
    highlight_step: Optional[int] = None,
) -> None:
    st.subheader("Storage trajectories")
    if not telemetry_rows:
        st.info("No telemetry rows.")
        return

    plot_rows = series_by_step(telemetry_rows)
    steps = [int(r["step"]) for r in plot_rows]
    co2 = [r.get("co2_storage_kg") for r in plot_rows]
    o2 = [r.get("o2_storage_kg") for r in plot_rows]
    water = [r.get("product_water_reserve_l") for r in plot_rows]
    cabin_co2 = has_plant_sim_topics(telemetry_rows)
    co2_label = "Cabin CO2 (kg)" if cabin_co2 else "CO2 storage (kg)"
    thresholds = thresholds_from_summary(summary or {})

    fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
    axes[0].plot(steps, co2, label=co2_label, color="#c44e52")
    axes[1].plot(steps, o2, label="O2 storage (kg)", color="#4c72b0")
    axes[2].plot(steps, water, label="Product water (L)", color="#55a868")
    if thresholds:
        _draw_threshold_bands(axes[0], thresholds, co2=True, o2=False, water=False)
        _draw_threshold_bands(axes[1], thresholds, co2=False, o2=True, water=False)
        _draw_threshold_bands(axes[2], thresholds, co2=False, o2=False, water=True)
    for ax in axes:
        ax.legend(loc="upper left", fontsize=8)
        ax.grid(True, alpha=0.3)
        if highlight_step is not None:
            ax.axvline(highlight_step, color="gray", linestyle="--", alpha=0.6)
    axes[-1].set_xlabel("Step")
    if cabin_co2:
        st.caption(
            "plant_sim maps cabin CO₂ inventory to `co2_storage_kg` (danger signal); "
            "captured tank CO₂ is under raw_topics.plant_sim."
        )
    if thresholds is None:
        st.caption("Threshold band lines not in this run's summary.json — series and status chips only.")
    else:
        st.caption("Band lines from summary.json thresholds recorded at simulation time.")
    st.pyplot(fig, clear_figure=True)


def render_ssos_schematic(
    *,
    step: int,
    telemetry_rows: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
) -> None:
    """Fixed ECLSS block diagram; numbers only from run artifacts."""
    st.subheader("ECLSS schematic")
    telemetry_row = select_row_for_step(telemetry_rows, step)
    metabolism_map = extract_metabolism_by_step(telemetry_rows)
    ops_flows = extract_ops_flows(events)
    node_numbers = build_step_node_numbers(
        step=step,
        telemetry_row=telemetry_row,
        ops_flows=ops_flows,
        metabolism=metabolism_map.get(step),
    )

    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 5)
    ax.axis("off")

    layout = {
        "crew": (0.5, 3.2, 1.6, 1.2),
        "cabin": (2.5, 3.2, 1.6, 1.2),
        "ars": (4.5, 3.2, 1.6, 1.2),
        "ogs": (6.5, 3.2, 1.6, 1.2),
        "wrs": (8.2, 3.2, 1.6, 1.2),
        "co2_tank": (4.5, 1.0, 1.6, 1.2),
        "buffers": (6.5, 1.0, 1.6, 1.2),
    }
    for name, (x, y, w, h) in layout.items():
        rect = plt.Rectangle((x, y), w, h, fill=False, edgecolor="#333333", linewidth=1.2)
        ax.add_patch(rect)
        lines = node_numbers.get(name) or []
        body = "\n".join(lines) if lines else "—"
        ax.text(x + w / 2, y + h - 0.15, name.upper(), ha="center", va="top", fontsize=9, fontweight="bold")
        ax.text(x + 0.08, y + h - 0.45, body, ha="left", va="top", fontsize=7.5)

    st.caption(f"Step {step}: values from telemetry, metabolism, and event result.details only.")
    st.pyplot(fig, clear_figure=True)


def render_ssos_flow_detail(
    *,
    step: int,
    telemetry_rows: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
    table_height: Optional[int] = None,
) -> None:
    st.subheader("Flow detail")
    metabolism_map = extract_metabolism_by_step(telemetry_rows)
    ops_flows = extract_ops_flows(events)
    rows = flatten_flow_table(
        step=step,
        metabolism=metabolism_map.get(step),
        ops_flows=ops_flows,
    )
    if not rows:
        st.caption("No metabolism or operational flow details for this step in run artifacts.")
        return
    df_kwargs: Dict[str, Any] = {"use_container_width": True, "hide_index": True}
    if isinstance(table_height, int) and table_height > 0:
        df_kwargs["height"] = table_height
    st.dataframe(rows, **df_kwargs)


def render_plant_sim_panel(
    telemetry_rows: List[Dict[str, Any]],
    *,
    highlight_step: Optional[int] = None,
    show_empty: bool = False,
) -> None:
    series = plant_sim_series(telemetry_rows)
    st.subheader("plant_sim ledgers")
    if not series:
        if show_empty:
            st.caption("No plant_sim ledgers in this run.")
        return

    steps = [row["step"] for row in series]
    captured = [row.get("captured_co2_kg") for row in series]
    urine = [row.get("urine_buffer_l") for row in series]
    grey = [row.get("grey_water_collected_l") for row in series]

    fig, axes = plt.subplots(3, 1, figsize=(10, 7.5), sharex=True)
    axes[0].plot(steps, captured, label="Captured CO2 (kg)", color="#c44e52")
    axes[1].plot(steps, urine, label="Urine buffer (L)", color="#8172b3")
    axes[1].plot(steps, grey, label="Grey water (L)", color="#55a868")
    crew_alive = [row.get("crew_alive") for row in series]
    if any(val is not None for val in crew_alive):
        axes[2].plot(steps, crew_alive, label="Crew alive", color="#4c72b0", marker="o")
    for ax in axes:
        ax.legend(loc="upper left")
        ax.grid(True, alpha=0.3)
        if highlight_step is not None:
            ax.axvline(highlight_step, color="gray", linestyle="--", alpha=0.6)
    axes[-1].set_xlabel("Step")
    st.pyplot(fig, clear_figure=True)

    if highlight_step is not None:
        latest = select_row_for_step(series, highlight_step)
        if latest is None:
            st.caption(
                f"No plant_sim ledger at step {highlight_step}; "
                "cumulative metrics omitted (chart still shows the full run)."
            )
            return
    else:
        latest = series[-1]
    cols = st.columns(5)
    with cols[0]:
        val = latest.get("total_o2_shortfall_kg")
        st.metric("O2 shortfall (kg)", f"{val:.3f}" if isinstance(val, (int, float)) else "—")
    with cols[1]:
        val = latest.get("total_water_shortfall_l")
        st.metric("Water shortfall (L)", f"{val:.3f}" if isinstance(val, (int, float)) else "—")
    with cols[2]:
        val = latest.get("total_co2_vented_kg")
        st.metric("CO2 vented (kg)", f"{val:.3f}" if isinstance(val, (int, float)) else "—")
    with cols[3]:
        val = latest.get("total_wrs_brine_loss_l")
        st.metric("WRS brine loss (L)", f"{val:.3f}" if isinstance(val, (int, float)) else "—")
    with cols[4]:
        alive = latest.get("crew_alive")
        lost = latest.get("crew_lost_total")
        if isinstance(alive, (int, float)):
            st.metric("Crew remaining", int(alive), delta=f"-{int(lost)}" if isinstance(lost, (int, float)) and lost else None)
        else:
            st.metric("Crew remaining", "—")


def render_ssos_operational_timeline(
    events: List[Dict[str, Any]],
    *,
    table_height: Optional[int] = None,
) -> None:
    st.subheader("Operational commands")
    operational = filter_ssos_operational_events(events)
    if not operational:
        st.caption("No operational commands recorded.")
        return
    rows = []
    for event in operational:
        cmd = event.get("command") or {}
        result = event.get("result") if isinstance(event.get("result"), dict) else {}
        details = result.get("details") or event.get("details")
        detail_text = ""
        if isinstance(details, dict) and details:
            detail_text = ", ".join(f"{k}={v}" for k, v in sorted(details.items()))
        rows.append(
            {
                "step": event.get("step"),
                "kind": cmd.get("kind"),
                "success": event.get("success", result.get("success")),
                "issued_by": cmd.get("issued_by"),
                "details": detail_text or None,
                "message": event.get("message") or result.get("message"),
            }
        )
    df_kwargs: Dict[str, Any] = {"use_container_width": True, "hide_index": True}
    if isinstance(table_height, int) and table_height > 0:
        df_kwargs["height"] = table_height
    st.dataframe(rows, **df_kwargs)


def render_anomaly_status_panel(
    *,
    step: int,
    telemetry_rows: List[Dict[str, Any]],
    health_rows: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
    summary: Optional[Dict[str, Any]] = None,
    table_height: Optional[int] = None,
) -> None:
    """Active anomaly / health stress at the selected step (additive panel)."""
    st.subheader("Anomaly / stress status")
    rows = extract_anomaly_status(
        step=step,
        telemetry_rows=telemetry_rows,
        health_rows=health_rows,
        events=events,
        summary=summary,
    )
    st.caption(
        "Derived from telemetry failure flags, health bands (worst of pre/post_ops for the step; "
        "may differ from Status above when ops recovered the band), "
        "scrubber anomaly_flags/events, and plant_sim shortfall ledgers — "
        "elapsed = steps since onset across adjacent recorded steps (gaps break the episode)."
    )
    if not rows:
        st.caption("No active anomaly, subsystem failure, or health stress at this step.")
        return
    df_kwargs: Dict[str, Any] = {"use_container_width": True, "hide_index": True}
    if isinstance(table_height, int) and table_height > 0:
        df_kwargs["height"] = table_height
    st.dataframe(rows, **df_kwargs)


def render_operator_step_panel(
    *,
    step: int,
    messages: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
    summary: Optional[Dict[str, Any]] = None,
) -> None:
    """What operators did and thought at the selected step."""
    st.subheader("Operators at this step")
    payload = extract_operator_step(
        step=step,
        messages=messages,
        events=events,
        summary=summary,
    )
    mode = payload.get("agents_mode") or "—"
    st.caption(f"agents_mode={mode} · step={step}")

    step_messages = payload.get("messages") or []
    if not step_messages:
        st.caption("No agent messages at this step.")
    else:
        for index, row in enumerate(step_messages, start=1):
            role = row.get("from_role") or "?"
            msg_type = row.get("message_type") or "—"
            source = row.get("decision_source") or "—"
            phase = row.get("deliberation_phase")
            title = f"{index}. {role} · {msg_type} · {source}"
            if phase:
                title += f" · {phase}"
            with st.expander(title, expanded=index == 1):
                st.markdown(f"**Did / said:** {row.get('message') or '—'}")
                thought = row.get("reasoning")
                if thought:
                    st.markdown(f"**Thought:** {thought}")
                else:
                    st.caption("No reasoning field on this message.")

    ops = payload.get("operations") or []
    if ops:
        st.markdown("**Applied / rejected commands at this step**")
        st.dataframe(ops, use_container_width=True, hide_index=True)
    else:
        st.caption("No operational/recovery events at this step.")


_STATE_TIMELINE_COLORS = {
    "safe": "#2ca02c",
    "ok": "#2ca02c",
    "inactive": "#2ca02c",
    "warning": "#ff7f0e",
    "critical": "#d62728",
    "failure": "#d62728",
    "active": "#d62728",
    "unknown": "#7f7f7f",
    "shortfall": "#ff7f0e",
}


def _draw_state_timeline(
    *,
    title: str,
    lanes: List[Dict[str, Any]],
    empty_caption: str,
    policy_caption: Optional[str] = None,
) -> None:
    st.subheader(title)
    if policy_caption:
        st.caption(policy_caption)
    if not lanes or not any(lane.get("segments") for lane in lanes):
        st.caption(empty_caption)
        return

    fig_h = max(2.2, 0.7 + 0.55 * len(lanes))
    fig, ax = plt.subplots(figsize=(11, fig_h))
    yticks = []
    ylabels = []
    used_states: Dict[str, str] = {}

    for index, lane in enumerate(reversed(lanes)):
        y = index
        yticks.append(y + 0.35)
        ylabels.append(str(lane.get("lane") or lane.get("key") or f"lane-{index}"))
        for segment in lane.get("segments") or []:
            state = str(segment.get("state") or "unknown").lower()
            start = float(segment.get("start_step", 0))
            end = float(segment.get("end_step", start + 1))
            width = max(end - start, 0.05)
            color = _STATE_TIMELINE_COLORS.get(state, "#7f7f7f")
            used_states[state] = color
            ax.broken_barh(
                [(start, width)],
                (y, 0.7),
                facecolors=color,
                edgecolors="#111111",
                linewidth=0.4,
            )
            if width >= 1.2:
                ax.text(
                    start + min(0.15, width * 0.05),
                    y + 0.35,
                    state,
                    va="center",
                    ha="left",
                    fontsize=8,
                    color="white",
                    clip_on=True,
                )

    ax.set_yticks(yticks)
    ax.set_yticklabels(ylabels)
    ax.set_xlabel("Step")
    ax.set_ylim(-0.2, len(lanes))
    ax.grid(True, axis="x", alpha=0.25)
    if used_states:
        handles = [
            plt.Rectangle((0, 0), 1, 1, color=color, label=state)
            for state, color in sorted(used_states.items())
        ]
        ax.legend(handles=handles, loc="upper right", fontsize=8, framealpha=0.85)
    st.caption(
        "Segments merge equal states only across adjacent recorded steps; "
        "missing steps split segments rather than stretching across gaps."
    )
    st.pyplot(fig, clear_figure=True)


def render_status_state_timeline(health_rows: List[Dict[str, Any]]) -> None:
    lanes = build_status_timeline_lanes(health_rows)
    _draw_state_timeline(
        title="Status timeline",
        lanes=lanes,
        empty_caption="No health_metrics rows available for a status timeline.",
        policy_caption=(
            "Uses the post-ops health row when a step has pre/post_ops duplicates "
            "(final state after commands). Step Replay's Anomaly panel uses worst-of-step instead."
        ),
    )


def render_anomaly_state_timeline(
    telemetry_rows: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
) -> None:
    lanes = build_anomaly_timeline_lanes(telemetry_rows, events)
    _draw_state_timeline(
        title="Anomaly status timeline",
        lanes=lanes,
        empty_caption="No subsystem failure flags or scrubber anomaly flags in this run.",
    )


def render_ssos_design_proposals(
    run_dir: Path,
    *,
    summary: Optional[Dict[str, Any]] = None,
) -> None:
    st.subheader("Design proposals")
    path = run_dir / "design_proposals.json"
    if not path.exists():
        st.caption("No design_proposals.json for this run.")
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    changes = list_design_changes(payload)
    drivers = extract_design_drivers(payload, summary)

    meta_cols = st.columns(3)
    with meta_cols[0]:
        st.metric("Changes", len(changes))
    with meta_cols[1]:
        st.metric("Proposed by", payload.get("proposed_by", "—"))
    with meta_cols[2]:
        st.metric("Decision source", payload.get("decision_source", "—"))

    st.markdown("##### What observation drove these proposals?")
    if drivers.get("message"):
        st.markdown(f"**Message:** {drivers['message']}")
    if drivers.get("reasoning"):
        st.markdown(f"**Reasoning:** {drivers['reasoning']}")
    change_whys = drivers.get("change_whys") or []
    if change_whys:
        st.markdown("**Per-change why:**")
        for why in change_whys:
            st.markdown(f"- {why}")
    observations = drivers.get("summary_observations") or []
    if observations:
        st.caption("Summary observations: " + " · ".join(observations))
    if not any(
        [
            drivers.get("message"),
            drivers.get("reasoning"),
            change_whys,
            observations,
        ]
    ):
        st.caption("No proposal message, reasoning, why text, or summary observations recorded.")

    if not changes:
        st.caption("Proposal file has no changes[].")
        return

    st.markdown("##### Proposed changes")
    for index, change in enumerate(changes, start=1):
        kind = change.get("change_kind", "—")
        with st.expander(f"{index}. {kind}", expanded=index == 1):
            if change.get("why"):
                st.markdown(f"**Why (observation):** {change['why']}")
            if change.get("what"):
                st.markdown(f"**What (intent):** {change['what']}")
            if change.get("how"):
                st.markdown(f"**How (concrete change):** {change['how']}")
            if not any(change.get(k) for k in ("why", "what", "how")):
                st.caption("Why/What/How not recorded for this change.")
            st.markdown("**Payload**")
            st.json(change.get("payload") or {}, expanded=False)
    graph = payload.get("baseline_graph") or payload.get("ssos_graph") or {}
    rewires = graph.get("rewires") or []
    if rewires:
        st.markdown("##### Graph rewires")
        st.dataframe(rewires, use_container_width=True, hide_index=True)


def render_ssos_summary_highlights(summary: Dict[str, Any]) -> None:
    cols = st.columns(6)
    with cols[0]:
        st.metric("Backend", summary.get("backend", "—"))
    with cols[1]:
        st.metric("ARS step", summary.get("ars_invoked_step", "—"))
    with cols[2]:
        st.metric("OGS step", summary.get("ogs_invoked_step", "—"))
    with cols[3]:
        st.metric("Ops commands", summary.get("operational_command_count", "—"))
    with cols[4]:
        st.metric("Crew remaining", summary.get("crew_remaining", "—"))
    with cols[5]:
        st.metric("Crew lost", summary.get("crew_lost", "—"))
