"""Tests for dashboard anomaly / operator / design-driver / timeline extractors."""

from tools.dashboard.run_status import (
    _contiguous_segments,
    _episode_onset,
    build_anomaly_timeline_lanes,
    build_status_timeline_lanes,
    extract_anomaly_status,
    extract_design_drivers,
    extract_operator_step,
)


def test_extract_anomaly_status_health_band_elapsed():
    health = [
        {"step": 1, "overall": "safe", "co2_status": "safe", "o2_status": "safe", "water_status": "safe"},
        {"step": 2, "overall": "warning", "co2_status": "warning", "o2_status": "safe", "water_status": "safe"},
        {"step": 3, "overall": "critical", "co2_status": "critical", "o2_status": "safe", "water_status": "safe"},
    ]
    telemetry = [
        {"step": 1, "co2_storage_kg": 1.0, "o2_storage_kg": 1.0, "product_water_reserve_l": 10.0},
        {"step": 2, "co2_storage_kg": 1.6, "o2_storage_kg": 1.0, "product_water_reserve_l": 10.0},
        {"step": 3, "co2_storage_kg": 2.3, "o2_storage_kg": 1.0, "product_water_reserve_l": 10.0},
    ]
    rows = extract_anomaly_status(
        step=3,
        telemetry_rows=telemetry,
        health_rows=health,
        events=[],
        summary={
            "thresholds": {
                "co2_storage_high_kg": 1.5,
                "co2_storage_critical_kg": 2.2,
            }
        },
    )
    by_name = {row["name"]: row for row in rows}
    assert by_name["co2_status"]["severity"] == "critical"
    assert by_name["co2_status"]["onset_step"] == 2
    assert by_name["co2_status"]["elapsed_steps"] == 1
    assert "co2_storage_kg=2.3" in by_name["co2_status"]["telemetry"]
    assert by_name["overall"]["onset_step"] == 2


def test_extract_anomaly_status_prefers_pre_ops_stress_when_post_ops_safe():
    health = [
        {"step": 6, "overall": "warning", "co2_status": "warning", "o2_status": "safe", "water_status": "safe"},
        {
            "step": 6,
            "overall": "safe",
            "co2_status": "safe",
            "o2_status": "safe",
            "water_status": "safe",
            "post_ops": True,
        },
    ]
    telemetry = [{"step": 6, "co2_storage_kg": 1.6, "o2_storage_kg": 1.0, "product_water_reserve_l": 10.0}]
    rows = extract_anomaly_status(
        step=6,
        telemetry_rows=telemetry,
        health_rows=health,
        events=[],
        summary={"thresholds": {"co2_storage_high_kg": 1.5}},
    )
    by_name = {row["name"]: row for row in rows}
    assert by_name["co2_status"]["severity"] == "warning"
    assert by_name["overall"]["severity"] == "warning"


def test_extract_anomaly_status_scheduled_scrubber_when_other_flags_present():
    telemetry = [
        {
            "step": 5,
            "anomaly_flags": ["other_anomaly"],
            "scrubber_efficiency": 0.9,
            "co2_ppm": 900.0,
        }
    ]
    rows = extract_anomaly_status(
        step=5,
        telemetry_rows=telemetry,
        health_rows=[
            {"step": 5, "overall": "safe", "co2_status": "safe", "o2_status": "safe", "water_status": "safe"}
        ],
        events=[
            {"kind": "anomaly_injected", "spec": {"name": "scrubber_degradation", "start_step": 4}},
        ],
    )
    by_name = {row["name"]: row for row in rows if row["type"] == "scrubber_anomaly"}
    assert "other_anomaly" in by_name
    assert by_name["other_anomaly"]["severity"] == "active"
    assert "scrubber_degradation" in by_name
    assert by_name["scrubber_degradation"]["severity"] == "scheduled_or_active"
    assert by_name["scrubber_degradation"]["onset_step"] == 4
    assert "scheduled_from_step=4" in by_name["scrubber_degradation"]["telemetry"]


def test_extract_anomaly_status_subsystem_failure_and_scrubber_flag():
    telemetry = [
        {"step": 1, "ars_failure_enabled": False, "anomaly_flags": []},
        {"step": 2, "ars_failure_enabled": True, "anomaly_flags": []},
        {"step": 3, "ars_failure_enabled": True, "anomaly_flags": []},
        {"step": 4, "ars_failure_enabled": True, "anomaly_flags": []},
        {
            "step": 5,
            "ars_failure_enabled": True,
            "anomaly_flags": ["scrubber_degradation"],
            "scrubber_efficiency": 0.8,
            "co2_ppm": 1200.0,
        },
    ]
    rows = extract_anomaly_status(
        step=5,
        telemetry_rows=telemetry,
        health_rows=[
            {"step": 5, "overall": "safe", "co2_status": "safe", "o2_status": "safe", "water_status": "safe"}
        ],
        events=[
            {"kind": "anomaly_injected", "spec": {"name": "scrubber_degradation", "start_step": 4}},
        ],
    )
    types = {row["type"] for row in rows}
    assert "subsystem_failure" in types
    assert "scrubber_anomaly" in types
    ars = next(row for row in rows if row["name"] == "ARS")
    assert ars["onset_step"] == 2
    assert ars["elapsed_steps"] == 3
    scrubber = next(row for row in rows if row["name"] == "scrubber_degradation")
    assert scrubber["onset_step"] == 5
    assert "scrubber_efficiency=0.8" in scrubber["telemetry"]


def test_extract_operator_step_includes_thoughts_and_ops():
    messages = [
        {
            "step": 2,
            "from_role": "eclss_operator_1",
            "message_type": "comment",
            "decision_source": "llm",
            "deliberation_phase": "deliberation",
            "message": "O2 looks low.",
            "reasoning": "Telemetry o2_storage_kg=0.2",
        },
        {
            "step": 2,
            "from_role": "eclss_operator_1",
            "message_type": "operational_command",
            "decision_source": "llm",
            "deliberation_phase": "action",
            "message": "Start OGS",
            "reasoning": "Need oxygen",
        },
        {"step": 1, "from_role": "eclss_operator_2", "message": "ignore"},
    ]
    events = [
        {
            "step": 2,
            "kind": "/eclss/events/operational_applied",
            "command": {"kind": "oxygen_generation", "issued_by": "eclss_operator_1"},
            "success": True,
            "result": {"success": True, "details": {"o2_produced_kg": 0.1}},
        }
    ]
    payload = extract_operator_step(
        step=2,
        messages=messages,
        events=events,
        summary={"agents_mode": "llm"},
    )
    assert payload["agents_mode"] == "llm"
    assert payload["actor_mode"] is None
    assert payload["design_mode"] is None
    assert len(payload["messages"]) == 2
    assert payload["messages"][0]["reasoning"] == "Telemetry o2_storage_kg=0.2"
    assert payload["operations"][0]["command_kind"] == "oxygen_generation"
    assert payload["operations"][0]["details"]["o2_produced_kg"] == 0.1


def test_extract_operator_step_includes_actor_and_design_modes():
    payload = extract_operator_step(
        step=1,
        messages=[],
        events=[],
        summary={
            "agents_mode": "labeled_rule_base",
            "actor_mode": "labeled_rule_base",
            "design_mode": "llm",
        },
    )
    assert payload["actor_mode"] == "labeled_rule_base"
    assert payload["design_mode"] == "llm"


def test_extract_design_drivers_uses_recorded_fields_only():
    proposals = {
        "proposed_by": "eclss_operator_2",
        "decision_source": "rule",
        "message": "Raise ARS capacity",
        "reasoning": "CO2 peaked above high band",
        "changes": [
            {"change_kind": "action_profile", "why": "peak_co2_storage_kg=1.54 >= 1.5", "payload": {}}
        ],
    }
    drivers = extract_design_drivers(
        proposals,
        summary={
            "peak_co2_storage_kg": 1.54,
            "final_health": {"co2_status": "warning", "overall": "warning"},
        },
    )
    assert drivers["message"] == "Raise ARS capacity"
    assert drivers["reasoning"] == "CO2 peaked above high band"
    assert drivers["change_whys"] == ["peak_co2_storage_kg=1.54 >= 1.5"]
    assert "peak_co2_storage_kg=1.54" in drivers["summary_observations"]
    assert any("final_health" in item for item in drivers["summary_observations"])

    sparse = extract_design_drivers({"changes": [{"change_kind": "add_edge", "payload": {}}]})
    assert "message" not in sparse
    assert "reasoning" not in sparse
    assert "change_whys" not in sparse
    assert sparse["change_count"] == 1


def test_build_status_timeline_lanes_includes_power_band_for_scrubber_runs():
    health = [
        {"step": 1, "overall": "safe", "co2_status": "safe", "power_status": "safe"},
        {"step": 2, "overall": "warning", "co2_status": "safe", "power_status": "warning"},
        {"step": 3, "overall": "critical", "co2_status": "safe", "power_status": "critical"},
    ]
    lanes = {lane["key"]: lane for lane in build_status_timeline_lanes(health)}
    assert "power_status" in lanes
    assert "o2_status" not in lanes
    assert "water_status" not in lanes
    assert lanes["power_status"]["segments"][-1]["state"] == "critical"


def test_build_anomaly_timeline_lanes_omits_missing_failure_flags():
    telemetry = [
        {"step": 1, "anomaly_flags": []},
        {"step": 2, "anomaly_flags": ["scrubber_degradation"]},
    ]
    lanes = build_anomaly_timeline_lanes(telemetry, [])
    lane_keys = {lane["key"] for lane in lanes}
    assert "ars_failure_enabled" not in lane_keys
    assert "ogs_failure_enabled" not in lane_keys
    assert "wrs_failure_enabled" not in lane_keys
    assert "anomaly:scrubber_degradation" in lane_keys


def test_extract_anomaly_status_crew_shortfall_only_when_ledger_increases():
    telemetry = [
        {
            "step": 1,
            "raw_topics": {
                "plant_sim": {"total_o2_shortfall_kg": 0.0, "total_water_shortfall_l": 0.0}
            },
        },
        {
            "step": 2,
            "raw_topics": {
                "plant_sim": {"total_o2_shortfall_kg": 0.02, "total_water_shortfall_l": 0.0}
            },
        },
        {
            "step": 3,
            "raw_topics": {
                "plant_sim": {"total_o2_shortfall_kg": 0.02, "total_water_shortfall_l": 0.0}
            },
        },
        {
            "step": 4,
            "raw_topics": {
                "plant_sim": {"total_o2_shortfall_kg": 0.05, "total_water_shortfall_l": 0.01}
            },
        },
    ]
    rows_at_2 = extract_anomaly_status(
        step=2,
        telemetry_rows=telemetry,
        health_rows=[{"step": 2, "overall": "safe", "co2_status": "safe"}],
        events=[],
    )
    assert any(row["type"] == "plant_sim_shortfall" for row in rows_at_2)
    shortfall_2 = next(row for row in rows_at_2 if row["type"] == "plant_sim_shortfall")
    assert shortfall_2["onset_step"] == 2
    assert shortfall_2["elapsed_steps"] == 0

    rows_at_3 = extract_anomaly_status(
        step=3,
        telemetry_rows=telemetry,
        health_rows=[{"step": 3, "overall": "safe", "co2_status": "safe"}],
        events=[],
    )
    assert not any(row["type"] == "plant_sim_shortfall" for row in rows_at_3)

    rows_at_4 = extract_anomaly_status(
        step=4,
        telemetry_rows=telemetry,
        health_rows=[{"step": 4, "overall": "safe", "co2_status": "safe"}],
        events=[],
    )
    shortfall_4 = next(row for row in rows_at_4 if row["type"] == "plant_sim_shortfall")
    assert shortfall_4["onset_step"] == 2
    assert shortfall_4["elapsed_steps"] == 2


def test_extract_anomaly_status_crew_shortfall_episode_onset_across_consecutive_increases():
    telemetry = [
        {
            "step": 1,
            "raw_topics": {
                "plant_sim": {"total_o2_shortfall_kg": 0.0, "total_water_shortfall_l": 0.0}
            },
        },
        {
            "step": 2,
            "raw_topics": {
                "plant_sim": {"total_o2_shortfall_kg": 0.02, "total_water_shortfall_l": 0.0}
            },
        },
        {
            "step": 3,
            "raw_topics": {
                "plant_sim": {"total_o2_shortfall_kg": 0.04, "total_water_shortfall_l": 0.01}
            },
        },
    ]
    rows_at_3 = extract_anomaly_status(
        step=3,
        telemetry_rows=telemetry,
        health_rows=[{"step": 3, "overall": "safe", "co2_status": "safe"}],
        events=[],
    )
    shortfall = next(row for row in rows_at_3 if row["type"] == "plant_sim_shortfall")
    assert shortfall["onset_step"] == 2
    assert shortfall["elapsed_steps"] == 1


def test_build_status_timeline_lanes_prefers_post_ops_health_row():
    health = [
        {"step": 6, "overall": "warning", "co2_status": "warning", "o2_status": "safe", "water_status": "safe"},
        {
            "step": 6,
            "overall": "safe",
            "co2_status": "safe",
            "o2_status": "safe",
            "water_status": "safe",
            "post_ops": True,
        },
    ]
    lanes = {lane["key"]: lane for lane in build_status_timeline_lanes(health)}
    overall = lanes["overall"]["segments"]
    assert overall == [{"start_step": 6, "end_step": 7, "state": "safe"}]
    co2 = lanes["co2_status"]["segments"]
    assert co2 == [{"start_step": 6, "end_step": 7, "state": "safe"}]


def test_build_status_timeline_lanes_merges_contiguous_states():
    health = [
        {"step": 1, "overall": "safe", "co2_status": "safe", "o2_status": "safe", "water_status": "safe"},
        {"step": 2, "overall": "safe", "co2_status": "safe", "o2_status": "safe", "water_status": "safe"},
        {"step": 3, "overall": "warning", "co2_status": "warning", "o2_status": "safe", "water_status": "safe"},
        {"step": 4, "overall": "warning", "co2_status": "warning", "o2_status": "safe", "water_status": "safe"},
        {"step": 5, "overall": "critical", "co2_status": "critical", "o2_status": "safe", "water_status": "safe"},
    ]
    lanes = {lane["key"]: lane for lane in build_status_timeline_lanes(health)}
    overall = lanes["overall"]["segments"]
    assert overall == [
        {"start_step": 1, "end_step": 3, "state": "safe"},
        {"start_step": 3, "end_step": 5, "state": "warning"},
        {"start_step": 5, "end_step": 6, "state": "critical"},
    ]
    co2 = lanes["co2_status"]["segments"]
    assert co2[0]["state"] == "safe" and co2[0]["end_step"] == 3
    assert co2[-1]["state"] == "critical"


def test_build_anomaly_timeline_lanes_failures_and_scrubber_flags():
    telemetry = [
        {"step": 1, "ars_failure_enabled": False, "anomaly_flags": []},
        {"step": 2, "ars_failure_enabled": True, "anomaly_flags": []},
        {"step": 3, "ars_failure_enabled": True, "anomaly_flags": ["scrubber_degradation"]},
        {"step": 4, "ars_failure_enabled": False, "anomaly_flags": ["scrubber_degradation"]},
    ]
    lanes = {lane["key"]: lane for lane in build_anomaly_timeline_lanes(telemetry, [])}
    ars = lanes["ars_failure_enabled"]["segments"]
    assert {"start_step": 2, "end_step": 4, "state": "failure"} in ars
    assert {"start_step": 4, "end_step": 5, "state": "ok"} in ars
    scrubber = lanes["anomaly:scrubber_degradation"]["segments"]
    assert {"start_step": 3, "end_step": 5, "state": "active"} in scrubber


def test_episode_onset_breaks_on_missing_adjacent_steps():
    series = [
        {"step": 2, "ars_failure_enabled": True},
        {"step": 5, "ars_failure_enabled": True},
    ]
    onset = _episode_onset(
        series,
        step=5,
        is_active=lambda row: bool(row.get("ars_failure_enabled")),
    )
    assert onset == 5


def test_contiguous_segments_split_on_step_gaps():
    segments = _contiguous_segments(
        [
            (2, "warning"),
            (5, "warning"),
            (6, "warning"),
            (7, "safe"),
        ]
    )
    assert segments == [
        {"start_step": 2, "end_step": 3, "state": "warning"},
        {"start_step": 5, "end_step": 7, "state": "warning"},
        {"start_step": 7, "end_step": 8, "state": "safe"},
    ]
