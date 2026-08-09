"""Tests for ssos_eclss_loop dashboard extractors (run artifacts only)."""

from tools.dashboard import ssos_flow


def test_thresholds_from_summary_returns_none_when_absent():
    assert ssos_flow.thresholds_from_summary({}) is None
    assert ssos_flow.thresholds_from_summary({"thresholds": {}}) is None


def test_thresholds_from_summary_passes_through_recorded_values():
    summary = {
        "thresholds": {
            "co2_storage_high_kg": 1.5,
            "o2_storage_low_kg": 0.45,
            "o2_storage_critical_kg": 0.3375,
        }
    }
    thresholds = ssos_flow.thresholds_from_summary(summary)
    assert thresholds is not None
    assert thresholds["co2_storage_high_kg"] == 1.5
    assert thresholds["o2_storage_critical_kg"] == 0.3375


def test_extract_metabolism_by_step_ignores_post_ops_rows():
    telemetry = [
        {
            "step": 2,
            "raw_topics": {
                "plant_sim": {
                    "last_metabolism": {"co2_generated_kg": 0.01, "o2_consumed_kg": 0.008},
                }
            },
        },
        {
            "step": 2,
            "post_ops": True,
            "raw_topics": {"plant_sim": {"last_metabolism": {"co2_generated_kg": 999.0}}},
        },
    ]
    by_step = ssos_flow.extract_metabolism_by_step(telemetry)
    assert by_step[2]["co2_generated_kg"] == 0.01


def test_extract_ops_flows_uses_result_details_only():
    events = [
        {
            "step": 1,
            "kind": "/eclss/events/operational_applied",
            "command": {"kind": "air_revitalisation"},
            "result": {
                "success": True,
                "details": {"co2_removed_kg": 0.5, "captured_co2_kg": 0.4},
            },
        },
        {
            "step": 1,
            "kind": "/eclss/events/operational_applied",
            "command": {"kind": "request_co2"},
            "result": {"success": True, "response_value": 0.02, "message": "co2 delivered"},
        },
        {"step": 1, "kind": "/eclss/events/operational_rejected", "command": {"kind": "air_revitalisation"}},
    ]
    flows = ssos_flow.extract_ops_flows(events)
    assert len(flows) == 2
    assert flows[0]["details"]["co2_removed_kg"] == 0.5
    assert flows[1]["details"]["response_value"] == 0.02


def test_list_design_changes_does_not_invent_why():
    proposals = {
        "changes": [
            {
                "change_kind": "action_profile",
                "payload": {"subsystem": "ars", "fields": {"initial_co2_mass": 2.0}},
            }
        ]
    }
    listed = ssos_flow.list_design_changes(proposals)
    assert listed[0]["change_kind"] == "action_profile"
    assert "why" not in listed[0]
    assert "what" not in listed[0]
    assert "how" not in listed[0]


def test_build_step_node_numbers_maps_metabolism_and_ops():
    telemetry_row = {
        "step": 3,
        "co2_storage_kg": 1.2,
        "o2_storage_kg": 0.5,
        "product_water_reserve_l": 80.0,
        "grey_water_collected_l": 0.1,
        "raw_topics": {"plant_sim": {"captured_co2_kg": 0.3, "urine_buffer_l": 0.05}},
    }
    metabolism = {"co2_generated_kg": 0.01, "o2_consumed_kg": 0.008}
    ops_flows = [
        {
            "step": 3,
            "kind": "air_revitalisation",
            "details": {"co2_removed_kg": 0.4, "captured_co2_kg": 0.35},
        }
    ]
    nodes = ssos_flow.build_step_node_numbers(
        step=3,
        telemetry_row=telemetry_row,
        ops_flows=ops_flows,
        metabolism=metabolism,
    )
    assert any("CO2 generated" in line for line in nodes["crew"])
    assert any("cabin CO2" in line for line in nodes["cabin"])
    assert any("CO2 removed" in line for line in nodes["ars"])


def test_build_step_node_numbers_labels_mock_co2_as_storage():
    """mock/ros2 co2_storage_kg is /co2_storage inventory, not cabin atmosphere."""
    telemetry_row = {
        "step": 1,
        "co2_storage_kg": 1.8,
        "o2_storage_kg": 0.6,
        "product_water_reserve_l": 50.0,
    }
    nodes = ssos_flow.build_step_node_numbers(
        step=1,
        telemetry_row=telemetry_row,
        ops_flows=[],
        metabolism=None,
    )
    assert any("CO2 storage" in line for line in nodes["co2_tank"])
    assert not any("cabin CO2" in line for line in nodes["cabin"])
    assert any("available O2" in line for line in nodes["cabin"])
