"""Tests for mock ECLSS simulator."""

from pathlib import Path

import pytest

from environment.scrubber.eclss_ops.telemetry import compute_health_metrics, co2_health
from environment.protocol import (
    AnomalySpec,
    CommandKind,
    HealthStatus,
    RecoveryCommand,
)
from environment.scrubber.eclss_ops.design_state import DesignStateManager
from environment.scrubber.mock_eclss import MockEclssSimulator


def test_baseline_step_produces_telemetry():
    sim = MockEclssSimulator()
    snap = sim.step()
    assert snap.step == 1
    assert snap.co2_ppm > 0
    assert 0 < snap.scrubber_efficiency <= 1.0


def test_anomaly_raises_co2():
    baseline = MockEclssSimulator()
    stressed = MockEclssSimulator()
    stressed.inject_anomaly(
        AnomalySpec(
            name="test_degradation",
            start_step=5,
            scrubber_efficiency_decay_per_step=0.05,
            co2_production_multiplier=1.5,
        )
    )
    for _ in range(25):
        baseline.step()
        stressed.step()
    assert stressed.co2_ppm > baseline.co2_ppm


def test_recovery_command_reduces_co2_rise():
    sim = MockEclssSimulator()
    sim.inject_anomaly(
        AnomalySpec(name="deg", start_step=1, scrubber_efficiency_decay_per_step=0.03)
    )
    for _ in range(15):
        sim.step()
    co2_stressed = sim.co2_ppm

    sim.apply_command(RecoveryCommand(kind=CommandKind.SET_FAN_SPEED, value=1.0))
    sim.apply_command(RecoveryCommand(kind=CommandKind.ENABLE_BYPASS, value=True))
    for _ in range(10):
        sim.step()
    assert sim.co2_ppm < co2_stressed + 500  # fan+bypass should help scrub


def test_invalid_fan_speed_command_returns_failure_instead_of_crashing():
    sim = MockEclssSimulator()
    result = sim.apply_command(RecoveryCommand(kind=CommandKind.SET_FAN_SPEED, value="fast"))
    assert result.success is False
    assert "fan_speed must be numeric" in result.message


def test_design_dict_change_adds_bypass_edge():
    manager = DesignStateManager()
    state = manager.apply_dict_change(
        "add_edge",
        {"node_a": "manifold", "node_b": "scrubber", "kind": "bypass"},
    )
    assert any(e.kind == "bypass" for e in state.topology.edges)


def test_power_draw_uses_unified_margin_factor():
    sim = MockEclssSimulator(initial_power_margin_w=150.0)
    before = sim.power_margin_w
    sim.step()
    # default: (200 + 80*0.7) * 0.01875 = 4.8
    assert before - sim.power_margin_w == pytest.approx(4.8)


def test_health_metrics_critical_on_high_co2():
    sim = MockEclssSimulator(initial_co2_ppm=2500.0)
    snap = sim.step()
    health = compute_health_metrics(snap)
    assert health.co2_status == HealthStatus.CRITICAL


def test_run_mock_writes_telemetry_jsonl(tmp_path: Path):
    from scripts.run_mock_eclss import run_mock_simulation

    run_dir = run_mock_simulation(steps=10, output_dir=tmp_path / "run", inject_scrubber_anomaly=False)
    telemetry_file = run_dir / "telemetry.jsonl"
    assert telemetry_file.exists()
    lines = telemetry_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 10
    summary = run_dir / "summary.json"
    assert summary.exists()
