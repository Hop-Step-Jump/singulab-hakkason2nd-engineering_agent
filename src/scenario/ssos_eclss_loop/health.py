"""Deterministic health assessment for SSOS ECLSS storage telemetry."""

from __future__ import annotations

import math
from typing import Any, Dict, Optional

from environment.protocol import HealthStatus
from environment.ssos.eclss.types import EclssTelemetrySnapshot


HEALTH_INPUT_FIELDS = {
    "co2": "telemetry.co2_storage_kg",
    "o2": "telemetry.o2_storage_kg",
    "water": "telemetry.product_water_reserve_l",
}


def build_effective_thresholds(thresholds: Dict[str, Any]) -> Dict[str, Any]:
    """Thresholds actually used by ``compute_eclss_storage_health`` for a run."""
    co2_high = float(thresholds.get("co2_storage_high_kg", 1.5))
    co2_critical = float(thresholds.get("co2_storage_critical_kg", 2.2))
    o2_low = float(thresholds.get("o2_storage_low_kg", 0.45))
    water_low = float(thresholds.get("product_water_low_l", 50.0))
    return {
        "co2_storage_high_kg": co2_high,
        "co2_storage_critical_kg": co2_critical,
        "o2_storage_low_kg": o2_low,
        "o2_storage_critical_kg": o2_low * 0.75,
        "product_water_low_l": water_low,
        "product_water_critical_l": water_low * 0.5,
    }


def health_inputs_note() -> Dict[str, str]:
    """Document which telemetry fields health assessment reads."""
    return dict(HEALTH_INPUT_FIELDS)


def compute_eclss_storage_health(
    step: int,
    snap: EclssTelemetrySnapshot,
    thresholds: Dict[str, Any],
) -> Dict[str, Any]:
    effective = build_effective_thresholds(thresholds)
    co2_high = effective["co2_storage_high_kg"]
    co2_critical = effective["co2_storage_critical_kg"]
    o2_low = effective["o2_storage_low_kg"]
    water_low = effective["product_water_low_l"]

    co2_status = _co2_status(snap.co2_storage_kg, co2_high, co2_critical)
    o2_status = _o2_status(snap.o2_storage_kg, o2_low)
    water_status = _water_status(snap.product_water_reserve_l, water_low)
    overall = _worst_status(co2_status, o2_status, water_status)

    return {
        "step": step,
        "co2_status": co2_status.value,
        "o2_status": o2_status.value,
        "water_status": water_status.value,
        "overall": overall.value,
    }


def _invalid_reading(value: Optional[float]) -> bool:
    return value is None or not math.isfinite(float(value))


def _co2_status(value: Optional[float], high: float, critical: float) -> HealthStatus:
    if _invalid_reading(value):
        return HealthStatus.UNKNOWN
    assert value is not None
    if value >= critical:
        return HealthStatus.CRITICAL
    if value >= high:
        return HealthStatus.WARNING
    return HealthStatus.SAFE


def _o2_status(value: Optional[float], low: float) -> HealthStatus:
    if _invalid_reading(value):
        return HealthStatus.UNKNOWN
    assert value is not None
    if value <= low * 0.75:
        return HealthStatus.CRITICAL
    if value <= low:
        return HealthStatus.WARNING
    return HealthStatus.SAFE


def _water_status(value: Optional[float], low: float) -> HealthStatus:
    if _invalid_reading(value):
        return HealthStatus.UNKNOWN
    assert value is not None
    if value <= low * 0.5:
        return HealthStatus.CRITICAL
    if value <= low:
        return HealthStatus.WARNING
    return HealthStatus.SAFE


def _worst_status(*statuses: HealthStatus) -> HealthStatus:
    order = {
        HealthStatus.SAFE: 0,
        HealthStatus.UNKNOWN: 1,
        HealthStatus.WARNING: 2,
        HealthStatus.CRITICAL: 3,
    }
    return max(statuses, key=lambda s: order[s])
