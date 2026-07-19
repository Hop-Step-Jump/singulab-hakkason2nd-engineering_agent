"""Mock ECLSS simulator implementing SimulatorProtocol."""

from __future__ import annotations

from typing import Dict, List, Optional

from environment.scrubber.eclss_ops.anomalies import AnomalyManager
from environment.scrubber.eclss_ops.commands import apply_command_to_state, validate_command
from environment.scrubber.eclss_ops.design_state import DesignStateManager, default_parameters
from environment.protocol import (
    AnomalySpec,
    CommandKind,
    CommandResult,
    DesignState,
    RecoveryCommand,
    TelemetrySnapshot,
    TopologyGraph,
)
from environment.scrubber.topics import EVENT_ANOMALY, EVENT_RECOVERY


class MockEclssSimulator:
    """Simplified CO2 scrubber plant model for Week-1 MVP."""

    def __init__(
        self,
        initial_co2_ppm: float = 800.0,
        initial_power_margin_w: float = 150.0,
        design: Optional[DesignStateManager] = None,
        anomalies: Optional[AnomalyManager] = None,
    ):
        self.design = design or DesignStateManager()
        self.anomalies = anomalies or AnomalyManager()
        self.step_count = 0
        self.co2_ppm = initial_co2_ppm
        self.power_margin_w = initial_power_margin_w
        self.scrubber_efficiency = self.design.parameters["scrubber_base_efficiency"]
        self.fan_speed = 0.7
        self.bypass_enabled = False
        self.load_reduced = False
        self._event_log: List[dict] = []

    def inject_anomaly(self, spec: AnomalySpec) -> None:
        self.anomalies.register(spec)
        self._event_log.append({"kind": "anomaly_injected", "spec": spec.to_dict()})

    def step(self) -> TelemetrySnapshot:
        self.step_count += 1
        params = self.design.parameters
        active_flags = self.anomalies.on_step(self.step_count)

        self.scrubber_efficiency, self.power_margin_w, co2_mult = self.anomalies.apply_effects(
            self.step_count,
            self.scrubber_efficiency,
            self.power_margin_w,
            1.0,
        )

        co2_production = params["co2_production_ppm_per_step"] * co2_mult
        if self.load_reduced:
            co2_production *= params["load_reduction_factor"]

        scrub_rate = (
            self.co2_ppm
            * self.scrubber_efficiency
            * self.fan_speed
            * params.get("scrub_rate_coefficient", 0.06)
        )

        bypass_bonus = 0.0
        if self.bypass_enabled:
            bypass_bonus = params["bypass_flow_bonus"]
            if self.design.has_bypass_edge():
                bypass_bonus += 0.05
            scrub_rate *= 1.0 + bypass_bonus

        self.co2_ppm = max(400.0, self.co2_ppm + co2_production - scrub_rate)

        fan_power = params["fan_power_w"] * self.fan_speed
        bypass_power = 0.0
        if self.bypass_enabled:
            bypass_power = (
                params["permanent_bypass_power_w"]
                if self.design.has_bypass_edge()
                else params["bypass_power_w"]
            )
        # Facility loads are nameplate watts; convert with one factor so base/fan/bypass
        # share the same unit path. Anomaly power_margin_decay_per_step stays in
        # power_margin_w units (not raw watts).
        load_w = params["base_power_draw_w"] + fan_power + bypass_power
        margin_factor = float(params.get("power_draw_to_margin_factor", 0.01875))
        self.power_margin_w -= load_w * margin_factor

        if active_flags:
            self._event_log.append({"step": self.step_count, "kind": EVENT_ANOMALY, "flags": active_flags})

        return self._snapshot(active_flags)

    def apply_command(self, cmd: RecoveryCommand) -> CommandResult:
        error = validate_command(cmd)
        if error:
            return error

        if cmd.kind == CommandKind.REQUEST_EPS_BOOST:
            return CommandResult(
                success=False,
                message="request_eps_boost requires StationSimulator (EPS facade)",
            )
        self.fan_speed, self.bypass_enabled, self.load_reduced, msg = apply_command_to_state(
            cmd, self.fan_speed, self.bypass_enabled, self.load_reduced
        )
        snap = self._snapshot(self.anomalies.on_step(self.step_count))
        self._event_log.append(
            {
                "step": self.step_count,
                "kind": EVENT_RECOVERY,
                "command": cmd.to_dict(),
                "message": msg,
            }
        )
        return CommandResult(success=True, message=msg, telemetry=snap)

    def get_topology(self) -> TopologyGraph:
        return self.design.snapshot().topology

    def get_design_parameters(self) -> Dict[str, float]:
        return dict(self.design.parameters)

    def get_design_state(self) -> DesignState:
        return self.design.snapshot()

    def get_events(self) -> List[dict]:
        return list(self._event_log)

    def _snapshot(self, anomaly_flags: List[str]) -> TelemetrySnapshot:
        return TelemetrySnapshot(
            step=self.step_count,
            co2_ppm=round(self.co2_ppm, 2),
            scrubber_efficiency=round(self.scrubber_efficiency, 4),
            power_margin_w=round(self.power_margin_w, 2),
            fan_speed=round(self.fan_speed, 3),
            bypass_enabled=self.bypass_enabled,
            load_reduced=self.load_reduced,
            eps_support_w=0.0,
            eps_support_steps_remaining=0,
            anomaly_flags=list(anomaly_flags),
        )
