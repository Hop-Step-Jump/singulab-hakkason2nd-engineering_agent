"""ROS 2 bridge to SSOS ECLSS (ARS + OGS + WRS).

Telemetry uses a persistent ``rclpy`` subscriber when available; otherwise
parallel ``ros2 topic echo`` CLI calls. Actions and services stay CLI-based so
the bridge works in the SSOS Docker container without extra pip dependencies.
"""

from __future__ import annotations

import os
import subprocess
from typing import Mapping, Optional, Tuple

from environment.ssos.ros2.cli import (
    echo_float_topics_parallel,
    extract_bool,
    extract_float,
    extract_service_field_float,
    extract_service_message,
    extract_service_success,
    extract_string,
    run_ros2_cli,
)
from environment.ssos.eclss.ros2.graph_rewire import remap_name
from environment.ssos.eclss.ros2.telemetry import get_rclpy_telemetry_reader
from environment.ssos.eclss.ros2.topics import (
    ACTION_AIR_REVITALISATION,
    ACTION_OXYGEN_GENERATION,
    ACTION_WATER_RECOVERY,
    ACTION_TYPE_AIR_REVITALISATION,
    ACTION_TYPE_OXYGEN_GENERATION,
    ACTION_TYPE_WATER_RECOVERY,
    MSG_TYPE_BOOL,
    SERVICE_ARS_REQUEST_CO2,
    SERVICE_GREY_WATER,
    SERVICE_OGS_REQUEST_O2,
    SERVICE_WRS_PRODUCT_WATER,
    SERVICE_TYPE_CO2_REQUEST,
    SERVICE_TYPE_GREY_WATER,
    SERVICE_TYPE_O2_REQUEST,
    SERVICE_TYPE_PRODUCT_WATER,
    TOPIC_ARS_SELF_DIAGNOSIS,
    TOPIC_CO2_STORAGE,
    TOPIC_O2_STORAGE,
    TOPIC_OGS_SELF_DIAGNOSIS,
    TOPIC_WRS_PRODUCT_WATER_RESERVE,
    TOPIC_WRS_SELF_DIAGNOSIS,
    ros_cli_action_name,
)
from environment.ssos.eclss.types import (
    ActionResult,
    ArsGoal,
    EclssTelemetrySnapshot,
    OgsGoal,
    ServiceResult,
    WrsGoal,
)
from environment.ssos.eclss.units import mass_g_to_kg, mass_kg_to_g

_SELF_DIAGNOSIS_BY_SUBSYSTEM = {
    "ars": TOPIC_ARS_SELF_DIAGNOSIS,
    "ogs": TOPIC_OGS_SELF_DIAGNOSIS,
    "wrs": TOPIC_WRS_SELF_DIAGNOSIS,
}


def _force_cli_telemetry() -> bool:
    return os.environ.get("SSOS_ECLSS_FORCE_CLI_TELEMETRY", "").lower() in {"1", "true", "yes"}


class Ros2EclssBridge:
    """EclssBackend implementation backed by SSOS ROS 2 graph."""

    def __init__(
        self,
        *,
        action_timeout_s: float = 120.0,
        service_timeout_s: float = 30.0,
        topic_timeout_s: float = 10.0,
        telemetry_max_age_s: Optional[float] = None,
        topic_remap: Optional[Mapping[str, str]] = None,
    ) -> None:
        self.action_timeout_s = action_timeout_s
        self.service_timeout_s = service_timeout_s
        self.topic_timeout_s = topic_timeout_s
        self.telemetry_max_age_s = (
            topic_timeout_s if telemetry_max_age_s is None else telemetry_max_age_s
        )
        self._topic_remap = dict(topic_remap or {})
        self._failure_flags: dict[str, bool] = {
            "ars": False,
            "ogs": False,
            "wrs": False,
        }

    def _ros_name(self, public_name: str) -> str:
        return remap_name(public_name, self._topic_remap)

    @staticmethod
    def ros2_available() -> bool:
        try:
            code, _, _ = run_ros2_cli(["--help"], timeout_s=5.0)
            return code == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def poll_telemetry(self) -> EclssTelemetrySnapshot:
        co2: Optional[float]
        o2: Optional[float]
        water: Optional[float]

        if not _force_cli_telemetry() and not self._topic_remap:
            reader = get_rclpy_telemetry_reader()
            if reader is not None:
                co2, o2, water = reader.read_fresh(
                    wait_timeout_s=self.topic_timeout_s,
                    max_age_s=self.telemetry_max_age_s,
                )
            else:
                co2, o2, water = self._poll_telemetry_cli()
        else:
            co2, o2, water = self._poll_telemetry_cli()

        # SSOS mass topics publish grams; expose kilograms internally.
        co2_kg = mass_g_to_kg(co2) if co2 is not None else None
        o2_kg = mass_g_to_kg(o2) if o2 is not None else None

        raw: dict[str, object] = {}
        if co2 is not None:
            raw[TOPIC_CO2_STORAGE] = co2
        if o2 is not None:
            raw[TOPIC_O2_STORAGE] = o2
        if water is not None:
            raw[TOPIC_WRS_PRODUCT_WATER_RESERVE] = water
        return EclssTelemetrySnapshot(
            co2_storage_kg=co2_kg,
            o2_storage_kg=o2_kg,
            product_water_reserve_l=water,
            ars_failure_enabled=self._failure_flags["ars"],
            ogs_failure_enabled=self._failure_flags["ogs"],
            wrs_failure_enabled=self._failure_flags["wrs"],
            raw_topics=raw,
        )

    def _poll_telemetry_cli(self) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        backend_topics = (
            self._ros_name(TOPIC_CO2_STORAGE),
            self._ros_name(TOPIC_O2_STORAGE),
            self._ros_name(TOPIC_WRS_PRODUCT_WATER_RESERVE),
        )
        values = echo_float_topics_parallel(backend_topics, timeout_s=self.topic_timeout_s)
        return (
            values.get(backend_topics[0]),
            values.get(backend_topics[1]),
            values.get(backend_topics[2]),
        )

    def send_air_revitalisation_goal(self, goal: ArsGoal) -> ActionResult:
        # SSOS action fields expect grams for CO₂ mass.
        goal_yaml = (
            f"{{initial_co2_mass: {mass_kg_to_g(goal.initial_co2_mass)}, "
            f"initial_moisture_content: {goal.initial_moisture_content}, "
            f"initial_contaminants: {goal.initial_contaminants}}}"
        )
        combined, err = self._send_action_goal(
            self._ros_name(ACTION_AIR_REVITALISATION),
            ACTION_TYPE_AIR_REVITALISATION,
            goal_yaml,
        )
        if err:
            return ActionResult(success=False, summary_message=err)
        success = "Goal finished with status: SUCCEEDED" in combined or "Result:" in combined
        summary = extract_string(combined, r"summary_message:\s*'([^']*)'") or extract_string(
            combined, r'summary_message:\s*"([^"]*)"'
        )
        co2_vented_g = extract_float(combined, r"total_co2_vented:\s*([-+]?[0-9]*\.?[0-9]+)")
        return ActionResult(
            success=success,
            summary_message=summary or "",
            details={
                "cycles_completed": extract_float(combined, r"cycles_completed:\s*([-+]?[0-9]*\.?[0-9]+)"),
                "total_vents": extract_float(combined, r"total_vents:\s*([-+]?[0-9]*\.?[0-9]+)"),
                "total_co2_vented": mass_g_to_kg(co2_vented_g) if co2_vented_g is not None else None,
            },
        )

    def send_oxygen_generation_goal(self, goal: OgsGoal) -> ActionResult:
        # SSOS action fields expect grams for water mass; O₂/CH₄ results are grams.
        goal_yaml = (
            f"{{input_water_mass: {mass_kg_to_g(goal.input_water_mass)}, "
            f"iodine_concentration: {goal.iodine_concentration}}}"
        )
        combined, err = self._send_action_goal(
            self._ros_name(ACTION_OXYGEN_GENERATION),
            ACTION_TYPE_OXYGEN_GENERATION,
            goal_yaml,
        )
        if err:
            return ActionResult(success=False, summary_message=err)
        success = "Goal finished with status: SUCCEEDED" in combined or "Result:" in combined
        summary = extract_string(combined, r"summary_message:\s*'([^']*)'") or extract_string(
            combined, r'summary_message:\s*"([^"]*)"'
        )
        o2_g = extract_float(combined, r"total_o2_generated:\s*([-+]?[0-9]*\.?[0-9]+)")
        ch4_g = extract_float(combined, r"total_ch4_vented:\s*([-+]?[0-9]*\.?[0-9]+)")
        return ActionResult(
            success=success,
            summary_message=summary or "",
            details={
                "total_o2_generated": mass_g_to_kg(o2_g) if o2_g is not None else None,
                "total_ch4_vented": mass_g_to_kg(ch4_g) if ch4_g is not None else None,
            },
        )

    def send_water_recovery_goal(self, goal: WrsGoal) -> ActionResult:
        goal_yaml = f"{{urine_volume: {goal.urine_volume}}}"
        combined, err = self._send_action_goal(
            self._ros_name(ACTION_WATER_RECOVERY),
            ACTION_TYPE_WATER_RECOVERY,
            goal_yaml,
        )
        if err:
            return ActionResult(success=False, summary_message=err)
        success = "Goal finished with status: SUCCEEDED" in combined or "Result:" in combined
        summary = extract_string(combined, r"summary_message:\s*'([^']*)'") or extract_string(
            combined, r'summary_message:\s*"([^"]*)"'
        )
        return ActionResult(
            success=success,
            summary_message=summary or "",
            details={
                "total_purified_water": extract_float(
                    combined, r"total_purified_water:\s*([-+]?[0-9]*\.?[0-9]+)"
                ),
                "total_cycles": extract_float(combined, r"total_cycles:\s*([-+]?[0-9]*\.?[0-9]+)"),
            },
        )

    def request_o2(self, amount: float) -> ServiceResult:
        result = self._call_service(
            self._ros_name(SERVICE_OGS_REQUEST_O2),
            SERVICE_TYPE_O2_REQUEST,
            f"{{o2_req: {mass_kg_to_g(amount)}}}",
            response_field="o2_resp",
        )
        return ServiceResult(
            success=result.success,
            response_value=mass_g_to_kg(result.response_value),
            message=result.message,
        )

    def request_co2(self, amount: float) -> ServiceResult:
        result = self._call_service(
            self._ros_name(SERVICE_ARS_REQUEST_CO2),
            SERVICE_TYPE_CO2_REQUEST,
            f"{{co2_req: {mass_kg_to_g(amount)}}}",
            response_field="co2_resp",
        )
        return ServiceResult(
            success=result.success,
            response_value=mass_g_to_kg(result.response_value),
            message=result.message,
        )

    def request_product_water(self, liters: float) -> ServiceResult:
        return self._call_service(
            self._ros_name(SERVICE_WRS_PRODUCT_WATER),
            SERVICE_TYPE_PRODUCT_WATER,
            f"{{amount: {liters}}}",
            response_field="water_granted",
        )

    def submit_grey_water(self, liters: float) -> ServiceResult:
        return self._call_service(
            self._ros_name(SERVICE_GREY_WATER),
            SERVICE_TYPE_GREY_WATER,
            f"{{gray_water_liters: {liters}}}",
        )

    def set_subsystem_failure(self, subsystem: str, enabled: bool) -> None:
        key = subsystem.lower().removesuffix("_failure")
        topic = _SELF_DIAGNOSIS_BY_SUBSYSTEM.get(key)
        if topic is None:
            raise ValueError(f"unknown subsystem: {subsystem!r}")
        ros_topic = self._ros_name(topic)
        payload = f"{{data: {'true' if enabled else 'false'}}}"
        code, out, err = run_ros2_cli(
            ["topic", "pub", "--once", ros_topic, MSG_TYPE_BOOL, payload],
            timeout_s=self.service_timeout_s,
        )
        if code != 0:
            raise RuntimeError(err or out or f"ros2 topic pub exited {code}")
        self._failure_flags[key] = enabled

    def _send_action_goal(
        self,
        action_name: str,
        action_type: str,
        goal_yaml: str,
    ) -> Tuple[str, Optional[str]]:
        try:
            code, out, err = run_ros2_cli(
                [
                    "action",
                    "send_goal",
                    "--feedback",
                    ros_cli_action_name(action_name),
                    action_type,
                    goal_yaml,
                ],
                timeout_s=self.action_timeout_s,
            )
        except FileNotFoundError:
            return "", "ros2 CLI not found"
        except subprocess.TimeoutExpired:
            return "", f"action goal timed out after {self.action_timeout_s}s"

        combined = f"{out}\n{err}"
        if code != 0:
            return combined, combined.strip() or f"ros2 action send_goal exited {code}"
        return combined, None

    def _call_service(
        self,
        service_name: str,
        service_type: str,
        request_yaml: str,
        *,
        response_field: Optional[str] = None,
    ) -> ServiceResult:
        try:
            code, out, err = run_ros2_cli(
                ["service", "call", service_name, service_type, request_yaml],
                timeout_s=self.service_timeout_s,
            )
        except FileNotFoundError:
            return ServiceResult(success=False, message="ros2 CLI not found")
        except subprocess.TimeoutExpired:
            return ServiceResult(success=False, message=f"service call timed out after {self.service_timeout_s}s")

        combined = f"{out}\n{err}"
        if code != 0:
            return ServiceResult(success=False, message=combined.strip() or f"ros2 service call exited {code}")

        success = extract_service_success(combined) or False
        response_value = (
            extract_service_field_float(combined, response_field) or 0.0
            if response_field
            else 0.0
        )
        message = extract_service_message(combined)
        return ServiceResult(success=success, response_value=response_value, message=message or "")


# Re-export CLI helpers for tests that imported from this module historically.
from environment.ssos.ros2.cli import echo_float_topic as _echo_float_topic
from environment.ssos.ros2.cli import run_ros2_cli as _run_ros2_cli
