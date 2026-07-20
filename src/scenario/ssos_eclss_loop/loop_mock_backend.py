"""Mock EclssBackend with simple storage dynamics for ssos_eclss_loop tests."""

from __future__ import annotations

from typing import Any, Dict

from environment.ssos.eclss.types import (
    ActionResult,
    ArsGoal,
    EclssTelemetrySnapshot,
    OgsGoal,
    ServiceResult,
    WrsGoal,
)
from environment.ssos.eclss.mock.backend import MockEclssBackend
from environment.ssos.eclss.units import water_kg_to_l


class LoopMockEclssBackend(MockEclssBackend):
    """MockEclssBackend extension that evolves CO2/O2 storage across poll cycles."""

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__()
        sim_cfg = config.get("simulation", {})
        mock_cfg = config.get("mock_dynamics", {})
        self._co2 = float(sim_cfg.get("initial_co2_storage_kg", 1.65))
        self._o2 = float(sim_cfg.get("initial_o2_storage_kg", 0.48))
        self._water = float(sim_cfg.get("initial_product_water_l", 100.0))
        self._co2_growth = float(mock_cfg.get("co2_growth_kg_per_step", 0.06))
        self._ars_reduction = float(mock_cfg.get("ars_co2_reduction_kg", 0.35))
        self._ogs_o2_gain = float(mock_cfg.get("ogs_o2_gain_kg", 0.1))

    def advance_step(self) -> None:
        self._co2 += self._co2_growth

    def poll_telemetry(self) -> EclssTelemetrySnapshot:
        return EclssTelemetrySnapshot(
            co2_storage_kg=self._co2,
            o2_storage_kg=self._o2,
            product_water_reserve_l=self._water,
            ars_failure_enabled=self._failure_flags["ars"],
            ogs_failure_enabled=self._failure_flags["ogs"],
            wrs_failure_enabled=self._failure_flags["wrs"],
        )

    def send_air_revitalisation_goal(self, goal: ArsGoal) -> ActionResult:
        result = super().send_air_revitalisation_goal(goal)
        self._co2 = max(0.0, self._co2 - self._ars_reduction)
        return result

    def send_oxygen_generation_goal(self, goal: OgsGoal) -> ActionResult:
        result = super().send_oxygen_generation_goal(goal)
        water_kg = float(goal.input_water_mass)
        self._o2 += self._ogs_o2_gain
        # Keep LoopMock public water in sync with parent mass→liter draw (U2).
        self._water = max(0.0, self._water - water_kg_to_l(water_kg))
        self._co2 = max(0.0, self._co2 - min(self._co2, 0.03))
        return result

    def request_co2(self, amount: float) -> ServiceResult:
        result = super().request_co2(amount)
        self._co2 += amount
        return result

    def request_o2(self, amount: float) -> ServiceResult:
        """Withdraw O2 from plant storage (/o2_storage) when the service succeeds."""
        result = super().request_o2(amount)
        if result.success:
            self._o2 = max(0.0, self._o2 - min(self._o2, amount))
        return result

    def send_water_recovery_goal(self, goal: WrsGoal) -> ActionResult:
        raise NotImplementedError("WRS actions are Phase 2")

    def request_product_water(self, liters: float) -> ServiceResult:
        raise NotImplementedError("WRS product water is Phase 2")

    def submit_grey_water(self, liters: float) -> ServiceResult:
        raise NotImplementedError("grey water service is Phase 2")
