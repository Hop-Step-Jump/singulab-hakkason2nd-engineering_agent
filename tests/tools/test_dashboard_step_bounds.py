"""Dashboard step bounds for 0-based ssos and 1-based scrubber runs."""

from tools.dashboard.app import _max_telemetry_step, _telemetry_step_bounds


def test_telemetry_step_bounds_ssos_zero_based():
    telemetry = [{"step": 0}, {"step": 1}, {"step": 7}]
    assert _telemetry_step_bounds(telemetry) == (0, 7)
    assert _max_telemetry_step(telemetry) == 7


def test_telemetry_step_bounds_scrubber_one_based():
    telemetry = [{"step": 1}, {"step": 2}, {"step": 8}]
    assert _telemetry_step_bounds(telemetry) == (1, 8)


def test_telemetry_step_bounds_empty_defaults():
    assert _telemetry_step_bounds([]) == (1, 1)
    assert _max_telemetry_step([]) == 1


def test_telemetry_step_bounds_single_step_zero():
    assert _telemetry_step_bounds([{"step": 0}]) == (0, 0)
