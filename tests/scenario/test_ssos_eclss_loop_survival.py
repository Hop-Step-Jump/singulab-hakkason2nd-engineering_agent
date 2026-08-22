"""Band-dwell survival policy (independent of physics floor)."""

from __future__ import annotations

from environment.protocol import HealthStatus
from scenario.ssos_eclss_loop.survival import SurvivalDwellPolicy, SurvivalStreaks


def _health(*, o2="safe", water="safe", co2="safe"):
    return {
        "o2_status": o2,
        "water_status": water,
        "co2_status": co2,
        "overall": HealthStatus.WARNING.value,
    }


def test_o2_and_water_warning_two_steps_lose_one():
    policy = SurvivalDwellPolicy.from_config({"survival": {"enabled": True}})
    streaks = SurvivalStreaks()
    alive, lost, limiting, streaks, _ = policy.apply_dwell(
        4, _health(o2="warning"), streaks
    )
    assert alive == 4 and lost == 0 and not limiting
    alive, lost, limiting, streaks, by_cause = policy.apply_dwell(
        alive, _health(o2="warning"), streaks
    )
    assert alive == 3 and lost == 1
    assert limiting == ["o2_warning"]
    assert by_cause == {"o2_warning": 1}

    policy2 = SurvivalDwellPolicy.from_config({"survival": {"enabled": True}})
    streaks_w = SurvivalStreaks()
    _, _, _, streaks_w, _ = policy2.apply_dwell(4, _health(water="warning"), streaks_w)
    alive, lost, _, _, by_cause = policy2.apply_dwell(
        4, _health(water="warning"), streaks_w
    )
    assert lost == 1 and alive == 3 and by_cause == {"water_warning": 1}


def test_o2_critical_minus_two_water_critical_minus_one():
    policy = SurvivalDwellPolicy.from_config({"survival": {"enabled": True}})
    alive, lost, limiting, _, by_cause = policy.apply_dwell(
        4, _health(o2="critical"), SurvivalStreaks()
    )
    assert lost == 2 and alive == 2
    assert limiting == ["o2_critical"]
    assert by_cause == {"o2_critical": 2}

    policy_w = SurvivalDwellPolicy.from_config({"survival": {"enabled": True}})
    alive, lost, _, _, by_cause = policy_w.apply_dwell(
        4, _health(water="critical"), SurvivalStreaks()
    )
    assert lost == 1 and alive == 3 and by_cause == {"water_critical": 1}


def test_warning_counter_resets_after_loss_and_on_safe():
    policy = SurvivalDwellPolicy.from_config({"survival": {"enabled": True}})
    streaks = SurvivalStreaks()
    _, _, _, streaks, _ = policy.apply_dwell(4, _health(o2="warning"), streaks)
    alive, lost, _, streaks, _ = policy.apply_dwell(4, _health(o2="warning"), streaks)
    assert lost == 1
    alive, lost, _, streaks, _ = policy.apply_dwell(alive, _health(o2="warning"), streaks)
    assert lost == 0
    _, lost, _, streaks, _ = policy.apply_dwell(alive, _health(o2="warning"), streaks)
    assert lost == 1

    _, _, _, streaks, _ = policy.apply_dwell(4, _health(o2="warning"), streaks)
    _, _, _, streaks, _ = policy.apply_dwell(4, _health(o2="safe"), streaks)
    assert streaks.o2_warning == 0


def test_critical_does_not_increment_warning_streak():
    policy = SurvivalDwellPolicy.from_config({"survival": {"enabled": True}})
    streaks = SurvivalStreaks()
    _, _, _, streaks, _ = policy.apply_dwell(4, _health(o2="warning"), streaks)
    assert streaks.o2_warning == 1
    _, _, _, streaks, _ = policy.apply_dwell(4, _health(o2="critical"), streaks)
    assert streaks.o2_warning == 0
    assert streaks.o2_critical == 0  # fired and reset


def test_co2_warning_two_steps_quarter_once_then_reenter():
    policy = SurvivalDwellPolicy.from_config({"survival": {"enabled": True}})
    streaks = SurvivalStreaks()
    alive, lost, limiting, streaks, _ = policy.apply_dwell(
        8, _health(co2="warning"), streaks
    )
    assert alive == 8 and lost == 0 and not limiting
    alive, lost, _, streaks, by_cause = policy.apply_dwell(
        alive, _health(co2="warning"), streaks
    )
    assert lost == 2 and alive == 6 and by_cause == {"co2_warning": 2}
    alive, lost, _, streaks, _ = policy.apply_dwell(alive, _health(co2="warning"), streaks)
    assert lost == 0 and alive == 6 and streaks.co2_warning_fired
    _, lost, _, streaks, _ = policy.apply_dwell(alive, _health(co2="safe"), streaks)
    assert not streaks.co2_warning_fired and streaks.co2_warning == 0
    _, _, _, streaks, _ = policy.apply_dwell(alive, _health(co2="warning"), streaks)
    alive, lost, _, _, by_cause = policy.apply_dwell(alive, _health(co2="warning"), streaks)
    assert lost == 1 and by_cause == {"co2_warning": 1} and alive == 5


def test_co2_critical_two_steps_half_once_then_reenter():
    policy = SurvivalDwellPolicy.from_config({"survival": {"enabled": True}})
    streaks = SurvivalStreaks()
    alive, lost, _, streaks, _ = policy.apply_dwell(
        8, _health(co2="critical"), streaks
    )
    assert lost == 0 and alive == 8
    alive, lost, limiting, streaks, by_cause = policy.apply_dwell(
        alive, _health(co2="critical"), streaks
    )
    assert lost == 4 and alive == 4 and by_cause == {"co2_critical": 4}
    assert limiting[0] == "co2_critical"
    alive, lost, _, streaks, _ = policy.apply_dwell(alive, _health(co2="critical"), streaks)
    assert lost == 0 and streaks.co2_critical_fired
    _, _, _, streaks, _ = policy.apply_dwell(alive, _health(co2="safe"), streaks)
    assert not streaks.co2_critical_fired
    _, _, _, streaks, _ = policy.apply_dwell(alive, _health(co2="critical"), streaks)
    alive, lost, _, _, by_cause = policy.apply_dwell(alive, _health(co2="critical"), streaks)
    assert lost == 2 and by_cause == {"co2_critical": 2}


def test_co2_n1_loses_zero_after_dwell():
    policy = SurvivalDwellPolicy.from_config({"survival": {"enabled": True}})
    streaks = SurvivalStreaks()
    _, lost, _, streaks, _ = policy.apply_dwell(1, _health(co2="warning"), streaks)
    alive, lost, limiting, streaks, _ = policy.apply_dwell(
        1, _health(co2="warning"), streaks
    )
    assert alive == 1 and lost == 0 and not limiting
    _, _, _, streaks, _ = policy.apply_dwell(1, _health(co2="critical"), streaks)
    alive, lost, _, _, _ = policy.apply_dwell(1, _health(co2="critical"), streaks)
    assert alive == 1 and lost == 0


def test_co2_critical_clears_warning_and_beats_warning():
    policy = SurvivalDwellPolicy.from_config({"survival": {"enabled": True}})
    streaks = SurvivalStreaks()
    _, _, _, streaks, _ = policy.apply_dwell(8, _health(co2="warning"), streaks)
    assert streaks.co2_warning == 1
    _, lost, _, streaks, _ = policy.apply_dwell(
        8, _health(co2="critical"), streaks
    )
    assert lost == 0
    assert streaks.co2_warning == 0 and not streaks.co2_warning_fired
    alive, lost, limiting, _, by_cause = policy.apply_dwell(
        8, _health(co2="critical", o2="warning"), streaks
    )
    assert lost == 4 and alive == 4
    assert limiting[0] == "co2_critical"
    assert by_cause == {"co2_critical": 4}


def test_stack_priority_slices_causes():
    policy = SurvivalDwellPolicy.from_config({"survival": {"enabled": True}})
    alive, lost, limiting, _, by_cause = policy.apply_dwell(
        4, _health(o2="critical", water="critical"), SurvivalStreaks()
    )
    assert lost == 3 and alive == 1
    assert limiting == ["o2_critical", "water_critical"]
    assert by_cause == {"o2_critical": 2, "water_critical": 1}
