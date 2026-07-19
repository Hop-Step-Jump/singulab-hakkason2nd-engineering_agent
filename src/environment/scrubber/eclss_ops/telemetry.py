"""Telemetry formatting and health status derivation.

CO₂ bands (single source of truth for scrubber_degradation)
----------------------------------------------------------
- ``CO2_SAFE_PPM`` (800): health SAFE if strictly below this
- ``CO2_RECOVERY_PPM`` (1000): shared operational band for labeled agents,
  summary recovery KPI, and dashboard reference line
- ``CO2_WARNING_PPM`` (1200): health WARNING below this; CRITICAL at/above
"""

from __future__ import annotations

from environment.protocol import HealthMetrics, HealthStatus, TelemetrySnapshot

CO2_SAFE_PPM = 800.0
CO2_RECOVERY_PPM = 1000.0
CO2_WARNING_PPM = 1200.0
POWER_LOW_W = 0.0
POWER_CRITICAL_W = -150.0


def co2_health(co2_ppm: float) -> HealthStatus:
    if co2_ppm < CO2_SAFE_PPM:
        return HealthStatus.SAFE
    if co2_ppm < CO2_WARNING_PPM:
        return HealthStatus.WARNING
    return HealthStatus.CRITICAL


def power_health(power_margin_w: float) -> HealthStatus:
    if power_margin_w > POWER_LOW_W:
        return HealthStatus.SAFE
    if power_margin_w > POWER_CRITICAL_W:
        return HealthStatus.WARNING
    return HealthStatus.CRITICAL


def overall_health(co2: HealthStatus, power: HealthStatus) -> HealthStatus:
    order = {HealthStatus.SAFE: 0, HealthStatus.WARNING: 1, HealthStatus.CRITICAL: 2}
    return co2 if order[co2] >= order[power] else power


def compute_health_metrics(snapshot: TelemetrySnapshot) -> HealthMetrics:
    co2 = co2_health(snapshot.co2_ppm)
    power = power_health(snapshot.power_margin_w)
    return HealthMetrics(
        step=snapshot.step,
        co2_status=co2,
        power_status=power,
        overall=overall_health(co2, power),
    )


def snapshot_to_topics(snapshot: TelemetrySnapshot) -> dict[str, float | bool | list[str] | int]:
    """Map snapshot fields to ROS2-like topic payloads."""
    from environment.scrubber import topics

    return {
        topics.TELEMETRY_CO2: snapshot.co2_ppm,
        topics.TELEMETRY_SCRUBBER: snapshot.scrubber_efficiency,
        topics.TELEMETRY_POWER: snapshot.power_margin_w,
    }
