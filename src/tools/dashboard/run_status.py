"""Pure extractors for anomaly / operator / design-driver panels (run artifacts only)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from tools.dashboard.jsonl_rows import select_row_for_step, series_by_step
from tools.dashboard.ssos_flow import plant_sim_topic, thresholds_from_summary

_FAILURE_FLAGS = (
    ("ars_failure_enabled", "ARS", "air revitalisation subsystem"),
    ("ogs_failure_enabled", "OGS", "oxygen generation subsystem"),
    ("wrs_failure_enabled", "WRS", "water recovery subsystem"),
)

_HEALTH_BAND_CANDIDATES = (
    ("overall", "overall health"),
    ("co2_status", "CO2 band"),
    ("o2_status", "O2 band"),
    ("water_status", "water band"),
    ("power_status", "power band"),
)

_STRESS_STATUSES = frozenset({"warning", "critical"})
_STATUS_RANK = {"safe": 0, "unknown": 1, "warning": 2, "critical": 3}


def _health_bands_for_rows(health_rows: Sequence[Dict[str, Any]]) -> List[Tuple[str, str]]:
    """Return health bands present in the run (scrubber: power; SSOS: O2/water)."""
    bands: List[Tuple[str, str]] = []
    for band_key, label in _HEALTH_BAND_CANDIDATES:
        if band_key == "overall":
            bands.append((band_key, label))
            continue
        if any(str(row.get(band_key) or "").strip() for row in health_rows):
            bands.append((band_key, label))
    return bands


def _failure_flags_for_telemetry(
    telemetry_rows: Sequence[Dict[str, Any]],
) -> List[Tuple[str, str, str]]:
    """Return SSOS failure flags that actually appear in telemetry."""
    keys_present = {
        flag_key
        for row in telemetry_rows
        for flag_key, _, _ in _FAILURE_FLAGS
        if flag_key in row
    }
    return [item for item in _FAILURE_FLAGS if item[0] in keys_present]


def _fmt_num(value: Any, digits: int = 3) -> Optional[str]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return f"{float(value):.{digits}g}"


def _status_rank(status: Any) -> int:
    return _STATUS_RANK.get(str(status or "").lower(), -1)


def _worst_health_row(rows: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Prefer the most stressed health row when a step has pre/post_ops duplicates."""
    if not rows:
        return None
    return max(
        rows,
        key=lambda row: (
            _status_rank(row.get("overall")),
            _status_rank(row.get("co2_status")),
            _status_rank(row.get("o2_status")),
            _status_rank(row.get("water_status")),
            _status_rank(row.get("power_status")),
            0 if row.get("post_ops") is True else 1,
        ),
    )


def _health_series_worst(health_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[int, List[Dict[str, Any]]] = {}
    for row in health_rows:
        if "step" not in row:
            continue
        grouped.setdefault(int(row["step"]), []).append(row)
    series: List[Dict[str, Any]] = []
    for step in sorted(grouped):
        worst = _worst_health_row(grouped[step])
        if worst is not None:
            series.append(worst)
    return series


def _episode_onset(
    series: Sequence[Dict[str, Any]],
    *,
    step: int,
    is_active,
) -> Optional[int]:
    """Earliest step of the active episode ending at ``step``.

    Walks backward only through adjacent recorded steps (``prior == onset - 1``).
    Gaps in the series break the episode so elapsed is not inflated across missing steps.
    """
    by_step = {int(row["step"]): row for row in series if "step" in row}
    if step not in by_step or not is_active(by_step[step]):
        return None
    onset = step
    while True:
        prior = onset - 1
        if prior not in by_step or not is_active(by_step[prior]):
            break
        onset = prior
    return onset


def _plant_sim_shortfall_series(telemetry_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    series: List[Dict[str, Any]] = []
    for row in series_by_step(telemetry_rows):
        topic = plant_sim_topic(row)
        if topic is None:
            continue
        series.append({"step": int(row["step"]), **topic})
    return series


def _ledger_increased_at(
    current: Dict[str, Any],
    prior: Optional[Dict[str, Any]],
    key: str,
) -> bool:
    cur_val = current.get(key)
    if not isinstance(cur_val, (int, float)) or float(cur_val) <= 0:
        return False
    if prior is None:
        return True
    prev_val = prior.get(key)
    if not isinstance(prev_val, (int, float)):
        return True
    return float(cur_val) > float(prev_val)


def _crew_shortfall_active(series: Sequence[Dict[str, Any]], step: int) -> bool:
    by_step = {int(row["step"]): row for row in series if "step" in row}
    if step not in by_step:
        return False
    ordered = sorted(by_step)
    idx = ordered.index(step)
    current = by_step[step]
    prior = by_step[ordered[idx - 1]] if idx > 0 else None
    return _ledger_increased_at(current, prior, "total_o2_shortfall_kg") or _ledger_increased_at(
        current, prior, "total_water_shortfall_l"
    )


def _crew_shortfall_ledger_positive(series: Sequence[Dict[str, Any]], step: int) -> bool:
    by_step = {int(row["step"]): row for row in series if "step" in row}
    if step not in by_step:
        return False
    current = by_step[step]
    for key in ("total_o2_shortfall_kg", "total_water_shortfall_l"):
        value = current.get(key)
        if isinstance(value, (int, float)) and float(value) > 0:
            return True
    return False


def extract_anomaly_status(
    *,
    step: int,
    telemetry_rows: List[Dict[str, Any]],
    health_rows: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
    summary: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Active anomaly / stress rows at ``step`` derived only from run artifacts."""
    rows: List[Dict[str, Any]] = []
    tel_series = series_by_step(telemetry_rows)
    health_series = _health_series_worst(health_rows)
    current_tel = select_row_for_step(telemetry_rows, step) or {}
    step_health_rows = [r for r in health_rows if int(r.get("step", -1)) == int(step)]
    current_health = _worst_health_row(step_health_rows) or {}
    thresholds = thresholds_from_summary(summary or {}) or {}

    for flag_key, short_name, where in _failure_flags_for_telemetry(telemetry_rows):
        onset = _episode_onset(
            tel_series,
            step=step,
            is_active=lambda row, key=flag_key: bool(row.get(key)),
        )
        if onset is None:
            continue
        rows.append(
            {
                "type": "subsystem_failure",
                "name": short_name,
                "where": where,
                "severity": "failure_enabled",
                "onset_step": onset,
                "elapsed_steps": int(step) - int(onset),
                "telemetry": f"{flag_key}=true",
            }
        )

    for band_key, where in _health_bands_for_rows(health_rows):
        status = str(current_health.get(band_key, "") or "").lower()
        if status not in _STRESS_STATUSES:
            continue
        onset = _episode_onset(
            health_series,
            step=step,
            is_active=lambda row, key=band_key: str(row.get(key, "") or "").lower()
            in _STRESS_STATUSES,
        )
        if onset is None:
            continue
        impact_parts: List[str] = [f"{band_key}={status}"]
        if band_key in {"co2_status", "overall"}:
            co2 = current_tel.get("co2_storage_kg")
            co2_s = _fmt_num(co2)
            if co2_s is not None:
                impact_parts.append(f"co2_storage_kg={co2_s}")
            for thr_key in ("co2_storage_high_kg", "co2_storage_critical_kg"):
                thr = thresholds.get(thr_key)
                thr_s = _fmt_num(thr)
                if thr_s is not None:
                    impact_parts.append(f"{thr_key}={thr_s}")
            ppm = current_tel.get("co2_ppm")
            ppm_s = _fmt_num(ppm)
            if ppm_s is not None:
                impact_parts.append(f"co2_ppm={ppm_s}")
        if band_key in {"o2_status", "overall"}:
            o2 = current_tel.get("o2_storage_kg")
            o2_s = _fmt_num(o2)
            if o2_s is not None:
                impact_parts.append(f"o2_storage_kg={o2_s}")
            for thr_key in ("o2_storage_low_kg", "o2_storage_critical_kg"):
                thr = thresholds.get(thr_key)
                thr_s = _fmt_num(thr)
                if thr_s is not None:
                    impact_parts.append(f"{thr_key}={thr_s}")
        if band_key in {"water_status", "overall"}:
            water = current_tel.get("product_water_reserve_l")
            water_s = _fmt_num(water)
            if water_s is not None:
                impact_parts.append(f"product_water_reserve_l={water_s}")
            for thr_key in ("product_water_low_l", "product_water_critical_l"):
                thr = thresholds.get(thr_key)
                thr_s = _fmt_num(thr)
                if thr_s is not None:
                    impact_parts.append(f"{thr_key}={thr_s}")
        if band_key in {"power_status", "overall"}:
            power_margin = current_tel.get("power_margin_w")
            power_s = _fmt_num(power_margin)
            if power_s is not None:
                impact_parts.append(f"power_margin_w={power_s}")
        rows.append(
            {
                "type": "health_stress",
                "name": band_key,
                "where": where,
                "severity": status,
                "onset_step": onset,
                "elapsed_steps": int(step) - int(onset),
                "telemetry": "; ".join(impact_parts),
            }
        )

    flags = current_tel.get("anomaly_flags") or []
    if isinstance(flags, list) and flags:
        for flag in flags:
            name = str(flag)

            def _flag_active(row: Dict[str, Any], flag_name: str = name) -> bool:
                row_flags = row.get("anomaly_flags") or []
                return isinstance(row_flags, list) and flag_name in row_flags

            onset = _episode_onset(tel_series, step=step, is_active=_flag_active)
            if onset is None:
                onset = step
            impact_parts = [f"anomaly_flags={name}"]
            eff = current_tel.get("scrubber_efficiency")
            eff_s = _fmt_num(eff)
            if eff_s is not None:
                impact_parts.append(f"scrubber_efficiency={eff_s}")
            ppm = current_tel.get("co2_ppm")
            ppm_s = _fmt_num(ppm)
            if ppm_s is not None:
                impact_parts.append(f"co2_ppm={ppm_s}")
            rows.append(
                {
                    "type": "scrubber_anomaly",
                    "name": name,
                    "where": "scrubber / cabin atmosphere",
                    "severity": "active",
                    "onset_step": onset,
                    "elapsed_steps": int(step) - int(onset),
                    "telemetry": "; ".join(impact_parts),
                }
            )

    # Scheduled anomaly not yet reflected in flags (pre-onset or missing flags).
    for event in events:
        if event.get("kind") != "anomaly_injected":
            continue
        spec = event.get("spec") or {}
        start = spec.get("start_step")
        if not isinstance(start, int) or step < start:
            continue
        name = str(spec.get("name") or "anomaly")
        if any(r.get("name") == name and r.get("type") == "scrubber_anomaly" for r in rows):
            continue
        impact_parts = [f"scheduled_from_step={start}"]
        eff = current_tel.get("scrubber_efficiency")
        eff_s = _fmt_num(eff)
        if eff_s is not None:
            impact_parts.append(f"scrubber_efficiency={eff_s}")
        rows.append(
            {
                "type": "scrubber_anomaly",
                "name": name,
                "where": "scrubber / cabin atmosphere",
                "severity": "scheduled_or_active",
                "onset_step": start,
                "elapsed_steps": int(step) - int(start),
                "telemetry": "; ".join(impact_parts),
            }
        )

    shortfall_series = _plant_sim_shortfall_series(telemetry_rows)
    if shortfall_series and _crew_shortfall_active(shortfall_series, step):
        current_topic = next(row for row in shortfall_series if int(row["step"]) == int(step))
        shortfall_bits: List[str] = []
        o2_short = current_topic.get("total_o2_shortfall_kg")
        water_short = current_topic.get("total_water_shortfall_l")
        if isinstance(o2_short, (int, float)) and float(o2_short) > 0:
            shortfall_bits.append(f"total_o2_shortfall_kg={_fmt_num(o2_short)}")
        if isinstance(water_short, (int, float)) and float(water_short) > 0:
            shortfall_bits.append(f"total_water_shortfall_l={_fmt_num(water_short)}")
        onset = _episode_onset(
            shortfall_series,
            step=step,
            is_active=lambda row: _crew_shortfall_ledger_positive(
                shortfall_series, int(row["step"])
            ),
        )
        if onset is None:
            onset = step
        rows.append(
            {
                "type": "plant_sim_shortfall",
                "name": "crew_shortfall",
                "where": "plant_sim crew demand",
                "severity": "shortfall",
                "onset_step": onset,
                "elapsed_steps": int(step) - int(onset),
                "telemetry": "; ".join(shortfall_bits),
            }
        )

    return rows


def extract_operator_step(
    *,
    step: int,
    messages: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
    summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Per-step operator actions and thoughts from messages + operational events."""
    step_messages = [
        {
            "from_role": row.get("from_role"),
            "to_role": row.get("to_role"),
            "message_type": row.get("message_type"),
            "decision_source": row.get("decision_source"),
            "deliberation_phase": row.get("deliberation_phase"),
            "message": row.get("message"),
            "reasoning": row.get("reasoning"),
        }
        for row in messages
        if int(row.get("step", -1)) == int(step)
    ]
    ops: List[Dict[str, Any]] = []
    for event in events:
        if int(event.get("step", -1)) != int(step):
            continue
        kind = str(event.get("kind") or "")
        if "operational" not in kind and "recovery" not in kind:
            continue
        cmd = event.get("command") or {}
        result = event.get("result") if isinstance(event.get("result"), dict) else {}
        ops.append(
            {
                "event_kind": kind,
                "command_kind": cmd.get("kind"),
                "issued_by": cmd.get("issued_by"),
                "success": event.get("success", result.get("success")),
                "details": result.get("details") or event.get("details"),
                "message": event.get("message") or result.get("message"),
            }
        )
    return {
        "step": step,
        "agents_mode": (summary or {}).get("agents_mode"),
        "messages": step_messages,
        "operations": ops,
    }


def extract_design_drivers(
    proposals: Dict[str, Any],
    summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Observation / incident text that drove design proposals (no invented fields)."""
    summary = summary or {}
    observations: List[str] = []
    for key in (
        "peak_co2_storage_kg",
        "final_co2_storage_kg",
        "min_o2_storage_kg",
        "final_o2_storage_kg",
        "final_product_water_reserve_l",
        "ars_invoked_step",
        "ogs_invoked_step",
    ):
        if key in summary and summary.get(key) is not None:
            observations.append(f"{key}={summary.get(key)}")
    final_health = summary.get("final_health")
    if isinstance(final_health, dict) and final_health:
        parts = [f"{k}={v}" for k, v in final_health.items() if v is not None]
        if parts:
            observations.append("final_health: " + ", ".join(parts))

    change_whys: List[str] = []
    for change in proposals.get("changes") or []:
        if not isinstance(change, dict):
            continue
        why = change.get("why")
        if why:
            change_whys.append(str(why))

    drivers: Dict[str, Any] = {
        "proposed_by": proposals.get("proposed_by"),
        "decision_source": proposals.get("decision_source"),
        "change_count": len(proposals.get("changes") or []),
    }
    if proposals.get("message") is not None:
        drivers["message"] = proposals.get("message")
    if proposals.get("reasoning") is not None:
        drivers["reasoning"] = proposals.get("reasoning")
    if change_whys:
        drivers["change_whys"] = change_whys
    if observations:
        drivers["summary_observations"] = observations
    return drivers


def _contiguous_segments(
    series: Sequence[Tuple[int, Optional[str]]],
) -> List[Dict[str, Any]]:
    """Merge equal states into [start_step, end_step) segments.

    Only adjacent recorded steps (``step - prev_step == 1``) stay in one segment;
    gaps split segments even when the state value matches on both sides.
    """
    segments: List[Dict[str, Any]] = []
    if not series:
        return segments
    start_step, current = series[0]
    prev_step = start_step
    for step, value in series[1:]:
        gap = int(step) - int(prev_step) > 1
        if value != current or gap:
            if current is not None:
                segments.append(
                    {
                        "start_step": int(start_step),
                        "end_step": int(prev_step) + 1,
                        "state": str(current),
                    }
                )
            start_step, current = step, value
        prev_step = step
    if current is not None:
        segments.append(
            {
                "start_step": int(start_step),
                "end_step": int(prev_step) + 1,
                "state": str(current),
            }
        )
    return segments


def build_status_timeline_lanes(
    health_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Health-band state timeline lanes for Overview (Grafana-style state history)."""
    series = series_by_step(health_rows)
    lanes: List[Dict[str, Any]] = []
    for band_key, label in _health_bands_for_rows(health_rows):
        points = [
            (int(row["step"]), str(row.get(band_key) or "").lower() or None)
            for row in series
        ]
        # Normalize empty to None (gap).
        points = [(step, state if state else None) for step, state in points]
        lanes.append(
            {
                "lane": label,
                "key": band_key,
                "segments": _contiguous_segments(points),
            }
        )
    return lanes


def build_anomaly_timeline_lanes(
    telemetry_rows: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Subsystem failure / scrubber anomaly lanes across the full run."""
    tel_series = series_by_step(telemetry_rows)
    lanes: List[Dict[str, Any]] = []

    for flag_key, short_name, _where in _failure_flags_for_telemetry(telemetry_rows):
        points = [
            (
                int(row["step"]),
                "failure" if bool(row.get(flag_key)) else "ok",
            )
            for row in tel_series
        ]
        lanes.append(
            {
                "lane": f"{short_name} failure",
                "key": flag_key,
                "segments": _contiguous_segments(points),
            }
        )

    # Collect scrubber anomaly flag names observed in the run.
    flag_names: List[str] = []
    seen: set[str] = set()
    for row in tel_series:
        flags = row.get("anomaly_flags") or []
        if not isinstance(flags, list):
            continue
        for flag in flags:
            name = str(flag)
            if name and name not in seen:
                seen.add(name)
                flag_names.append(name)
    for event in events:
        if event.get("kind") != "anomaly_injected":
            continue
        spec = event.get("spec") or {}
        name = str(spec.get("name") or "anomaly")
        if name and name not in seen:
            seen.add(name)
            flag_names.append(name)

    for name in flag_names:
        points = []
        for row in tel_series:
            flags = row.get("anomaly_flags") or []
            active = isinstance(flags, list) and name in flags
            points.append((int(row["step"]), "active" if active else "inactive"))
        lanes.append(
            {
                "lane": name,
                "key": f"anomaly:{name}",
                "segments": _contiguous_segments(points),
            }
        )

    return lanes
