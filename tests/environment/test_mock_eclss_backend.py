"""Contract tests for MockEclssBackend (Phase 1b)."""

import pytest

from environment.ssos.eclss.backend import EclssBackend
from environment.ssos.eclss.types import ArsGoal, OgsGoal, WrsGoal
from environment.ssos.eclss.mock.backend import MockEclssBackend


def test_mock_backend_satisfies_protocol():
    backend = MockEclssBackend()
    assert isinstance(backend, EclssBackend)


def test_mock_poll_telemetry_returns_defaults():
    snap = MockEclssBackend().poll_telemetry()
    assert snap.co2_storage_kg == 1.8
    assert snap.o2_storage_kg == 0.5
    assert snap.product_water_reserve_l == 100.0


def test_mock_ars_and_ogs_goals():
    backend = MockEclssBackend()
    ars = backend.send_air_revitalisation_goal(ArsGoal(initial_co2_mass=0.9))
    ogs = backend.send_oxygen_generation_goal(OgsGoal(input_water_mass=0.01))
    assert ars.success
    assert ogs.success
    assert backend.last_ars_goal.initial_co2_mass == 0.9
    assert backend.last_ogs_goal.input_water_mass == 0.01


def test_mock_o2_and_co2_services():
    backend = MockEclssBackend()
    o2 = backend.request_o2(0.25)
    co2 = backend.request_co2(0.1)
    assert o2.success and o2.response_value == 0.25
    assert co2.success and co2.response_value == 0.1


def test_mock_set_subsystem_failure():
    backend = MockEclssBackend()
    backend.set_subsystem_failure("ars", True)
    snap = backend.poll_telemetry()
    assert snap.ars_failure_enabled is True


def test_mock_wrs_water_tradeoffs():
    backend = MockEclssBackend()
    before = backend.poll_telemetry()
    assert before.product_water_reserve_l == 100.0
    assert before.grey_water_collected_l == 0.0

    backend.submit_grey_water(4.0)
    assert backend.poll_telemetry().grey_water_collected_l == 4.0

    wrs = backend.send_water_recovery_goal(WrsGoal(urine_volume=2.0))
    assert wrs.success
    assert backend.last_wrs_goal.urine_volume == 2.0
    after_recovery = backend.poll_telemetry()
    assert after_recovery.product_water_reserve_l > before.product_water_reserve_l

    product = backend.request_product_water(10.0)
    assert product.success
    assert product.response_value == 10.0
    after_drink = backend.poll_telemetry()
    assert after_drink.product_water_reserve_l == after_recovery.product_water_reserve_l - 10.0

    water_kg = 5.0
    ogs = backend.send_oxygen_generation_goal(OgsGoal(input_water_mass=water_kg))
    assert ogs.success
    assert ogs.details["total_o2_generated"] == pytest.approx(0.12)
    after_ogs = backend.poll_telemetry()
    assert after_ogs.product_water_reserve_l == after_drink.product_water_reserve_l - water_kg


def test_mock_request_product_water_insufficient_reserve():
    backend = MockEclssBackend()
    backend._telemetry.product_water_reserve_l = 2.0
    result = backend.request_product_water(5.0)
    assert result.success is False
    assert result.response_value == 2.0
    assert backend.poll_telemetry().product_water_reserve_l == 0.0
