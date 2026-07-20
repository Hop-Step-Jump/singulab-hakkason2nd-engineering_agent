"""In-memory EclssBackend stub for local dev and contract tests."""

from __future__ import annotations

from typing import Optional

from environment.ssos.eclss.types import (
    ActionResult,
    ArsGoal,
    EclssTelemetrySnapshot,
    OgsGoal,
    ServiceResult,
    WrsGoal,
)
from environment.ssos.eclss.units import water_kg_to_l

# Approximate WRS pipeline recovery (UPA × filter × ionization from SSOS defaults).
_WRS_URINE_RECOVERY = 0.95 * 0.90 * 0.98
_GREY_WATER_RECOVERY = 0.50


class MockEclssBackend:
    """No-op backend that satisfies EclssBackend without ROS or SSOS."""

    def __init__(self) -> None:
        self._telemetry = EclssTelemetrySnapshot(
            co2_storage_kg=1.8,
            o2_storage_kg=0.5,
            product_water_reserve_l=100.0,
        )
        self._grey_water_buffer_l = 0.0
        self._failure_flags: dict[str, bool] = {
            "ars": False,
            "ogs": False,
            "wrs": False,
        }
        self.last_ars_goal: Optional[ArsGoal] = None
        self.last_ogs_goal: Optional[OgsGoal] = None
        self.last_wrs_goal: Optional[WrsGoal] = None

    def poll_telemetry(self) -> EclssTelemetrySnapshot:
        return EclssTelemetrySnapshot(
            co2_storage_kg=self._telemetry.co2_storage_kg,
            o2_storage_kg=self._telemetry.o2_storage_kg,
            product_water_reserve_l=self._telemetry.product_water_reserve_l,
            grey_water_collected_l=self._grey_water_buffer_l,
            ars_failure_enabled=self._failure_flags["ars"],
            ogs_failure_enabled=self._failure_flags["ogs"],
            wrs_failure_enabled=self._failure_flags["wrs"],
        )

    def send_air_revitalisation_goal(self, goal: ArsGoal) -> ActionResult:
        self.last_ars_goal = goal
        return ActionResult(success=True, summary_message="mock air_revitalisation complete")

    def send_oxygen_generation_goal(self, goal: OgsGoal) -> ActionResult:
        self.last_ogs_goal = goal
        water_kg = float(goal.input_water_mass)
        water_used_l = water_kg_to_l(water_kg)
        reserve = self._telemetry.product_water_reserve_l or 0.0
        self._telemetry.product_water_reserve_l = max(0.0, reserve - water_used_l)
        return ActionResult(
            success=True,
            summary_message="mock oxygen_generation complete",
            details={
                # Fixed mock O₂ gain (kg). Stoichiometric yield is out of scope for unit fixes.
                "total_o2_generated": 0.12,
                "input_water_mass": water_kg,
                "water_used_l": water_used_l,
            },
        )

    def send_water_recovery_goal(self, goal: WrsGoal) -> ActionResult:
        self.last_wrs_goal = goal
        purified_from_urine = goal.urine_volume * _WRS_URINE_RECOVERY
        grey_recovered = self._grey_water_buffer_l * _GREY_WATER_RECOVERY
        self._grey_water_buffer_l = max(0.0, self._grey_water_buffer_l - grey_recovered)
        total_purified = purified_from_urine + grey_recovered
        reserve = self._telemetry.product_water_reserve_l or 0.0
        self._telemetry.product_water_reserve_l = reserve + total_purified
        return ActionResult(
            success=True,
            summary_message="mock water_recovery complete",
            details={"total_purified_water": total_purified, "total_cycles": 1},
        )

    def request_o2(self, amount: float) -> ServiceResult:
        return ServiceResult(success=True, response_value=amount, message="mock o2 delivered")

    def request_co2(self, amount: float) -> ServiceResult:
        return ServiceResult(success=True, response_value=amount, message="mock co2 delivered")

    def request_product_water(self, liters: float) -> ServiceResult:
        reserve = self._telemetry.product_water_reserve_l or 0.0
        granted = min(liters, reserve)
        self._telemetry.product_water_reserve_l = reserve - granted
        success = granted >= liters
        return ServiceResult(
            success=success,
            response_value=granted,
            message="mock water delivered" if success else "insufficient product water reserve",
        )

    def submit_grey_water(self, liters: float) -> ServiceResult:
        self._grey_water_buffer_l += liters
        return ServiceResult(success=True, message="mock grey water accepted")

    def set_subsystem_failure(self, subsystem: str, enabled: bool) -> None:
        key = subsystem.lower().removesuffix("_failure")
        if key not in self._failure_flags:
            raise ValueError(f"unknown subsystem: {subsystem!r}")
        self._failure_flags[key] = enabled
