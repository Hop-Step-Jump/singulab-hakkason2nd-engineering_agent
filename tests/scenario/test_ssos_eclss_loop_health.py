"""Health and summary helpers for ssos_eclss_loop."""

from __future__ import annotations

import pytest

from environment.protocol import HealthStatus
from environment.ssos.eclss.types import EclssTelemetrySnapshot
from scenario.ssos_eclss_loop.health import (
    build_effective_thresholds,
    compute_eclss_storage_health,
    health_inputs_note,
)
from scenario.ssos_eclss_loop.scenario_run import (
    _assert_ros2_storage_telemetry,
    _omit_nulls,
    _storage_telemetry_missing,
    _telemetry_summary_fields,
    _wait_for_ros2_storage_telemetry,
)


def test_build_effective_thresholds_defaults_match_scenario_yaml():
    effective = build_effective_thresholds({})
    assert effective["co2_storage_high_kg"] == pytest.approx(2.0)
    assert effective["co2_storage_critical_kg"] == pytest.approx(8.0)
    assert effective["o2_storage_low_kg"] == pytest.approx(6.0)
    assert effective["product_water_low_l"] == pytest.approx(50.0)


def test_build_effective_thresholds_includes_derived_criticals():
    effective = build_effective_thresholds(
        {
            "co2_storage_high_kg": 1.6,
            "co2_storage_critical_kg": 2.3,
            "o2_storage_low_kg": 0.4,
            "product_water_low_l": 40.0,
        }
    )
    assert effective["o2_storage_critical_kg"] == pytest.approx(0.3)
    assert effective["product_water_critical_l"] == pytest.approx(20.0)
    assert "co2" in health_inputs_note()


def test_build_effective_thresholds_promotes_yaml_criticals():
    effective = build_effective_thresholds(
        {
            "o2_storage_low_kg": 0.45,
            "o2_storage_critical_kg": 0.2,
            "product_water_low_l": 50.0,
            "product_water_critical_l": 10.0,
        }
    )
    assert effective["o2_storage_critical_kg"] == pytest.approx(0.2)
    assert effective["product_water_critical_l"] == pytest.approx(10.0)


def test_health_unknown_when_telemetry_missing():
    snap = EclssTelemetrySnapshot()
    health = compute_eclss_storage_health(0, snap, {})
    assert health["co2_status"] == HealthStatus.UNKNOWN.value
    assert health["o2_status"] == HealthStatus.UNKNOWN.value
    assert health["water_status"] == HealthStatus.UNKNOWN.value
    assert health["overall"] == HealthStatus.UNKNOWN.value


def test_health_unknown_for_nan_telemetry():
    import math

    snap = EclssTelemetrySnapshot(co2_storage_kg=math.nan, o2_storage_kg=math.nan)
    health = compute_eclss_storage_health(0, snap, {"co2_storage_high_kg": 1.5, "o2_storage_low_kg": 0.45})
    assert health["co2_status"] == HealthStatus.UNKNOWN.value
    assert health["o2_status"] == HealthStatus.UNKNOWN.value
    assert health["overall"] == HealthStatus.UNKNOWN.value


def test_telemetry_snapshot_to_dict_omits_nulls():
    payload = EclssTelemetrySnapshot(co2_storage_kg=10.0).to_dict()
    assert payload == {"co2_storage_kg": 10.0}
    assert "o2_storage_kg" not in payload


def test_summary_helpers_omit_null_metrics():
    snap = EclssTelemetrySnapshot(co2_storage_kg=12.5, o2_storage_kg=480.0, raw_topics={"/co2_storage": 12.5})
    fields = _telemetry_summary_fields(snap, peak_co2=12.5, min_o2=480.0)
    assert fields["final_co2_storage_kg"] == 12.5
    assert "final_product_water_reserve_l" not in fields
    assert fields["telemetry_topics_read"] == ["/co2_storage"]

    omitted = _omit_nulls({"ars_invoked_step": None, "message_count": 0})
    assert omitted == {"message_count": 0}


def test_storage_telemetry_missing_detects_empty_snapshot():
    assert _storage_telemetry_missing(EclssTelemetrySnapshot()) is True
    assert _storage_telemetry_missing(EclssTelemetrySnapshot(o2_storage_kg=1.0)) is False


def test_assert_ros2_storage_telemetry_raises_when_empty():
    import pytest

    with pytest.raises(RuntimeError, match="No ECLSS storage telemetry"):
        _assert_ros2_storage_telemetry(1, EclssTelemetrySnapshot())


def test_wait_for_ros2_storage_telemetry_returns_when_present():
    class _Backend:
        def __init__(self) -> None:
            self._calls = 0

        def poll_telemetry(self) -> EclssTelemetrySnapshot:
            self._calls += 1
            if self._calls < 2:
                return EclssTelemetrySnapshot()
            return EclssTelemetrySnapshot(co2_storage_kg=1500.0)

    snap = _wait_for_ros2_storage_telemetry(_Backend(), timeout_s=1.0, poll_interval_s=0.01)
    assert snap.co2_storage_kg == 1500.0


def test_wait_for_ros2_storage_telemetry_times_out():
    import pytest

    class _EmptyBackend:
        def poll_telemetry(self) -> EclssTelemetrySnapshot:
            return EclssTelemetrySnapshot()

    with pytest.raises(RuntimeError, match="Timed out waiting"):
        _wait_for_ros2_storage_telemetry(_EmptyBackend(), timeout_s=0.05, poll_interval_s=0.01)
