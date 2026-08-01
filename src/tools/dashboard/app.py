"""Streamlit dashboard for scrubber_degradation run outputs."""

from __future__ import annotations

import copy
import html
import itertools
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import matplotlib.pyplot as plt
import streamlit as st
import streamlit.components.v1 as components

from tools.dashboard import ssos_views
from environment.scrubber.eclss_ops.telemetry import CO2_RECOVERY_PPM
from tools.dashboard.jsonl_rows import select_row_for_step, series_by_step

RESULTS_ROOT = Path(__file__).resolve().parents[2] / "experiments" / "results"


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _list_runs() -> List[Path]:
    if not RESULTS_ROOT.exists():
        return []
    runs = []
    for entry in RESULTS_ROOT.iterdir():
        if entry.is_dir() and (entry / "summary.json").exists():
            runs.append(entry)
    return sorted(runs, key=lambda p: p.name)


def _select_rows_at_step(rows: List[Dict[str, Any]], step: int) -> List[Dict[str, Any]]:
    return [r for r in rows if int(r.get("step", -1)) == step]


_BCDU_MODE_Y = {"idle": 0, "charging": 1, "discharging": 2, "fault": 3, "safe": 4}


def _build_line_plot_figure(
    telemetry_rows: List[Dict[str, Any]],
    eps_rows: List[Dict[str, Any]],
    *,
    highlight_step: Optional[int] = None,
) -> Optional[plt.Figure]:
    if not telemetry_rows:
        return None

    plot_rows = series_by_step(telemetry_rows)
    steps = [int(r["step"]) for r in plot_rows]
    scrubber_eff = [float(r.get("scrubber_efficiency", 0.0)) for r in plot_rows]
    co2 = [float(r["co2_ppm"]) for r in plot_rows]
    power = [float(r["power_margin_w"]) for r in plot_rows]
    eps_support = [float(r.get("eps_support_w", 0.0)) for r in plot_rows]
    anomaly_start = next(
        (
            int(r["step"])
            for r in plot_rows
            if "scrubber_degradation" in r.get("anomaly_flags", [])
        ),
        None,
    )

    nrows = 6 if eps_rows else 4
    fig, axes = plt.subplots(nrows, 1, figsize=(10, 3 * nrows), sharex=True)
    if nrows == 4:
        axes = list(axes)

    def _maybe_highlight(ax: plt.Axes) -> None:
        if highlight_step is not None:
            ax.axvline(highlight_step, color="#d62728", linestyle=":", linewidth=1)

    baseline_eff = scrubber_eff[0] if scrubber_eff else 0.95
    axes[0].plot(steps, scrubber_eff, color="#bcbd22", linewidth=2)
    axes[0].axhline(baseline_eff, color="#ff7f0e", linestyle="--", linewidth=1)
    if anomaly_start is not None:
        axes[0].axvline(anomaly_start, color="#9467bd", linestyle="--", linewidth=1)
    _maybe_highlight(axes[0])
    axes[0].set_ylim(0.0, 1.05)
    axes[0].set_ylabel("Efficiency")
    axes[0].set_title("Scrubber efficiency (anomaly: scrubber_degradation)")
    axes[0].grid(alpha=0.2)

    axes[1].plot(steps, co2, color="#1f77b4", linewidth=2)
    axes[1].axhline(CO2_RECOVERY_PPM, color="#ff7f0e", linestyle="--", linewidth=1)
    _maybe_highlight(axes[1])
    axes[1].set_ylabel("CO2 (ppm)")
    axes[1].set_title("CO2 trajectory")
    axes[1].grid(alpha=0.2)

    axes[2].plot(steps, power, color="#2ca02c", linewidth=2)
    axes[2].axhline(0.0, color="#ff7f0e", linestyle="--", linewidth=1)
    _maybe_highlight(axes[2])
    axes[2].set_ylabel("Power margin (W)")
    axes[2].set_title("ECLSS net power margin (loads − generation budget; EPS boost added per step)")
    axes[2].grid(alpha=0.2)

    axes[3].plot(steps, eps_support, color="#9467bd", linewidth=2)
    _maybe_highlight(axes[3])
    axes[3].set_ylabel("EPS support (W)")
    axes[3].set_title("EPS support (ECLSS telemetry)")
    axes[3].grid(alpha=0.2)

    if eps_rows:
        eps_plot_rows = series_by_step(eps_rows)
        eps_steps = [int(r["step"]) for r in eps_plot_rows]
        solar_v = [float(r.get("solar_voltage_v") or 0.0) for r in eps_plot_rows]
        bcdu_y = [_BCDU_MODE_Y.get(str(r.get("bcdu_mode", "idle")), 0) for r in eps_plot_rows]
        bcdu_support = [float(r.get("support_w", 0.0)) for r in eps_plot_rows]

        axes[4].plot(eps_steps, solar_v, color="#e377c2", linewidth=2)
        _maybe_highlight(axes[4])
        axes[4].set_ylabel("Solar V")
        axes[4].set_title("SARJ solar voltage (beta fixed in mock)")
        axes[4].grid(alpha=0.2)

        ax_mode = axes[5]
        ax_support = ax_mode.twinx()
        ax_mode.plot(eps_steps, bcdu_y, color="#17becf", linewidth=2, drawstyle="steps-post", label="BCDU mode")
        ax_support.plot(
            eps_steps,
            bcdu_support,
            color="#9467bd",
            linewidth=1.5,
            linestyle="--",
            alpha=0.9,
            label="Support W",
        )
        _maybe_highlight(ax_mode)
        ax_mode.set_yticks(list(_BCDU_MODE_Y.values()))
        ax_mode.set_yticklabels(list(_BCDU_MODE_Y.keys()))
        ax_mode.set_ylabel("BCDU mode")
        ax_support.set_ylabel("Support (W)")
        max_support = max(bcdu_support) if bcdu_support else 1.0
        ax_support.set_ylim(0.0, max(max_support * 1.15, 10.0))
        ax_mode.set_title("BCDU mode (left) + discharge support W (right, dashed)")
        ax_mode.set_xlabel("Step")
        ax_mode.grid(alpha=0.2)
        lines = ax_mode.get_lines() + ax_support.get_lines()
        ax_mode.legend(lines, [line.get_label() for line in lines], loc="upper right", fontsize=8)
        fig._replay_highlight_axes = list(axes[:6])
    else:
        axes[3].set_xlabel("Step")
        fig._replay_highlight_axes = list(axes)

    return fig


def _line_plot(
    telemetry_rows: List[Dict[str, Any]],
    eps_rows: List[Dict[str, Any]],
    current_step: int,
) -> None:
    fig = _build_line_plot_figure(
        telemetry_rows,
        eps_rows,
        highlight_step=current_step,
    )
    if fig is None:
        st.info("No telemetry data found.")
        return
    st.pyplot(fig, use_container_width=True)


def _set_plot_highlight(fig: plt.Figure, highlight_step: Optional[int]) -> None:
    """Update cached replay figure with a current-step marker only."""
    for artist in getattr(fig, "_replay_highlight_lines", []):
        artist.remove()
    fig._replay_highlight_lines = []
    if highlight_step is None:
        return
    for ax in getattr(fig, "_replay_highlight_axes", fig.get_axes()):
        line = ax.axvline(highlight_step, color="#d62728", linestyle=":", linewidth=1)
        fig._replay_highlight_lines.append(line)


def _render_static_replay_plot(run: RunViewData, current_step: int) -> None:
    """Draw telemetry plots once per run; refresh only the step marker."""
    if st.session_state.get("replay_static_plot_run") != run.run_name:
        st.session_state.replay_static_plot_run = run.run_name
        st.session_state.replay_static_plot_fig = _build_line_plot_figure(
            run.telemetry,
            run.eps_telemetry,
            highlight_step=None,
        )

    fig = st.session_state.get("replay_static_plot_fig")
    if fig is None:
        st.info("No telemetry data found.")
        return
    _set_plot_highlight(fig, current_step)
    st.pyplot(fig, use_container_width=True, clear_figure=False)


def _escape_html(text: Any) -> str:
    return html.escape(str(text or ""), quote=True)


def _event_timeline_label(event: Dict[str, Any]) -> str:
    kind = str(event.get("kind", "event"))
    if kind == "anomaly_injected":
        spec = event.get("spec") or {}
        return (
            f"Anomaly scheduled: {spec.get('name', 'anomaly')} "
            f"(starts step {spec.get('start_step', '?')})"
        )
    if kind == "/eclss/events/anomaly":
        flags = event.get("flags") or []
        return f"Anomaly active: {', '.join(flags) if flags else '—'}"
    if kind == "/eclss/events/recovery_applied":
        command = event.get("command") or {}
        issued_by = command.get("issued_by", "?")
        return (
            f"Recovery applied: {command.get('kind', '?')} "
            f"→ {command.get('value', '?')} ({issued_by})"
        )
    if kind == "/eclss/events/design_change":
        change = event.get("change") or {}
        return f"Design change: {change.get('kind', '?')} ({change.get('proposed_by', '?')})"
    if event.get("message"):
        return str(event["message"])
    return kind


_REPLAY_TIMELINE_HEIGHT = 520
_REPLAY_FEED_HEIGHT = 300


def _step_visual_state(step: int, current_step: int) -> Tuple[float, str, str, str]:
    """Opacity, title color, body color, dot style for timeline nodes."""
    if step == current_step:
        return 1.0, "#ffffff", "#e8e8e8", "background:#ffffff;box-shadow:0 0 6px rgba(255,255,255,0.8);"
    if step < current_step:
        return 0.45, "#8a8a8a", "#6f6f6f", "background:#666666;"
    return 0.25, "#5a5a5a", "#4a4a4a", "background:#3a3a3a;"


def _nearest_step_anchor(available_steps: List[int], current_step: int) -> int:
    if not available_steps:
        return current_step
    if current_step in available_steps:
        return current_step
    prior = [step for step in available_steps if step <= current_step]
    if prior:
        return prior[-1]
    return min(available_steps)


def _group_events_by_step(events: List[Dict[str, Any]]) -> List[Tuple[int, List[str]]]:
    ordered = sorted(events, key=lambda row: (int(row.get("step", 0)), str(row.get("kind", ""))))
    groups: List[Tuple[int, List[str]]] = []
    for step, rows in itertools.groupby(ordered, key=lambda row: int(row.get("step", 0))):
        labels = [_event_timeline_label(event) for event in rows]
        groups.append((step, labels))
    return groups


def _render_scrolling_html(
    inner_html: str,
    *,
    height_px: int,
    scroll_anchor_id: str,
    panel_style: str = "",
) -> None:
    """Render scrollable HTML and center the anchor element (components allow JS)."""
    doc = f"""<!DOCTYPE html>
<html><head><style>
  html, body {{ margin:0; padding:0; background:transparent; }}
  #scroll-panel {{
    height:{height_px}px;
    overflow-y:auto;
    overflow-x:hidden;
    {panel_style}
  }}
</style></head><body>
  <div id="scroll-panel">{inner_html}</div>
  <script>
    (function() {{
      const panel = document.getElementById("scroll-panel");
      const target = document.getElementById("{scroll_anchor_id}");
      if (!panel || !target) return;
      const top = target.getBoundingClientRect().top
        - panel.getBoundingClientRect().top
        + panel.scrollTop;
      panel.scrollTop = Math.max(0, top - panel.clientHeight / 2 + target.clientHeight / 2);
    }})();
  </script>
</body></html>"""
    components.html(doc, height=height_px + 6, scrolling=False)


def _render_event_timeline(events: List[Dict[str, Any]], current_step: int) -> None:
    st.markdown("**Event timeline**")
    if not events:
        st.caption("No events logged.")
        return

    groups = _group_events_by_step(events)
    anchor_step = _nearest_step_anchor([step for step, _ in groups], current_step)
    anchor_id = f"tl-step-{anchor_step}"

    nodes: List[str] = []
    for step, labels in groups:
        opacity, title_color, body_color, dot_style = _step_visual_state(step, current_step)
        label_html = "<br>".join(
            f"<span style='color:{body_color};'>{_escape_html(label)}</span>" for label in labels
        )
        dot_size = "12px" if step == current_step else "10px"
        nodes.append(
            f"<div id='tl-step-{step}' style='display:flex;gap:10px;margin-bottom:16px;"
            f"opacity:{opacity};position:relative;z-index:1;'>"
            f"<div style='width:22px;display:flex;justify-content:center;flex-shrink:0;'>"
            f"<div style='width:{dot_size};height:{dot_size};border-radius:50%;"
            f"margin-top:3px;{dot_style}'></div></div>"
            f"<div style='flex:1;line-height:1;font-size:0.82rem;'>"
            f"<div style='font-weight:600;color:{title_color};'>Step {step}</div>"
            f"<div style='margin-top:2px;'>{label_html}</div>"
            f"</div></div>"
        )

    inner = (
        "<div style='background:#0a0a0a;border-radius:8px;padding:14px 10px 8px 6px;"
        "position:relative;min-height:100%;'>"
        "<div style='position:absolute;left:16px;top:18px;bottom:18px;width:2px;"
        "background:rgba(255,255,255,0.35);z-index:0;'></div>"
        + "".join(nodes)
        + "</div>"
    )
    _render_scrolling_html(
        inner,
        height_px=_REPLAY_TIMELINE_HEIGHT,
        scroll_anchor_id=anchor_id,
    )


def _messages_through_step(messages: List[Dict[str, Any]], current_step: int) -> List[Dict[str, Any]]:
    return [row for row in messages if int(row.get("step", -1)) <= current_step]


def _group_messages_by_step(messages: List[Dict[str, Any]]) -> List[Tuple[int, List[Dict[str, Any]]]]:
    ordered = sorted(messages, key=lambda row: int(row.get("step", -1)))
    groups: List[Tuple[int, List[Dict[str, Any]]]] = []
    for step, rows in itertools.groupby(ordered, key=lambda row: int(row.get("step", -1))):
        groups.append((step, list(rows)))
    return groups


def _render_agent_scroll_feed(
    messages: List[Dict[str, Any]],
    current_step: int,
    *,
    field: str,
    title: str,
    empty_caption: str,
    height_px: int = _REPLAY_FEED_HEIGHT,
    anchor_prefix: str,
) -> None:
    st.markdown(f"**{title}**")
    visible = _messages_through_step(messages, current_step)
    if field == "reasoning":
        visible = [row for row in visible if str(row.get("reasoning", "")).strip()]

    if not visible:
        st.caption(empty_caption)
        return

    groups = _group_messages_by_step(visible)
    anchor_step = _nearest_step_anchor([step for step, _ in groups], current_step)
    anchor_id = f"{anchor_prefix}-step-{anchor_step}"

    blocks: List[str] = [
        "<div style='font-size:0.82rem;line-height:1;padding-right:4px;color:#e8e8e8;'>"
    ]
    for step, rows in groups:
        is_current = step == current_step
        marker = " ▶" if is_current else ""
        header_color = "#f0ad4e" if is_current else "#ffffff"
        blocks.append(
            f"<div id='{anchor_prefix}-step-{step}' style='margin-bottom:6px;'>"
            f"<div style='font-weight:600;margin:6px 0 2px 0;color:{header_color};'>"
            f"Step {step}{marker}</div>"
        )
        for row in rows:
            role = _escape_html(row.get("from_role", "?"))
            msg_type = _escape_html(row.get("message_type", "") or "")
            body = _escape_html(str(row.get(field, "") or "").strip() or "—")
            type_suffix = (
                f" <span style='color:#9aa0a6;'>({msg_type})</span>" if msg_type else ""
            )
            blocks.append(
                "<div style='margin:0 0 3px 8px;color:#e8e8e8;'>"
                f"<span style='font-weight:500;color:#ffffff;'>{role}</span>"
                f"{type_suffix}: {body}"
                "</div>"
            )
        blocks.append("</div>")
    blocks.append("</div>")

    _render_scrolling_html(
        "".join(blocks),
        height_px=height_px,
        scroll_anchor_id=anchor_id,
        panel_style="color:#e8e8e8;",
    )


def _init_replay_state(run_name: str, max_step: int) -> None:
    if st.session_state.get("replay_run_name") != run_name:
        st.session_state.replay_run_name = run_name
        st.session_state.replay_step = 1
    st.session_state.replay_step = min(
        max(int(st.session_state.get("replay_step", 1)), 1),
        max_step,
    )


def _replay_step_controls(max_step: int) -> int:
    if "replay_step" not in st.session_state:
        st.session_state.replay_step = 1

    control_cols = st.columns([5, 1])
    with control_cols[1]:
        if st.button("Reset", key="replay_reset_btn"):
            st.session_state.replay_step = 1

    with control_cols[0]:
        st.session_state.replay_step = st.slider(
            "Replay step",
            min_value=1,
            max_value=max_step,
            value=int(st.session_state.replay_step),
        )

    return int(st.session_state.replay_step)


def _render_run_replay_view(run: RunViewData) -> None:
    """Per-run step replay: timeline, plots, and agent discourse."""
    max_step = _max_telemetry_step(run.telemetry)
    _init_replay_state(run.run_name, max_step)
    st.session_state.replay_run_name = run.run_name

    st.markdown(f"**`{run.run_name}`** — step-by-step replay")
    st.caption(f"`{run.run_dir}`")
    current_step = _replay_step_controls(max_step)

    left_col, center_col, right_col = st.columns([1, 2.2, 1.3], gap="medium")

    with left_col:
        _render_event_timeline(run.events, current_step)

    with center_col:
        _render_health_card(run.telemetry, run.health, run.eps_telemetry, current_step)
        _render_static_replay_plot(run, current_step)

    with right_col:
        _render_agent_scroll_feed(
            run.messages,
            current_step,
            field="message",
            title="Agent messages",
            empty_caption="No agent messages through this step.",
            anchor_prefix="msg",
        )
        _render_agent_scroll_feed(
            run.messages,
            current_step,
            field="reasoning",
            title="Agent reasoning",
            empty_caption="No agent reasoning through this step.",
            anchor_prefix="reason",
        )


def _render_step_tables(
    messages: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
    provenance: List[Dict[str, Any]],
    current_step: int,
) -> None:
    step_messages = _select_rows_at_step(messages, current_step)
    step_events = _select_rows_at_step(events, current_step)
    step_provenance = _select_rows_at_step(provenance, current_step)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.subheader("Messages")
        if step_messages:
            st.dataframe(step_messages, use_container_width=True, hide_index=True)
        else:
            st.caption("No messages at this step.")
    with col2:
        st.subheader("Events")
        if step_events:
            st.dataframe(step_events, use_container_width=True, hide_index=True)
        else:
            st.caption("No events at this step.")
    with col3:
        st.subheader("Provenance")
        if step_provenance:
            st.dataframe(step_provenance, use_container_width=True, hide_index=True)
        else:
            st.caption("No provenance records at this step.")


_NODE_ANCHORS: Dict[str, Tuple[float, float]] = {
    "cabin": (0.0, 0.55),
    "manifold": (0.45, 0.55),
    "scrubber": (0.9, 0.55),
    "power_bus": (0.45, 0.05),
}

_EDGE_COLORS = {
    "flow": "#1f77b4",
    "bypass": "#ff7f0e",
    "power": "#9467bd",
    "monitor": "#e377c2",
}

_NODE_COLORS = {
    "volume": "#8c564b",
    "manifold": "#17becf",
    "scrubber": "#2ca02c",
    "electrical": "#d62728",
    "threshold_monitor": "#bcbd22",
    "monitor": "#bcbd22",
    "synthetic": "#9aa5b1",
    "node": "#6c757d",
}

_BASELINE_EDGE_KEYS = frozenset(
    {
        ("cabin", "manifold", "flow"),
        ("manifold", "scrubber", "flow"),
        ("scrubber", "cabin", "flow"),
        ("power_bus", "scrubber", "power"),
    }
)
_DESIGN_EDGE_COLOR = "#c0392b"


def _edge_key(edge: Dict[str, Any]) -> Tuple[str, str, str]:
    return (
        str(edge.get("source", "")),
        str(edge.get("target", "")),
        str(edge.get("kind", "flow")),
    )


def _prepare_topology_for_display(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    *,
    proposed_edge_keys: Optional[Set[Tuple[str, str, str]]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Set[Tuple[str, str, str]]]:
    """Deduplicate edges, synthesize missing endpoints, tag proposal deltas."""
    node_by_id: Dict[str, Dict[str, Any]] = {}
    for node in nodes:
        node_id = str(node.get("id", ""))
        if node_id:
            node_by_id[node_id] = dict(node)

    seen_edges: Set[Tuple[str, str, str]] = set()
    deduped_edges: List[Dict[str, Any]] = []
    for edge in edges:
        key = _edge_key(edge)
        if key in seen_edges:
            continue
        seen_edges.add(key)
        deduped_edges.append(edge)
        for endpoint in (key[0], key[1]):
            if endpoint and endpoint not in node_by_id:
                node_by_id[endpoint] = {
                    "id": endpoint,
                    "name": endpoint,
                    "kind": "synthetic",
                    "synthetic": True,
                }

    if proposed_edge_keys is None:
        proposed_edge_keys = {key for key in seen_edges if key not in _BASELINE_EDGE_KEYS}
    display_nodes = list(node_by_id.values())
    return display_nodes, deduped_edges, proposed_edge_keys


def _layout_node_positions(nodes: List[Dict[str, Any]]) -> Dict[str, Tuple[float, float]]:
    positions: Dict[str, Tuple[float, float]] = {}
    extras: List[str] = []
    for node in nodes:
        node_id = str(node.get("id", ""))
        if not node_id:
            continue
        if node_id in _NODE_ANCHORS:
            positions[node_id] = _NODE_ANCHORS[node_id]
        else:
            extras.append(node_id)
    for index, node_id in enumerate(extras):
        angle = (2.0 * math.pi * index) / max(len(extras), 1)
        positions[node_id] = (0.45 + 0.32 * math.cos(angle), 0.3 + 0.22 * math.sin(angle))
    return positions


_LABEL_BBOX = {
    "boxstyle": "round,pad=0.25",
    "facecolor": "white",
    "edgecolor": "#b0b8c4",
    "linewidth": 0.8,
    "alpha": 0.95,
}


def _draw_topology_graph(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    proposed_edge_keys: Set[Tuple[str, str, str]],
    *,
    proposed_node_ids: Optional[Set[str]] = None,
    title: str = "ECLSS topology",
) -> None:
    if not nodes:
        st.info("No topology nodes to display.")
        return

    if proposed_node_ids is None:
        proposed_node_ids = set()

    positions = _layout_node_positions(nodes)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    fig.patch.set_facecolor("#eef1f5")
    ax.set_facecolor("#eef1f5")

    for edge in edges:
        source = str(edge.get("source", ""))
        target = str(edge.get("target", ""))
        if source not in positions or target not in positions:
            continue
        x1, y1 = positions[source]
        x2, y2 = positions[target]
        kind = str(edge.get("kind", "flow"))
        key = _edge_key(edge)
        is_proposed = key in proposed_edge_keys
        color = _DESIGN_EDGE_COLOR if is_proposed else _EDGE_COLORS.get(kind, "#7f7f7f")
        linestyle = "dashed" if is_proposed else "solid"
        ax.annotate(
            "",
            xy=(x2, y2),
            xytext=(x1, y1),
            arrowprops={
                "arrowstyle": "->",
                "color": color,
                "lw": 2.5 if is_proposed else 2.0,
                "linestyle": linestyle,
                "shrinkA": 14,
                "shrinkB": 14,
            },
            zorder=1 if is_proposed else 2,
        )
        mid_x = (x1 + x2) / 2.0
        mid_y = (y1 + y2) / 2.0
        edge_label = f"{kind}*" if is_proposed else kind
        ax.text(
            mid_x,
            mid_y,
            edge_label,
            fontsize=8,
            color="#1f2933",
            ha="center",
            va="center",
            bbox=_LABEL_BBOX,
            zorder=3,
        )

    for node in nodes:
        node_id = str(node.get("id", ""))
        if node_id not in positions:
            continue
        x, y = positions[node_id]
        kind = str(node.get("kind", "volume"))
        is_proposed_node = node_id in proposed_node_ids
        is_synthetic = bool(node.get("synthetic"))
        if is_synthetic:
            color = _NODE_COLORS["synthetic"]
            size = 500
        else:
            color = _NODE_COLORS.get(kind, "#7f7f7f")
            size = 700 if is_proposed_node else 900
        edgecolor = _DESIGN_EDGE_COLOR if is_proposed_node else "#2d3436"
        marker = "s" if is_synthetic else "o"
        ax.scatter(
            [x],
            [y],
            s=size,
            c=color,
            marker=marker,
            edgecolors=edgecolor,
            linewidths=2.0 if is_proposed_node else 1.5,
            zorder=4,
        )
        label = str(node.get("name", node_id))
        suffix = " [proposed]" if is_proposed_node and not is_synthetic else ""
        if is_synthetic:
            suffix = " [ref]"
        ax.text(
            x,
            y,
            f"{label}\n({node_id}){suffix}",
            ha="center",
            va="center",
            fontsize=8,
            color="#1f2933",
            bbox=_LABEL_BBOX,
            zorder=5,
        )

    ax.set_xlim(-0.15, 1.05)
    ax.set_ylim(-0.05, 0.75)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(title, color="#1f2933")
    st.pyplot(fig, use_container_width=True)
    plt.close(fig)


def _run_end_design_state(
    design_state_rows: List[Dict[str, Any]],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    if not design_state_rows:
        return {}, {}
    final_row = design_state_rows[-1]
    return dict(final_row.get("topology", {})), dict(final_row.get("parameters", {}))


def _topology_edge_keys(topology: Dict[str, Any]) -> Set[Tuple[str, str, str]]:
    return {_edge_key(edge) for edge in topology.get("edges", [])}


def _topology_node_ids(topology: Dict[str, Any]) -> Set[str]:
    return {str(node.get("id", "")) for node in topology.get("nodes", []) if node.get("id")}


def _apply_proposal_changes(
    baseline_topology: Dict[str, Any],
    baseline_parameters: Dict[str, float],
    changes: List[Dict[str, Any]],
) -> Tuple[Dict[str, Any], Dict[str, float]]:
    topology = copy.deepcopy(baseline_topology)
    parameters = dict(baseline_parameters)
    nodes = list(topology.get("nodes", []))
    edges = list(topology.get("edges", []))

    for change in changes:
        change_kind = str(change.get("change_kind", ""))
        payload = change.get("payload", {})
        if not isinstance(payload, dict):
            payload = {}

        if change_kind == "add_node":
            node_id = str(payload.get("id", "")).strip()
            if node_id and node_id not in {str(n.get("id", "")) for n in nodes}:
                nodes.append(
                    {
                        "id": node_id,
                        "name": payload.get("name", node_id),
                        "kind": payload.get("kind", "volume"),
                    }
                )
        elif change_kind == "add_edge":
            source = payload.get("node_a")
            target = payload.get("node_b")
            kind = payload.get("kind", "bypass")
            key = (str(source), str(target), str(kind))
            if source and target and key not in {_edge_key(edge) for edge in edges}:
                edges.append({"source": source, "target": target, "kind": kind})
        elif change_kind == "set_parameter":
            key = str(payload.get("key", "")).strip()
            if key:
                try:
                    parameters[key] = float(payload.get("value"))
                except (TypeError, ValueError):
                    continue

    return {"nodes": nodes, "edges": edges}, parameters


def _topology_display_bundle(
    topology: Dict[str, Any],
    proposed_edge_keys: Set[Tuple[str, str, str]],
    proposed_node_ids: Set[str],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    raw_nodes = topology.get("nodes", [])
    raw_edges = topology.get("edges", [])
    nodes, edges, _ = _prepare_topology_for_display(
        raw_nodes,
        raw_edges,
        proposed_edge_keys=proposed_edge_keys,
    )
    table_nodes = [
        {
            **node,
            "proposed": str(node.get("id", "")) in proposed_node_ids,
            "synthetic": bool(node.get("synthetic")),
        }
        for node in nodes
    ]
    table_edges = [
        {**edge, "proposed": _edge_key(edge) in proposed_edge_keys}
        for edge in edges
    ]
    return nodes, edges, table_nodes, table_edges


def _render_topology_graph_only(
    *,
    title: str,
    topology: Dict[str, Any],
    proposed_edge_keys: Set[Tuple[str, str, str]],
    proposed_node_ids: Set[str],
) -> None:
    nodes, edges, _, _ = _topology_display_bundle(topology, proposed_edge_keys, proposed_node_ids)
    _draw_topology_graph(
        nodes,
        edges,
        proposed_edge_keys,
        proposed_node_ids=proposed_node_ids,
        title=title,
    )


def _render_topology_panel(
    *,
    title: str,
    topology: Dict[str, Any],
    proposed_edge_keys: Set[Tuple[str, str, str]],
    proposed_node_ids: Set[str],
) -> None:
    _, _, table_nodes, table_edges = _topology_display_bundle(
        topology, proposed_edge_keys, proposed_node_ids
    )
    _render_topology_graph_only(
        title=title,
        topology=topology,
        proposed_edge_keys=proposed_edge_keys,
        proposed_node_ids=proposed_node_ids,
    )
    st.markdown("**Nodes**")
    _render_dataframe_or_empty(table_nodes, "No nodes.")
    st.markdown("**Edges**")
    _render_dataframe_or_empty(table_edges, "No edges.")


def _render_dataframe_or_empty(rows: List[Dict[str, Any]], empty_caption: str) -> None:
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.caption(empty_caption)


@dataclass
class TopologyProposalContext:
    proposal: Dict[str, Any]
    changes: List[Dict[str, Any]]
    baseline_topology: Dict[str, Any]
    proposed_topology: Dict[str, Any]
    delta_edge_keys: Set[Tuple[str, str, str]]
    delta_node_ids: Set[str]
    before_nodes: List[Dict[str, Any]]
    before_edges: List[Dict[str, Any]]
    after_nodes: List[Dict[str, Any]]
    after_edges: List[Dict[str, Any]]
    param_rows: List[Dict[str, Any]]


def _load_topology_proposal_context(
    run_dir: Path,
    design_state_rows: List[Dict[str, Any]],
) -> Optional[TopologyProposalContext]:
    proposal = _read_json(run_dir / "design_proposals.json")
    if not proposal:
        return None

    run_end_topology, run_end_parameters = _run_end_design_state(design_state_rows)
    baseline_topology = proposal.get("baseline_topology") or run_end_topology
    if not baseline_topology:
        return None

    changes = proposal.get("changes", [])
    if not isinstance(changes, list):
        changes = []
    proposed_topology, proposed_parameters = _apply_proposal_changes(
        baseline_topology,
        run_end_parameters,
        changes,
    )

    delta_edge_keys = _topology_edge_keys(proposed_topology) - _topology_edge_keys(baseline_topology)
    delta_node_ids = _topology_node_ids(proposed_topology) - _topology_node_ids(baseline_topology)

    _, _, before_nodes, before_edges = _topology_display_bundle(baseline_topology, set(), set())
    _, _, after_nodes, after_edges = _topology_display_bundle(
        proposed_topology,
        delta_edge_keys,
        delta_node_ids,
    )

    parameter_keys = sorted(
        set(run_end_parameters.keys())
        | set(proposed_parameters.keys())
        | {
            str((change.get("payload") or {}).get("key", ""))
            for change in changes
            if change.get("change_kind") == "set_parameter"
        }
        - {""}
    )
    param_rows: List[Dict[str, Any]] = []
    for key in parameter_keys:
        before_value = run_end_parameters.get(key)
        after_value = proposed_parameters.get(key)
        delta = None
        if isinstance(before_value, (int, float)) and isinstance(after_value, (int, float)):
            delta = round(after_value - before_value, 6)
        param_rows.append(
            {
                "parameter": key,
                "before": before_value,
                "after": after_value,
                "delta": delta,
                "proposed": before_value != after_value,
            }
        )

    return TopologyProposalContext(
        proposal=proposal,
        changes=changes,
        baseline_topology=baseline_topology,
        proposed_topology=proposed_topology,
        delta_edge_keys=delta_edge_keys,
        delta_node_ids=delta_node_ids,
        before_nodes=before_nodes,
        before_edges=before_edges,
        after_nodes=after_nodes,
        after_edges=after_edges,
        param_rows=param_rows,
    )


def _render_topology_proposal_blurb(ctx: Optional[TopologyProposalContext], *, missing: str) -> None:
    if ctx is None:
        st.info(missing)
        return
    if ctx.proposal.get("message"):
        st.markdown(f"**Proposal:** {ctx.proposal['message']}")
    if ctx.proposal.get("reasoning"):
        st.caption(ctx.proposal["reasoning"])


def _render_topology_proposal_metrics(ctx: Optional[TopologyProposalContext]) -> None:
    if ctx is None:
        return
    metric_cols = st.columns(3)
    with metric_cols[0]:
        st.metric("Proposed changes", len(ctx.changes))
    with metric_cols[1]:
        st.metric("New edges", len(ctx.delta_edge_keys))
    with metric_cols[2]:
        st.metric("New nodes", len(ctx.delta_node_ids))


def _render_topology_baseline_graph(ctx: TopologyProposalContext) -> None:
    _render_topology_graph_only(
        title="Run-end topology",
        topology=ctx.baseline_topology,
        proposed_edge_keys=set(),
        proposed_node_ids=set(),
    )


def _render_topology_proposed_graph(ctx: TopologyProposalContext) -> None:
    _render_topology_graph_only(
        title="Proposed topology",
        topology=ctx.proposed_topology,
        proposed_edge_keys=ctx.delta_edge_keys,
        proposed_node_ids=ctx.delta_node_ids,
    )


def _render_topology_proposal_body(ctx: Optional[TopologyProposalContext], *, missing: str) -> None:
    """Single-run view: before/after panels side by side."""
    if ctx is None:
        st.info(missing)
        return

    _render_topology_proposal_metrics(ctx)

    st.markdown("**Proposed change list**")
    _render_dataframe_or_empty(ctx.changes, "No proposed changes.")

    graph_cols = st.columns(2)
    with graph_cols[0]:
        st.markdown("**Before (run-end baseline)**")
        _render_topology_panel(
            title="Run-end topology",
            topology=ctx.baseline_topology,
            proposed_edge_keys=set(),
            proposed_node_ids=set(),
        )
    with graph_cols[1]:
        st.markdown("**After (if proposals applied)**")
        _render_topology_panel(
            title="Proposed topology",
            topology=ctx.proposed_topology,
            proposed_edge_keys=ctx.delta_edge_keys,
            proposed_node_ids=ctx.delta_node_ids,
        )

    if ctx.param_rows:
        st.markdown("**Design parameters (before vs proposed)**")
        _render_dataframe_or_empty(ctx.param_rows, "No parameter changes.")


def _render_topology_proposal_for_run(
    run_dir: Path,
    design_state_rows: List[Dict[str, Any]],
) -> None:
    ctx = _load_topology_proposal_context(run_dir, design_state_rows)
    st.caption(
        "Compare run-end topology (before proposals) with the topology if design_engineer "
        "changes were applied. Proposals are not applied during simulation."
    )
    _render_topology_proposal_blurb(
        ctx,
        missing="No design_proposals.json for this run.",
    )
    _render_topology_proposal_body(
        ctx,
        missing="No design_proposals.json for this run.",
    )
    if ctx is not None:
        baseline_legend = ", ".join(f"{kind}={color}" for kind, color in _EDGE_COLORS.items())
        st.caption(
            f"Baseline edges: {baseline_legend}. "
            f"Proposed additions: dashed {_DESIGN_EDGE_COLOR} (*)."
        )


def _render_dual_topology_proposal(primary: RunViewData, compare: RunViewData) -> None:
    """Align topology subsections across runs (row-by-row, not stacked columns)."""
    primary_ctx = _load_topology_proposal_context(primary.run_dir, primary.design_state)
    compare_ctx = _load_topology_proposal_context(compare.run_dir, compare.design_state)

    st.caption(
        "Compare run-end topology (before proposals) with the topology if design_engineer "
        "changes were applied. Proposals are not applied during simulation."
    )

    _render_paired_columns(
        lambda: st.markdown(f"**`{primary.run_name}`**"),
        lambda: st.markdown(f"**`{compare.run_name}`**"),
    )

    _render_paired_columns(
        lambda: _render_topology_proposal_blurb(
            primary_ctx,
            missing="No design_proposals.json for this run.",
        ),
        lambda: _render_topology_proposal_blurb(
            compare_ctx,
            missing="No design_proposals.json for this run.",
        ),
    )

    _render_paired_columns(
        lambda: _render_topology_proposal_metrics(primary_ctx),
        lambda: _render_topology_proposal_metrics(compare_ctx),
    )

    st.markdown("**Proposed change list**")
    _render_paired_columns(
        lambda: _render_dataframe_or_empty(
            primary_ctx.changes if primary_ctx else [],
            "No proposed changes.",
        ),
        lambda: _render_dataframe_or_empty(
            compare_ctx.changes if compare_ctx else [],
            "No proposed changes.",
        ),
    )

    st.markdown("**Before (run-end baseline)**")
    _render_paired_columns(
        lambda: _render_topology_baseline_graph(primary_ctx)
        if primary_ctx
        else st.info("No topology data."),
        lambda: _render_topology_baseline_graph(compare_ctx)
        if compare_ctx
        else st.info("No topology data."),
    )

    st.markdown("**Before — Nodes**")
    _render_paired_columns(
        lambda: _render_dataframe_or_empty(
            primary_ctx.before_nodes if primary_ctx else [],
            "No nodes.",
        ),
        lambda: _render_dataframe_or_empty(
            compare_ctx.before_nodes if compare_ctx else [],
            "No nodes.",
        ),
    )

    st.markdown("**Before — Edges**")
    _render_paired_columns(
        lambda: _render_dataframe_or_empty(
            primary_ctx.before_edges if primary_ctx else [],
            "No edges.",
        ),
        lambda: _render_dataframe_or_empty(
            compare_ctx.before_edges if compare_ctx else [],
            "No edges.",
        ),
    )

    st.markdown("**After (if proposals applied)**")
    _render_paired_columns(
        lambda: _render_topology_proposed_graph(primary_ctx)
        if primary_ctx
        else st.info("No topology data."),
        lambda: _render_topology_proposed_graph(compare_ctx)
        if compare_ctx
        else st.info("No topology data."),
    )

    st.markdown("**After — Nodes**")
    _render_paired_columns(
        lambda: _render_dataframe_or_empty(
            primary_ctx.after_nodes if primary_ctx else [],
            "No nodes.",
        ),
        lambda: _render_dataframe_or_empty(
            compare_ctx.after_nodes if compare_ctx else [],
            "No nodes.",
        ),
    )

    st.markdown("**After — Edges**")
    _render_paired_columns(
        lambda: _render_dataframe_or_empty(
            primary_ctx.after_edges if primary_ctx else [],
            "No edges.",
        ),
        lambda: _render_dataframe_or_empty(
            compare_ctx.after_edges if compare_ctx else [],
            "No edges.",
        ),
    )

    if (primary_ctx and primary_ctx.param_rows) or (compare_ctx and compare_ctx.param_rows):
        st.markdown("**Design parameters (before vs proposed)**")
        _render_paired_columns(
            lambda: _render_dataframe_or_empty(
                primary_ctx.param_rows if primary_ctx else [],
                "No parameter changes.",
            ),
            lambda: _render_dataframe_or_empty(
                compare_ctx.param_rows if compare_ctx else [],
                "No parameter changes.",
            ),
        )

    baseline_legend = ", ".join(f"{kind}={color}" for kind, color in _EDGE_COLORS.items())
    st.caption(
        f"Baseline edges: {baseline_legend}. "
        f"Proposed additions: dashed {_DESIGN_EDGE_COLOR} (*)."
    )


def _render_topology_proposal_comparison(
    run_dir: Path,
    design_state_rows: List[Dict[str, Any]],
) -> None:
    st.subheader("Design topology — proposal comparison")
    _render_topology_proposal_for_run(run_dir, design_state_rows)


def _render_summary(summary: Dict[str, Any]) -> None:
    st.subheader("Run summary")
    if not summary:
        st.warning("summary.json not found.")
        return
    st.json(summary, expanded=False)


def _render_health_card(
    telemetry_rows: List[Dict[str, Any]],
    health_rows: List[Dict[str, Any]],
    eps_rows: List[Dict[str, Any]],
    current_step: int,
) -> None:
    current_telemetry = select_row_for_step(telemetry_rows, current_step)
    current_health = select_row_for_step(health_rows, current_step)
    current_eps = select_row_for_step(eps_rows, current_step)

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        st.metric("Step", current_step)
    with col2:
        st.metric("CO2 ppm", f"{(current_telemetry or {}).get('co2_ppm', '-')}")
    with col3:
        st.metric("Power margin W", f"{(current_telemetry or {}).get('power_margin_w', '-')}")
    with col4:
        st.metric("Overall health", (current_health or {}).get("overall", "-"))
    with col5:
        st.metric("EPS support W", f"{(current_telemetry or {}).get('eps_support_w', 0.0)}")
    with col6:
        st.metric("BCDU mode", (current_eps or {}).get("bcdu_mode", "-"))


def _summary_agents_mode(summary: Dict[str, Any]) -> str:
    return str(summary.get("agents_mode", "—"))


def _render_run_identity_cards(
    primary_name: str,
    primary_summary: Dict[str, Any],
    compare_name: str,
    compare_summary: Dict[str, Any],
) -> None:
    left_col, right_col = st.columns(2)
    with left_col:
        st.markdown("##### Primary run")
        st.markdown(f"`{primary_name}`")
        st.caption(f"agents.mode: `{_summary_agents_mode(primary_summary)}`")
    with right_col:
        st.markdown("##### Compare run")
        st.markdown(f"`{compare_name}`")
        st.caption(f"agents.mode: `{_summary_agents_mode(compare_summary)}`")


def _render_metric_comparison_table(
    primary_name: str,
    compare_name: str,
    metrics: List[Tuple[str, Any, Any]],
) -> None:
    """One row per metric; primary and compare values in named columns."""
    rows: List[Dict[str, Any]] = []
    for label, primary_val, compare_val in metrics:
        row: Dict[str, Any] = {
            "Metric": label,
            primary_name: primary_val,
            compare_name: compare_val,
        }
        if isinstance(primary_val, (int, float)) and isinstance(compare_val, (int, float)):
            row["Δ (primary − compare)"] = round(primary_val - compare_val, 6)
        else:
            row["Δ (primary − compare)"] = None
        rows.append(row)
    st.dataframe(rows, use_container_width=True, hide_index=True)


def _extract_recovery_commands(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for event in events:
        if event.get("kind") != "/eclss/events/recovery_applied":
            continue
        command = event.get("command") or {}
        rows.append(
            {
                "step": event.get("step"),
                "kind": command.get("kind"),
                "value": command.get("value"),
                "issued_by": command.get("issued_by"),
                "message": event.get("message"),
            }
        )
    return rows


def _render_power_recovery_comparison(
    primary_name: str,
    primary_events: List[Dict[str, Any]],
    primary_summary: Dict[str, Any],
    compare_name: str,
    compare_events: List[Dict[str, Any]],
    compare_summary: Dict[str, Any],
) -> None:
    st.markdown("**Power & recovery**")
    p_eps = len(
        [r for r in _extract_recovery_commands(primary_events) if r["kind"] == "request_eps_boost"]
    )
    c_eps = len(
        [r for r in _extract_recovery_commands(compare_events) if r["kind"] == "request_eps_boost"]
    )
    _render_metric_comparison_table(
        primary_name,
        compare_name,
        [
            (
                "EPS boost applied (step)",
                primary_summary.get("eps_boost_applied_step", "—"),
                compare_summary.get("eps_boost_applied_step", "—"),
            ),
            (
                "Min power margin (W)",
                primary_summary.get("min_power_margin_w", "—"),
                compare_summary.get("min_power_margin_w", "—"),
            ),
            (
                "Power recovered above critical (step)",
                primary_summary.get("power_recovered_above_critical_step", "—"),
                compare_summary.get("power_recovered_above_critical_step", "—"),
            ),
            ("EPS boost command count", p_eps, c_eps),
        ],
    )

    st.markdown("**Recovery command log**")
    _render_paired_columns(
        lambda: (
            st.markdown(f"**Primary — `{primary_name}`**"),
            _render_dataframe_or_empty(
                _extract_recovery_commands(primary_events),
                "No recovery events.",
            ),
        ),
        lambda: (
            st.markdown(f"**Compare — `{compare_name}`**"),
            _render_dataframe_or_empty(
                _extract_recovery_commands(compare_events),
                "No recovery events.",
            ),
        ),
    )


def _extract_final_parameters(design_state_rows: List[Dict[str, Any]]) -> Dict[str, float]:
    if not design_state_rows:
        return {}
    return dict(design_state_rows[-1].get("parameters", {}))


def _max_telemetry_step(telemetry: List[Dict[str, Any]]) -> int:
    return max((int(r["step"]) for r in telemetry), default=1)


@dataclass
class RunViewData:
    run_dir: Path
    run_name: str
    telemetry: List[Dict[str, Any]]
    eps_telemetry: List[Dict[str, Any]]
    health: List[Dict[str, Any]]
    messages: List[Dict[str, Any]]
    events: List[Dict[str, Any]]
    provenance: List[Dict[str, Any]]
    design_state: List[Dict[str, Any]]
    summary: Dict[str, Any]


def _render_paired_columns(
    render_primary: Callable[[], None],
    render_compare: Callable[[], None],
) -> None:
    """Render two panels on one row so the next section aligns across runs."""
    left_col, right_col = st.columns(2)
    with left_col:
        render_primary()
    with right_col:
        render_compare()


def _render_dual_run_views(primary: RunViewData, compare: RunViewData, current_step: int) -> None:
    """Section-aligned side-by-side layout (avoids column height drift)."""
    st.subheader("Runs side by side")

    _render_paired_columns(
        lambda: (
            st.markdown(f"**`{primary.run_name}`**"),
            st.caption(f"`{primary.run_dir}`"),
        ),
        lambda: (
            st.markdown(f"**`{compare.run_name}`**"),
            st.caption(f"`{compare.run_dir}`"),
        ),
    )

    if ssos_views.is_ssos_eclss_loop(primary.summary):
        _render_paired_columns(
            lambda: ssos_views.render_ssos_health_card(
                primary.telemetry, primary.health, current_step
            ),
            lambda: ssos_views.render_ssos_health_card(
                compare.telemetry, compare.health, current_step
            ),
        )
        _render_paired_columns(
            lambda: ssos_views.render_ssos_storage_plot(
                primary.telemetry, highlight_step=current_step
            ),
            lambda: ssos_views.render_ssos_storage_plot(
                compare.telemetry, highlight_step=current_step
            ),
        )
    else:
        _render_paired_columns(
            lambda: _render_health_card(
                primary.telemetry, primary.health, primary.eps_telemetry, current_step
            ),
            lambda: _render_health_card(
                compare.telemetry, compare.health, compare.eps_telemetry, current_step
            ),
        )

        _render_paired_columns(
            lambda: _line_plot(primary.telemetry, primary.eps_telemetry, current_step),
            lambda: _line_plot(compare.telemetry, compare.eps_telemetry, current_step),
        )

    if not ssos_views.is_ssos_eclss_loop(primary.summary):
        st.subheader("Design topology — proposal comparison")
        _render_dual_topology_proposal(primary, compare)

    st.subheader(f"Step {current_step} detail")
    primary_messages = _select_rows_at_step(primary.messages, current_step)
    compare_messages = _select_rows_at_step(compare.messages, current_step)
    primary_events = _select_rows_at_step(primary.events, current_step)
    compare_events = _select_rows_at_step(compare.events, current_step)
    primary_provenance = _select_rows_at_step(primary.provenance, current_step)
    compare_provenance = _select_rows_at_step(compare.provenance, current_step)

    st.markdown("**Messages**")
    _render_paired_columns(
        lambda: _render_dataframe_or_empty(primary_messages, "No messages at this step."),
        lambda: _render_dataframe_or_empty(compare_messages, "No messages at this step."),
    )

    st.markdown("**Events**")
    _render_paired_columns(
        lambda: _render_dataframe_or_empty(primary_events, "No events at this step."),
        lambda: _render_dataframe_or_empty(compare_events, "No events at this step."),
    )

    st.markdown("**Provenance**")
    _render_paired_columns(
        lambda: _render_dataframe_or_empty(primary_provenance, "No provenance records at this step."),
        lambda: _render_dataframe_or_empty(compare_provenance, "No provenance records at this step."),
    )

    st.subheader("Run summary")
    _render_paired_columns(
        lambda: st.json(primary.summary, expanded=False) if primary.summary else st.warning("summary.json not found."),
        lambda: st.json(compare.summary, expanded=False) if compare.summary else st.warning("summary.json not found."),
    )


def _render_run_detail_view(run: RunViewData, current_step: int) -> None:
    """Health, trajectories, topology, step tables, and summary for a single run."""
    st.markdown(f"**`{run.run_name}`**")
    st.caption(f"`{run.run_dir}`")
    if ssos_views.is_ssos_eclss_loop(run.summary):
        ssos_views.render_ssos_summary_highlights(run.summary)
        ssos_views.render_ssos_health_card(run.telemetry, run.health, current_step)
        ssos_views.render_ssos_storage_plot(run.telemetry, highlight_step=current_step)
        st.subheader("Operational commands")
        ssos_views.render_ssos_operational_timeline(run.events)
        ssos_views.render_ssos_design_proposals(run.run_dir)
        _render_step_tables(run.messages, run.events, run.provenance, current_step)
        _render_summary(run.summary)
        return
    _render_health_card(run.telemetry, run.health, run.eps_telemetry, current_step)
    _line_plot(run.telemetry, run.eps_telemetry, current_step)
    _render_topology_proposal_comparison(run.run_dir, run.design_state)
    _render_step_tables(run.messages, run.events, run.provenance, current_step)
    _render_summary(run.summary)


def _render_run_comparison(
    primary_name: str,
    primary_summary: Dict[str, Any],
    primary_design_state: List[Dict[str, Any]],
    primary_provenance: List[Dict[str, Any]],
    compare_name: str,
    compare_summary: Dict[str, Any],
    compare_design_state: List[Dict[str, Any]],
    compare_provenance: List[Dict[str, Any]],
    primary_events: List[Dict[str, Any]],
    compare_events: List[Dict[str, Any]],
) -> None:
    st.subheader("Run comparison")
    st.caption(
        "Each metric lists Primary and Compare in separate columns "
        "(sidebar selections). Δ = primary − compare."
    )
    _render_run_identity_cards(primary_name, primary_summary, compare_name, compare_summary)

    st.markdown("**Run outcome**")
    _render_metric_comparison_table(
        primary_name,
        compare_name,
        [
            (
                "Design changes (count)",
                primary_summary.get("design_change_count", 0),
                compare_summary.get("design_change_count", 0),
            ),
            (
                "Provenance records (count)",
                len(primary_provenance),
                len(compare_provenance),
            ),
            (
                "Final CO2 (ppm)",
                primary_summary.get("final_co2_ppm", "—"),
                compare_summary.get("final_co2_ppm", "—"),
            ),
            (
                "Final power margin (W)",
                primary_summary.get("final_power_margin_w", "—"),
                compare_summary.get("final_power_margin_w", "—"),
            ),
            (
                "Final step",
                primary_summary.get("final_step", "—"),
                compare_summary.get("final_step", "—"),
            ),
            (
                "Message count",
                primary_summary.get("message_count", "—"),
                compare_summary.get("message_count", "—"),
            ),
        ],
    )

    _render_power_recovery_comparison(
        primary_name,
        primary_events,
        primary_summary,
        compare_name,
        compare_events,
        compare_summary,
    )

    primary_params = _extract_final_parameters(primary_design_state)
    compare_params = _extract_final_parameters(compare_design_state)
    keys = sorted(set(primary_params.keys()) | set(compare_params.keys()))
    diff_rows: List[Dict[str, Any]] = []
    for key in keys:
        a = primary_params.get(key)
        b = compare_params.get(key)
        delta = None
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            delta = round(a - b, 6)
        diff_rows.append(
            {
                "parameter": key,
                f"{primary_name}": a,
                f"{compare_name}": b,
                "delta_primary_minus_compare": delta,
            }
        )
    st.markdown("**Final design parameters**")
    st.caption(
        f"End-of-run simulator parameters. "
        f"Columns `{primary_name}` and `{compare_name}` match the runs above."
    )
    st.dataframe(diff_rows, use_container_width=True, hide_index=True)

    st.markdown("**Full provenance log**")
    _render_paired_columns(
        lambda: (
            st.markdown(f"**Primary — `{primary_name}`**"),
            _render_dataframe_or_empty(primary_provenance, "No provenance records."),
        ),
        lambda: (
            st.markdown(f"**Compare — `{compare_name}`**"),
            _render_dataframe_or_empty(compare_provenance, "No provenance records."),
        ),
    )


def main() -> None:
    st.set_page_config(page_title="ECLSS Day6 Dashboard", layout="wide")
    st.title("ECLSS Resilience Dashboard")

    runs = _list_runs()
    if not runs:
        st.error(f"No run outputs found under {RESULTS_ROOT}")
        return

    run_map = {run.name: run for run in runs}
    run_names = list(run_map.keys())
    selected_run_name = st.sidebar.selectbox("Run", options=run_names, index=len(run_names) - 1)
    run_dir = run_map[selected_run_name]

    compare_enabled = st.sidebar.checkbox("Compare with another run", value=False)
    compare_run_name = None
    compare_run_dir = None
    if compare_enabled:
        compare_candidates = [name for name in run_names if name != selected_run_name]
        if compare_candidates:
            compare_run_name = st.sidebar.selectbox("Compare run", options=compare_candidates, index=0)
            compare_run_dir = run_map[compare_run_name]

    telemetry = _read_jsonl(run_dir / "telemetry.jsonl")
    eps_telemetry = _read_jsonl(run_dir / "eps_telemetry.jsonl")
    health = _read_jsonl(run_dir / "health_metrics.jsonl")
    messages = _read_jsonl(run_dir / "messages.jsonl")
    events = _read_jsonl(run_dir / "events.jsonl")
    provenance = _read_jsonl(run_dir / "provenance.jsonl")
    design_state = _read_jsonl(run_dir / "design_state.jsonl")
    summary = _read_json(run_dir / "summary.json")

    compare_telemetry: List[Dict[str, Any]] = []
    compare_eps_telemetry: List[Dict[str, Any]] = []
    compare_health: List[Dict[str, Any]] = []
    compare_messages: List[Dict[str, Any]] = []
    compare_events: List[Dict[str, Any]] = []
    compare_provenance: List[Dict[str, Any]] = []
    compare_design_state: List[Dict[str, Any]] = []
    compare_summary: Dict[str, Any] = {}
    if compare_run_dir is not None:
        compare_telemetry = _read_jsonl(compare_run_dir / "telemetry.jsonl")
        compare_eps_telemetry = _read_jsonl(compare_run_dir / "eps_telemetry.jsonl")
        compare_health = _read_jsonl(compare_run_dir / "health_metrics.jsonl")
        compare_messages = _read_jsonl(compare_run_dir / "messages.jsonl")
        compare_events = _read_jsonl(compare_run_dir / "events.jsonl")
        compare_provenance = _read_jsonl(compare_run_dir / "provenance.jsonl")
        compare_design_state = _read_jsonl(compare_run_dir / "design_state.jsonl")
        compare_summary = _read_json(compare_run_dir / "summary.json")

    max_step = _max_telemetry_step(telemetry)
    if max_step < 1 and telemetry:
        max_step = max(int(r.get("step", 0)) for r in telemetry)
    if max_step < 1:
        max_step = 1
    if compare_run_name and compare_telemetry:
        max_step = min(max_step, _max_telemetry_step(compare_telemetry))
    overview_step = st.sidebar.slider(
        "Step (overview)",
        min_value=1,
        max_value=max_step,
        value=max_step,
    )

    primary_run = RunViewData(
        run_dir=run_dir,
        run_name=selected_run_name,
        telemetry=telemetry,
        eps_telemetry=eps_telemetry,
        health=health,
        messages=messages,
        events=events,
        provenance=provenance,
        design_state=design_state,
        summary=summary,
    )

    view_mode = st.radio(
        "View",
        options=["Overview", "Step replay"],
        horizontal=True,
        key="dashboard_view_mode",
    )

    if view_mode == "Step replay":
        _render_run_replay_view(primary_run)
    elif compare_run_name and compare_run_dir:
        compare_run = RunViewData(
            run_dir=compare_run_dir,
            run_name=compare_run_name,
            telemetry=compare_telemetry,
            eps_telemetry=compare_eps_telemetry,
            health=compare_health,
            messages=compare_messages,
            events=compare_events,
            provenance=compare_provenance,
            design_state=compare_design_state,
            summary=compare_summary,
        )
        _render_dual_run_views(primary_run, compare_run, overview_step)
        st.divider()
        _render_run_comparison(
            primary_name=selected_run_name,
            primary_summary=summary,
            primary_design_state=design_state,
            primary_provenance=provenance,
            compare_name=compare_run_name,
            compare_summary=compare_summary,
            compare_design_state=compare_design_state,
            compare_provenance=compare_provenance,
            primary_events=events,
            compare_events=compare_events,
        )
    else:
        _render_run_detail_view(primary_run, overview_step)


if __name__ == "__main__":
    main()
