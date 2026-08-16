"""Unit tests for ssos_eclss_loop subsystem failure scheduling."""

from __future__ import annotations

import pytest

from scenario.ssos_eclss_loop.loop_mock_backend import LoopMockEclssBackend
from scenario.ssos_eclss_loop.subsystem_failures import (
    EVENT_KIND,
    SubsystemFailureScheduleError,
    apply_scheduled_subsystem_failures,
    clear_scheduled_subsystem_failures,
    parse_subsystem_failure_schedule,
    resolve_failure_flags,
    resolve_inject_subsystem_failures,
)


def test_resolve_inject_flag_defaults_off():
    assert resolve_inject_subsystem_failures({}) is False
    assert resolve_inject_subsystem_failures({"inject_failures": None}) is False
    assert resolve_inject_subsystem_failures({"inject_failures": False}) is False
    assert resolve_inject_subsystem_failures({"inject_failures": True}) is True


def test_resolve_inject_flag_rejects_non_bool():
    with pytest.raises(SubsystemFailureScheduleError, match="boolean"):
        resolve_inject_subsystem_failures({"inject_failures": "yes"})


def test_parse_accepts_end_step_and_duration():
    schedule = parse_subsystem_failure_schedule(
        [
            {"subsystem": "ARS_failure", "start_step": 0, "end_step": 3},
            {"subsystem": "ogs", "start_step": 2, "duration_steps": 2},
        ]
    )
    assert schedule[0].subsystem == "ars"
    assert schedule[0].start_step == 0
    assert schedule[0].end_step == 3
    assert schedule[1].subsystem == "ogs"
    assert schedule[1].duration_steps == 2


def test_parse_rejects_both_end_and_duration():
    with pytest.raises(SubsystemFailureScheduleError, match="both end_step"):
        parse_subsystem_failure_schedule(
            [{"subsystem": "ars", "start_step": 1, "end_step": 3, "duration_steps": 2}]
        )


def test_parse_rejects_unknown_subsystem():
    with pytest.raises(SubsystemFailureScheduleError, match="thermal"):
        parse_subsystem_failure_schedule([{"subsystem": "thermal", "start_step": 0}])


def test_parse_rejects_negative_start_step():
    with pytest.raises(SubsystemFailureScheduleError, match=">= 0"):
        parse_subsystem_failure_schedule([{"subsystem": "ars", "start_step": -1}])


def test_resolve_end_step_exclusive_and_or_across_entries():
    schedule = parse_subsystem_failure_schedule(
        [
            {"subsystem": "ars", "start_step": 3, "end_step": 5},
            {"subsystem": "ars", "start_step": 7, "duration_steps": 1},
            {"subsystem": "wrs", "start_step": 4},
        ]
    )
    assert resolve_failure_flags(schedule, 2) == {"ars": False, "wrs": False}
    assert resolve_failure_flags(schedule, 3) == {"ars": True, "wrs": False}
    assert resolve_failure_flags(schedule, 4) == {"ars": True, "wrs": True}
    assert resolve_failure_flags(schedule, 5) == {"ars": False, "wrs": True}
    assert resolve_failure_flags(schedule, 7) == {"ars": True, "wrs": True}
    assert resolve_failure_flags(schedule, 8) == {"ars": False, "wrs": True}


def test_apply_emits_events_only_on_transition():
    backend = LoopMockEclssBackend(
        {"simulation": {"initial_co2_storage_kg": 1.0}, "mock_dynamics": {}}
    )
    schedule = parse_subsystem_failure_schedule(
        [{"subsystem": "ars", "start_step": 2, "end_step": 4}]
    )
    last: dict[str, bool] = {"ars": False}

    e1 = apply_scheduled_subsystem_failures(backend, schedule, 1, last_enabled=last)
    assert e1 == []
    assert backend.poll_telemetry().ars_failure_enabled is False

    e2 = apply_scheduled_subsystem_failures(backend, schedule, 2, last_enabled=last)
    assert e2 == [
        {
            "kind": EVENT_KIND,
            "subsystem": "ars",
            "enabled": True,
            "source": "subsystem_failures",
        }
    ]
    assert backend.poll_telemetry().ars_failure_enabled is True

    e3 = apply_scheduled_subsystem_failures(backend, schedule, 3, last_enabled=last)
    assert e3 == []
    assert backend.poll_telemetry().ars_failure_enabled is True

    e4 = apply_scheduled_subsystem_failures(backend, schedule, 4, last_enabled=last)
    assert e4[0]["enabled"] is False
    assert backend.poll_telemetry().ars_failure_enabled is False


def test_apply_reasserts_over_manual_clear():
    backend = LoopMockEclssBackend(
        {"simulation": {"initial_co2_storage_kg": 1.0}, "mock_dynamics": {}}
    )
    schedule = parse_subsystem_failure_schedule(
        [{"subsystem": "ogs", "start_step": 0, "end_step": 5}]
    )
    last: dict[str, bool] = {}
    apply_scheduled_subsystem_failures(backend, schedule, 0, last_enabled=last)
    backend.set_subsystem_failure("ogs", False)
    assert backend.poll_telemetry().ogs_failure_enabled is False

    apply_scheduled_subsystem_failures(backend, schedule, 1, last_enabled=last)
    assert backend.poll_telemetry().ogs_failure_enabled is True


def test_clear_scheduled_failures_resets_all_owned_subsystems():
    backend = LoopMockEclssBackend(
        {"simulation": {"initial_co2_storage_kg": 1.0}, "mock_dynamics": {}}
    )
    schedule = parse_subsystem_failure_schedule(
        [
            {"subsystem": "ars", "start_step": 0},
            {"subsystem": "wrs", "start_step": 0},
        ]
    )
    apply_scheduled_subsystem_failures(backend, schedule, 0, last_enabled={})
    assert backend.poll_telemetry().ars_failure_enabled is True
    assert backend.poll_telemetry().wrs_failure_enabled is True

    clear_scheduled_subsystem_failures(backend, schedule)

    snap = backend.poll_telemetry()
    assert snap.ars_failure_enabled is False
    assert snap.wrs_failure_enabled is False
