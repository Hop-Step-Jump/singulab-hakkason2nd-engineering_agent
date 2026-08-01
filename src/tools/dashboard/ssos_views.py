"""Dashboard views for ssos_eclss_loop run outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import matplotlib.pyplot as plt
import streamlit as st

from tools.dashboard.jsonl_rows import select_row_for_step, series_by_step


def scenario_name(summary: Dict[str, Any]) -> str:
    return str(summary.get("scenario", ""))


def is_ssos_eclss_loop(summary: Dict[str, Any]) -> bool:
    return scenario_name(summary) == "ssos_eclss_loop"


def render_ssos_health_card(
    telemetry_rows: List[Dict[str, Any]],
    health_rows: List[Dict[str, Any]],
    current_step: int,
) -> None:
    current_telemetry = select_row_for_step(telemetry_rows, current_step)
    current_health = select_row_for_step(health_rows, current_step)

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        st.metric("Step", current_step)
    with col2:
        co2 = (current_telemetry or {}).get("co2_storage_kg")
        st.metric("CO2 storage (kg)", f"{co2:.1f}" if isinstance(co2, (int, float)) else "—")
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

    fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
    axes[0].plot(steps, co2, label="CO2 storage (kg)", color="#c44e52")
    axes[1].plot(steps, o2, label="O2 storage (kg)", color="#4c72b0")
    axes[2].plot(steps, water, label="Product water (L)", color="#55a868")
    for ax in axes:
        ax.legend(loc="upper left")
        ax.grid(True, alpha=0.3)
        if highlight_step is not None:
            ax.axvline(highlight_step, color="gray", linestyle="--", alpha=0.6)
    axes[-1].set_xlabel("Step")
    st.pyplot(fig, clear_figure=True)


def render_ssos_operational_timeline(events: List[Dict[str, Any]]) -> None:
    operational = [
        e
        for e in events
        if (e.get("command") or {}).get("kind")
        in {"air_revitalisation", "oxygen_generation", "request_co2", "request_o2"}
    ]
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
