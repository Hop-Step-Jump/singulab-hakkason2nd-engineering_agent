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


class LoopMockEclssBackend(MockEclssBackend):
    """MockEclssBackend extension that evolves CO2/O2 storage across poll cycles.

    Storage (``_co2`` / ``_o2`` / ``_water``) is the single source of truth for
    ``poll_telemetry``. Parent ``_telemetry`` is kept in sync so inherited
    helpers do not drift (D2).
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__()
        sim_cfg = config.get("simulation", {})
        mock_cfg = config.get("mock_dynamics", {})
        self._co2 = float(sim_cfg.get("initial_co2_storage_kg", 1.65))
        self._o2 = float(sim_cfg.get("initial_o2_storage_kg", 0.48))
        self._water = float(sim_cfg.get("initial_product_water_l", 100.0))
        self._co2_growth = float(mock_cfg.get("co2_growth_kg_per_step", 0.06))
        self._ars_reduction = float(mock_cfg.get("ars_co2_reduction_kg", 0.35))
        # Reference mass for scaling ARS reduction with goal.initial_co2_mass (D1).
        self._ars_reference_kg = float(mock_cfg.get("ars_reference_co2_mass_kg", 1.8))
        self._sabatier_co2_per_water = float(mock_cfg.get("sabatier_co2_kg_per_water_kg", 2.0))
        self._sync_parent_telemetry()

    def _sync_parent_telemetry(self) -> None:
        self._telemetry.co2_storage_kg = self._co2
        self._telemetry.o2_storage_kg = self._o2
        self._telemetry.product_water_reserve_l = self._water

    def advance_step(self) -> None:
        self._co2 += self._co2_growth
        self._sync_parent_telemetry()

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
        if not result.success:
            return result
        # D1: scale fixed mock reduction by goal mass vs reference (design proposals matter).
        reference = self._ars_reference_kg
        goal_mass = max(0.0, float(goal.initial_co2_mass))
        scale = (goal_mass / reference) if reference > 0.0 else 0.0
        reduction = min(self._co2, self._ars_reduction * scale)
        self._co2 = max(0.0, self._co2 - reduction)
        self._sync_parent_telemetry()
        return ActionResult(
            success=True,
            summary_message=result.summary_message,
            details={
                "co2_reduced_kg": reduction,
                "initial_co2_mass": goal_mass,
                "ars_scale": scale,
            },
        )

    def send_oxygen_generation_goal(self, goal: OgsGoal) -> ActionResult:
        # D2: parent water draw uses the same reserve LoopMock publishes.
        self._sync_parent_telemetry()
        result = super().send_oxygen_generation_goal(goal)
        if not result.success:
            return result
        # Inherit single water subtract from parent; do not subtract again.
        self._water = float(self._telemetry.product_water_reserve_l or 0.0)
        # Prefer parent mock O₂ yield (stoichiometric via o2_generated_kg) over a separate gain.
        o2_gain = float(result.details.get("total_o2_generated", 0.0))
        self._o2 += max(0.0, o2_gain)
        water_kg = max(0.0, float(goal.input_water_mass))
        # Models OGS-internal Sabatier /ars/request_co2. If labeled also issued
        # request_co2_before_ogs in this step, LoopMock (no buffer) double-debits.
        sabatier_co2 = min(self._co2, water_kg * self._sabatier_co2_per_water)
        self._co2 = max(0.0, self._co2 - sabatier_co2)
        self._sync_parent_telemetry()
        details = dict(result.details)
        details["sabatier_co2_consumed_kg"] = sabatier_co2
        return ActionResult(
            success=True,
            summary_message=result.summary_message,
            details=details,
        )

    def request_co2(self, amount: float) -> ServiceResult:
        """Withdraw CO2 from plant storage for Sabatier feedstock (D3).

        All-or-nothing like SSOS ``/ars/request_co2``: reject without mutating
        storage when the full requested mass is unavailable (no partial grant).
        """
        result = super().request_co2(amount)
        if not result.success:
            return result
        need = float(amount)
        if self._co2 < need:
            return ServiceResult(
                success=False,
                response_value=0.0,
                message="insufficient CO2 in storage",
            )
        self._co2 -= need
        self._sync_parent_telemetry()
        return ServiceResult(
            success=True,
            response_value=need,
            message="mock co2 delivered",
        )

    def request_o2(self, amount: float) -> ServiceResult:
        """Withdraw O2 from plant storage (/o2_storage) when the service succeeds."""
        result = super().request_o2(amount)
        if not result.success:
            return result
        granted = min(self._o2, float(amount))
        if granted <= 0.0:
            return ServiceResult(
                success=False,
                response_value=0.0,
                message="insufficient O2 in storage",
            )
        self._o2 = max(0.0, self._o2 - granted)
        self._sync_parent_telemetry()
        return ServiceResult(
            success=True,
            response_value=granted,
            message="mock o2 delivered",
        )

    def send_water_recovery_goal(self, goal: WrsGoal) -> ActionResult:
        raise NotImplementedError("WRS actions are Phase 2")

    def request_product_water(self, liters: float) -> ServiceResult:
        raise NotImplementedError("WRS product water is Phase 2")

    def submit_grey_water(self, liters: float) -> ServiceResult:
        raise NotImplementedError("grey water service is Phase 2")
