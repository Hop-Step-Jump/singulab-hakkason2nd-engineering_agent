"""Contract and integration tests for Ros2EclssBridge (Phase 1b)."""

import subprocess
import threading

import pytest

from environment.ssos.eclss.backend import EclssBackend
from environment.ssos.eclss.types import ArsGoal, OgsGoal, WrsGoal
from environment.ssos.eclss.ros2.bridge import Ros2EclssBridge
from environment.ssos.ros2.cli import echo_float_topic, run_ros2_cli


@pytest.fixture(autouse=True)
def _force_cli_telemetry(monkeypatch):
    """Keep existing CLI mocks effective when rclpy is installed on the host."""
    monkeypatch.setenv("SSOS_ECLSS_FORCE_CLI_TELEMETRY", "1")


def test_ros2_bridge_satisfies_protocol():
    assert isinstance(Ros2EclssBridge(), EclssBackend)


def test_ros2_available_false_when_cli_missing(monkeypatch):
    def fake_run(*_args, **_kwargs):
        raise FileNotFoundError("ros2")

    monkeypatch.setattr("environment.ssos.ros2.cli.subprocess.run", fake_run)
    assert Ros2EclssBridge.ros2_available() is False


def test_poll_telemetry_parses_jazzy_repr_float_topics(monkeypatch):
    responses = {
        ("/co2_storage",): "std_msgs.msg.Float64(data=1234.5)\n",
        ("/o2_storage",): "std_msgs.msg.Float64(data=678.0)\n",
        ("/wrs/product_water_reserve",): "std_msgs.msg.Float64(data=42.0)\n",
    }

    def fake_run(args, **_kwargs):
        topic = args[3] if len(args) > 3 and args[1] == "topic" else ""
        body = responses.get((topic,), "")
        return subprocess.CompletedProcess(args, 0, body, "")

    monkeypatch.setattr("environment.ssos.ros2.cli.subprocess.run", fake_run)
    snap = Ros2EclssBridge().poll_telemetry()
    assert snap.co2_storage_kg == pytest.approx(1.2345)
    assert snap.o2_storage_kg == pytest.approx(0.678)
    assert snap.product_water_reserve_l == 42.0


def test_run_ros2_cli_wraps_when_pythonpath_set(monkeypatch):
    captured: dict[str, object] = {}

    def fake_run(cmd, **_kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, "ok", "")

    monkeypatch.setenv("PYTHONPATH", "/opt/engineering_agents/src")
    monkeypatch.setenv("ROS_DISTRO", "jazzy")
    monkeypatch.setattr("environment.ssos.ros2.cli.subprocess.run", fake_run)
    code, out, _err = run_ros2_cli(["topic", "list"], timeout_s=5.0)
    assert code == 0
    assert out == "ok"
    assert captured["cmd"][0] == "bash"
    assert captured["cmd"][1] == "-c"
    script = captured["cmd"][2]
    assert "source /opt/ros/jazzy/setup.bash" in script
    assert "ros2 topic list" in script


def test_poll_telemetry_parses_float_topics(monkeypatch):
    responses = {
        ("/co2_storage",): "data: 1234.5\n",
        ("/o2_storage",): "data: 678.0\n",
        ("/wrs/product_water_reserve",): "data: 42.0\n",
    }

    def fake_run(args, **_kwargs):
        topic = args[3] if len(args) > 3 and args[1] == "topic" else ""
        body = responses.get((topic,), "")
        return subprocess.CompletedProcess(args, 0, body, "")

    monkeypatch.setattr("environment.ssos.ros2.cli.subprocess.run", fake_run)
    snap = Ros2EclssBridge().poll_telemetry()
    assert snap.co2_storage_kg == pytest.approx(1.2345)
    assert snap.o2_storage_kg == pytest.approx(0.678)
    assert snap.product_water_reserve_l == 42.0


def test_parallel_cli_poll_runs_echoes_concurrently(monkeypatch):
    import time

    active = 0
    peak = 0
    lock = threading.Lock()

    def fake_run(args, **_kwargs):
        nonlocal active, peak
        cmd = args
        if cmd and cmd[0] == "bash" and len(cmd) > 2:
            script = cmd[2]
            is_echo = "ros2 topic echo" in script
            topic = ""
            if is_echo:
                for candidate in ("/co2_storage", "/o2_storage", "/wrs/product_water_reserve"):
                    if candidate in script:
                        topic = candidate
                        break
        elif len(args) > 3 and args[1] == "topic" and args[2] == "echo":
            is_echo = True
            topic = args[3]
        else:
            is_echo = False
            topic = ""

        if is_echo:
            with lock:
                active += 1
                peak = max(peak, active)
            try:
                time.sleep(0.05)
                value = {
                    "/co2_storage": 1.0,
                    "/o2_storage": 2.0,
                    "/wrs/product_water_reserve": 3.0,
                }[topic]
                return subprocess.CompletedProcess(args, 0, f"data: {value}\n", "")
            finally:
                with lock:
                    active -= 1
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr("environment.ssos.ros2.cli.subprocess.run", fake_run)
    snap = Ros2EclssBridge().poll_telemetry()
    assert peak >= 2
    assert snap.co2_storage_kg == pytest.approx(0.001)
    assert snap.o2_storage_kg == pytest.approx(0.002)
    assert snap.product_water_reserve_l == 3.0


def test_poll_uses_rclpy_reader_when_available(monkeypatch):
    monkeypatch.delenv("SSOS_ECLSS_FORCE_CLI_TELEMETRY", raising=False)

    class _FakeReader:
        def read_fresh(self, wait_timeout_s: float, *, max_age_s: float):
            assert wait_timeout_s == 7.5
            assert max_age_s == 15.0
            return 10.0, 20.0, 30.0

    monkeypatch.setattr(
        "environment.ssos.eclss.ros2.bridge.get_rclpy_telemetry_reader",
        lambda: _FakeReader(),
    )
    snap = Ros2EclssBridge(topic_timeout_s=7.5, telemetry_max_age_s=15.0).poll_telemetry()
    assert snap.co2_storage_kg == pytest.approx(0.01)
    assert snap.o2_storage_kg == pytest.approx(0.02)
    assert snap.product_water_reserve_l == 30.0


def test_request_o2_parses_service_response(monkeypatch):
    captured = {}

    def fake_run(args, **_kwargs):
        assert args[0:2] == ["ros2", "service"]
        captured["args"] = list(args)
        return subprocess.CompletedProcess(
            args,
            0,
            "response:\n  o2_resp: 500.0\n  success: true\n  message: 'ok'\n",
            "",
        )

    monkeypatch.setattr("environment.ssos.ros2.cli.subprocess.run", fake_run)
    result = Ros2EclssBridge().request_o2(0.5)
    assert "o2_req: 500.0" in captured["args"][-1]
    assert result.success
    assert result.response_value == pytest.approx(0.5)
    assert result.message == "ok"


def test_request_co2_parses_service_response(monkeypatch):
    captured = {}

    def fake_run(args, **_kwargs):
        captured["args"] = list(args)
        return subprocess.CompletedProcess(
            args,
            0,
            "response:\n  co2_resp: 120.0\n  success: true\n  message: 'delivered'\n",
            "",
        )

    monkeypatch.setattr("environment.ssos.ros2.cli.subprocess.run", fake_run)
    result = Ros2EclssBridge().request_co2(0.12)
    assert "co2_req: 120.0" in captured["args"][-1]
    assert result.success
    assert result.response_value == pytest.approx(0.12)


def test_request_co2_parses_jazzy_repr_service_response(monkeypatch):
    def fake_run(args, **_kwargs):
        return subprocess.CompletedProcess(
            args,
            0,
            (
                "response:\n"
                "space_station_interfaces.srv.Co2Request_Response("
                "co2_resp=50.0, success=True, message='CO2 successfully delivered')\n"
            ),
            "",
        )

    monkeypatch.setattr("environment.ssos.ros2.cli.subprocess.run", fake_run)
    result = Ros2EclssBridge().request_co2(0.05)
    assert result.success
    assert result.response_value == pytest.approx(0.05)
    assert result.message == "CO2 successfully delivered"


def test_request_o2_parses_jazzy_repr_insufficient_storage(monkeypatch):
    def fake_run(args, **_kwargs):
        return subprocess.CompletedProcess(
            args,
            0,
            (
                "response:\n"
                "space_station_interfaces.srv.O2Request_Response("
                "o2_resp=0.0, success=False, message='Insufficient O2 in storage')\n"
            ),
            "",
        )

    monkeypatch.setattr("environment.ssos.ros2.cli.subprocess.run", fake_run)
    result = Ros2EclssBridge().request_o2(0.1)
    assert result.success is False
    assert result.response_value == 0.0
    assert "Insufficient" in result.message


def test_poll_telemetry_includes_failure_flags_after_set(monkeypatch):
    def fake_run(args, **_kwargs):
        if len(args) > 3 and args[1] == "topic" and args[2] == "echo":
            return subprocess.CompletedProcess(args, 0, "data: 100.0\n", "")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr("environment.ssos.ros2.cli.subprocess.run", fake_run)
    bridge = Ros2EclssBridge()
    bridge.set_subsystem_failure("ogs", True)
    snap = bridge.poll_telemetry()
    assert snap.ogs_failure_enabled is True
    assert snap.ars_failure_enabled is False
    assert snap.co2_storage_kg == pytest.approx(0.1)


def test_send_oxygen_generation_goal_parses_action_result(monkeypatch):
    captured = {}

    def fake_run(args, **_kwargs):
        assert "/oxygen_generation" in args
        captured["args"] = list(args)
        return subprocess.CompletedProcess(
            args,
            0,
            "Goal finished with status: SUCCEEDED\n"
            "Result:\n  success: true\n"
            "  total_o2_generated: 88.0\n"
            "  summary_message: 'done'\n",
            "",
        )

    monkeypatch.setattr("environment.ssos.ros2.cli.subprocess.run", fake_run)
    result = Ros2EclssBridge().send_oxygen_generation_goal(OgsGoal(input_water_mass=0.015))
    assert "input_water_mass: 15.0" in captured["args"][-1]
    assert result.success
    assert result.details.get("total_o2_generated") == pytest.approx(0.088)


def test_set_subsystem_failure_publishes_bool(monkeypatch):
    captured = {}

    def fake_run(args, **_kwargs):
        captured["args"] = list(args)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr("environment.ssos.ros2.cli.subprocess.run", fake_run)
    Ros2EclssBridge().set_subsystem_failure("ogs", True)
    assert captured["args"][1:5] == ["topic", "pub", "--once", "/ogs/self_diagnosis"]
    assert "{data: true}" in captured["args"][-1]


def test_send_water_recovery_goal_parses_action_result(monkeypatch):
    def fake_run(args, **_kwargs):
        assert "/water_recovery_systems" in args
        return subprocess.CompletedProcess(
            args,
            0,
            "Goal finished with status: SUCCEEDED\n"
            "Result:\n  success: true\n"
            "  total_purified_water: 1.68\n"
            "  total_cycles: 1\n"
            "  summary_message: 'done'\n",
            "",
        )

    monkeypatch.setattr("environment.ssos.ros2.cli.subprocess.run", fake_run)
    result = Ros2EclssBridge().send_water_recovery_goal(WrsGoal(urine_volume=2.0))
    assert result.success
    assert result.details.get("total_purified_water") == 1.68
    assert result.details.get("total_cycles") == 1.0


def test_request_product_water_parses_service_response(monkeypatch):
    def fake_run(args, **_kwargs):
        return subprocess.CompletedProcess(
            args,
            0,
            "response:\n  water_granted: 4.5\n  success: true\n  message: 'ok'\n",
            "",
        )

    monkeypatch.setattr("environment.ssos.ros2.cli.subprocess.run", fake_run)
    result = Ros2EclssBridge().request_product_water(5.0)
    assert result.success
    assert result.response_value == 4.5


def test_request_product_water_parses_jazzy_repr(monkeypatch):
    def fake_run(args, **_kwargs):
        return subprocess.CompletedProcess(
            args,
            0,
            (
                "response:\n"
                "space_station_interfaces.srv.RequestProductWater_Response("
                "water_granted=3.0, success=True, message='Water delivered')\n"
            ),
            "",
        )

    monkeypatch.setattr("environment.ssos.ros2.cli.subprocess.run", fake_run)
    result = Ros2EclssBridge().request_product_water(3.0)
    assert result.success
    assert result.response_value == 3.0
    assert result.message == "Water delivered"


def test_submit_grey_water_parses_service_response(monkeypatch):
    def fake_run(args, **_kwargs):
        assert "gray_water_liters" in args[-1]
        return subprocess.CompletedProcess(
            args,
            0,
            "response:\n  success: true\n  message: 'accepted'\n",
            "",
        )

    monkeypatch.setattr("environment.ssos.ros2.cli.subprocess.run", fake_run)
    result = Ros2EclssBridge().submit_grey_water(2.5)
    assert result.success
    assert result.message == "accepted"


def test_submit_grey_water_parses_jazzy_repr(monkeypatch):
    def fake_run(args, **_kwargs):
        return subprocess.CompletedProcess(
            args,
            0,
            (
                "response:\n"
                "space_station_interfaces.srv.GreyWater_Response("
                "success=True, message='Grey water received')\n"
            ),
            "",
        )

    monkeypatch.setattr("environment.ssos.ros2.cli.subprocess.run", fake_run)
    result = Ros2EclssBridge().submit_grey_water(1.0)
    assert result.success
    assert result.message == "Grey water received"


@pytest.mark.skipif(not Ros2EclssBridge.ros2_available(), reason="ros2 CLI not available")
def test_integration_poll_telemetry_when_eclss_running():
    """Requires SSOS ECLSS stack running (Docker). Skips on dev machines without ros2."""
    snap = Ros2EclssBridge(topic_timeout_s=5.0).poll_telemetry()
    # At least one storage topic should respond when ECLSS is up; otherwise fields stay None.
    assert snap.co2_storage_kg is not None or snap.o2_storage_kg is not None or snap.raw_topics == {}


@pytest.mark.skipif(not Ros2EclssBridge.ros2_available(), reason="ros2 CLI not available")
def test_integration_ros_graph_lists_eclss_interfaces():
    code, out, _ = run_ros2_cli(["topic", "list"], timeout_s=10.0)
    assert code == 0
    topics = set(out.splitlines())
    # When ECLSS is not running this still passes (empty or partial graph).
    if "/co2_storage" in topics:
        value = echo_float_topic("/co2_storage", timeout_s=5.0)
        assert value is not None
