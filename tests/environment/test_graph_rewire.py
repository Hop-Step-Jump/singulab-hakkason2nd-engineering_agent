"""Tests for ssos_graph.rewires runtime remapping."""

import subprocess

import pytest

from environment.ssos.eclss.ros2.graph_rewire import build_topic_remap, remap_name
from environment.ssos.eclss.ros2.bridge import Ros2EclssBridge


def test_build_topic_remap_from_rewires():
    rewires = [
        {"public": "/co2_storage", "backend": "/plant/co2_storage"},
        {"public": "/grey_water", "backend": "/waste/grey_water"},
    ]
    remap = build_topic_remap(rewires)
    assert remap["/co2_storage"] == "/plant/co2_storage"
    assert remap["/grey_water"] == "/waste/grey_water"


def test_remap_name_with_and_without_leading_slash():
    remap = {"/co2_storage": "/plant/co2_storage"}
    assert remap_name("/co2_storage", remap) == "/plant/co2_storage"
    assert remap_name("co2_storage", remap) == "/plant/co2_storage"


@pytest.fixture(autouse=True)
def _force_cli_telemetry(monkeypatch):
    monkeypatch.setenv("SSOS_ECLSS_FORCE_CLI_TELEMETRY", "1")


def test_ros2_bridge_poll_uses_remapped_topics(monkeypatch):
    remap = {"/co2_storage": "/plant/co2_storage"}
    seen_topics: list[str] = []

    def fake_run(args, **_kwargs):
        if len(args) > 3 and args[1] == "topic":
            topic = args[3]
            seen_topics.append(topic)
            body = {
                "/plant/co2_storage": "data: 99.0\n",
                "/o2_storage": "data: 50.0\n",
                "/wrs/product_water_reserve": "data: 10.0\n",
            }.get(topic, "")
            return subprocess.CompletedProcess(args, 0, body, "")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr("environment.ssos.ros2.cli.subprocess.run", fake_run)
    snap = Ros2EclssBridge(topic_remap=remap).poll_telemetry()
    assert "/plant/co2_storage" in seen_topics
    assert snap.co2_storage_kg == pytest.approx(0.099)
    assert snap.o2_storage_kg == pytest.approx(0.05)


def test_build_eclss_backend_passes_rewires(tmp_path):
    from scenario.ssos_eclss_loop.scenario_run import build_eclss_backend

    config = {
        "backend": {"kind": "ros2"},
        "ssos_graph": {
            "rewires": [{"public": "/co2_storage", "backend": "/alias/co2"}],
        },
    }
    backend = build_eclss_backend(config)
    assert backend._topic_remap["/co2_storage"] == "/alias/co2"
