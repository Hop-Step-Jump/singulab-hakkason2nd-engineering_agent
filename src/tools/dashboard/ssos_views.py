"""Dashboard views for ssos_eclss_loop run outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import matplotlib.pyplot as plt
import streamlit as st

from tools.dashboard.jsonl_rows import select_row_for_step, series_by_step

SSOS_OPERATIONAL_KINDS = frozenset(
    {
        "air_revitalisation",
        "oxygen_generation",
        "water_recovery",
        "request_co2",
        "request_o2",
    }
)


def scenario_name(summary: Dict[str, Any]) -> str:
    return str(summary.get("scenario", ""))


def is_ssos_eclss_loop(summary: Dict[str, Any]) -> bool:
    return scenario_name(summary) == "ssos_eclss_loop"


def plant_sim_topic(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    raw = row.get("raw_topics")
    if not isinstance(raw, dict):
        return None
    topic = raw.get("plant_sim")
    return topic if isinstance(topic, dict) else None


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
            }
        )
    return rows


def filter_ssos_operational_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        e
        for e in events
        if (e.get("command") or {}).get("kind") in SSOS_OPERATIONAL_KINDS
    ]


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


def render_ssos_storage_plot(
    telemetry_rows: List[Dict[str, Any]],
    *,
    highlight_step: Optional[int] = None,
) -> None:
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

    fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
    axes[0].plot(steps, co2, label=co2_label, color="#c44e52")
    axes[1].plot(steps, o2, label="O2 storage (kg)", color="#4c72b0")
    axes[2].plot(steps, water, label="Product water (L)", color="#55a868")
    for ax in axes:
        ax.legend(loc="upper left")
        ax.grid(True, alpha=0.3)
        if highlight_step is not None:
            ax.axvline(highlight_step, color="gray", linestyle="--", alpha=0.6)
    axes[-1].set_xlabel("Step")
    if cabin_co2:
        st.caption(
            "plant_sim maps cabin CO₂ inventory to `co2_storage_kg` (danger signal); "
            "captured tank CO₂ is under raw_topics.plant_sim."
        )
    st.pyplot(fig, clear_figure=True)


def render_plant_sim_panel(
    telemetry_rows: List[Dict[str, Any]],
    *,
    highlight_step: Optional[int] = None,
) -> None:
    series = plant_sim_series(telemetry_rows)
    if not series:
        return

    st.subheader("plant_sim ledgers")
    steps = [row["step"] for row in series]
    captured = [row.get("captured_co2_kg") for row in series]
    urine = [row.get("urine_buffer_l") for row in series]
    grey = [row.get("grey_water_collected_l") for row in series]

    fig, axes = plt.subplots(2, 1, figsize=(10, 5.5), sharex=True)
    axes[0].plot(steps, captured, label="Captured CO2 (kg)", color="#c44e52")
    axes[1].plot(steps, urine, label="Urine buffer (L)", color="#8172b3")
    axes[1].plot(steps, grey, label="Grey water (L)", color="#55a868")
    for ax in axes:
        ax.legend(loc="upper left")
        ax.grid(True, alpha=0.3)
        if highlight_step is not None:
            ax.axvline(highlight_step, color="gray", linestyle="--", alpha=0.6)
    axes[-1].set_xlabel("Step")
    st.pyplot(fig, clear_figure=True)

    latest = select_row_for_step(series, highlight_step) if highlight_step is not None else series[-1]
    if latest is None:
        latest = series[-1]
    cols = st.columns(4)
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


def render_ssos_operational_timeline(events: List[Dict[str, Any]]) -> None:
    operational = filter_ssos_operational_events(events)
    if not operational:
        st.caption("No operational commands recorded.")
        return
    rows = []
    for event in operational:
        cmd = event.get("command") or {}
        rows.append(
            {
                "step": event.get("step"),
                "kind": cmd.get("kind"),
                "success": event.get("success"),
                "issued_by": cmd.get("issued_by"),
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)


def render_ssos_design_proposals(run_dir: Path) -> None:
    path = run_dir / "design_proposals.json"
    if not path.exists():
        st.caption("No design_proposals.json for this run.")
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    changes = payload.get("changes") or []
    st.markdown(f"**Design proposals** ({len(changes)} change(s))")
    graph = payload.get("ssos_graph") or {}
    rewires = graph.get("rewires") or []
    if rewires:
        st.markdown("**Graph rewires**")
        st.dataframe(rewires, use_container_width=True, hide_index=True)
    if changes:
        st.json(payload, expanded=False)


def render_ssos_summary_highlights(summary: Dict[str, Any]) -> None:
    cols = st.columns(4)
    with cols[0]:
        st.metric("Backend", summary.get("backend", "—"))
    with cols[1]:
        st.metric("ARS step", summary.get("ars_invoked_step", "—"))
    with cols[2]:
        st.metric("OGS step", summary.get("ogs_invoked_step", "—"))
    with cols[3]:
        st.metric("Ops commands", summary.get("operational_command_count", "—"))
