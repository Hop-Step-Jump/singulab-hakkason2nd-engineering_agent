"""Scheduled subsystem failure injection for ssos_eclss_loop.

Scenario-layer schedule: calls ``EclssBackend.set_subsystem_failure`` at
configured steps. Distinct from scrubber ``anomalies:`` / ``inject_anomaly``.

YAML (under scenario config)::

    inject_failures: false   # default off; CLI --inject-failures
    subsystem_failures:
      - subsystem: ars          # ars | ogs | wrs
        start_step: 3           # inclusive, 0-based
        end_step: 6             # optional, exclusive
        # duration_steps: 3     # optional alternative to end_step

A subsystem listed in any entry is owned by the schedule for the whole run:
when no entry is active at the current step, the failure flag is cleared.
The schedule is applied only when ``inject_failures`` is true.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence

from environment.ssos.eclss.backend import EclssBackend

_VALID_SUBSYSTEMS = frozenset({"ars", "ogs", "wrs"})
EVENT_KIND = "subsystem_failure_applied"


class SubsystemFailureScheduleError(ValueError):
    """Invalid ``subsystem_failures`` configuration."""


@dataclass(frozen=True)
class SubsystemFailureEntry:
    subsystem: str
    start_step: int
    end_step: Optional[int] = None
    duration_steps: Optional[int] = None

    def is_active(self, step: int) -> bool:
        if step < self.start_step:
            return False
        if self.end_step is not None:
            return step < self.end_step
        if self.duration_steps is not None:
            return step < self.start_step + self.duration_steps
        return True


def resolve_inject_subsystem_failures(config: Mapping[str, Any]) -> bool:
    """Return whether the ``subsystem_failures`` schedule should be applied."""
    raw = config.get("inject_failures", False)
    if raw is None:
        return False
    if not isinstance(raw, bool):
        raise SubsystemFailureScheduleError("inject_failures must be a boolean")
    return raw


def parse_subsystem_failure_schedule(
    raw: Any,
) -> List[SubsystemFailureEntry]:
    """Parse and validate ``subsystem_failures`` from scenario config."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise SubsystemFailureScheduleError(
            "subsystem_failures must be a list of schedule entries"
        )
    entries: List[SubsystemFailureEntry] = []
    for index, item in enumerate(raw):
        entries.append(_parse_entry(item, index=index))
    return entries


def _parse_entry(item: Any, *, index: int) -> SubsystemFailureEntry:
    if not isinstance(item, Mapping):
        raise SubsystemFailureScheduleError(
            f"subsystem_failures[{index}] must be a mapping"
        )
    subsystem_raw = item.get("subsystem")
    if not isinstance(subsystem_raw, str) or not subsystem_raw.strip():
        raise SubsystemFailureScheduleError(
            f"subsystem_failures[{index}].subsystem must be a non-empty string"
        )
    subsystem = subsystem_raw.strip().lower().removesuffix("_failure")
    if subsystem not in _VALID_SUBSYSTEMS:
        raise SubsystemFailureScheduleError(
            f"subsystem_failures[{index}].subsystem must be one of "
            f"{sorted(_VALID_SUBSYSTEMS)}, got {subsystem_raw!r}"
        )

    start_step = _require_non_negative_int(
        item.get("start_step"), f"[{index}].start_step"
    )
    end_step_raw = item.get("end_step")
    duration_raw = item.get("duration_steps")
    if end_step_raw is not None and duration_raw is not None:
        raise SubsystemFailureScheduleError(
            f"subsystem_failures[{index}] cannot set both end_step and duration_steps"
        )

    end_step: Optional[int] = None
    duration_steps: Optional[int] = None
    if end_step_raw is not None:
        end_step = _require_non_negative_int(end_step_raw, f"[{index}].end_step")
        if end_step <= start_step:
            raise SubsystemFailureScheduleError(
                f"subsystem_failures[{index}].end_step must be > start_step "
                f"({start_step})"
            )
    if duration_raw is not None:
        duration_steps = _require_positive_int(
            duration_raw, f"[{index}].duration_steps"
        )

    return SubsystemFailureEntry(
        subsystem=subsystem,
        start_step=start_step,
        end_step=end_step,
        duration_steps=duration_steps,
    )


def _require_non_negative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SubsystemFailureScheduleError(
            f"subsystem_failures{label} must be a non-negative integer"
        )
    if value < 0:
        raise SubsystemFailureScheduleError(
            f"subsystem_failures{label} must be >= 0"
        )
    return value


def _require_positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SubsystemFailureScheduleError(
            f"subsystem_failures{label} must be a positive integer"
        )
    if value < 1:
        raise SubsystemFailureScheduleError(
            f"subsystem_failures{label} must be >= 1"
        )
    return value


def resolve_failure_flags(
    schedule: Sequence[SubsystemFailureEntry],
    step: int,
) -> Dict[str, bool]:
    """Return desired failure flags for subsystems owned by ``schedule``."""
    owned = {entry.subsystem for entry in schedule}
    desired = {sub: False for sub in owned}
    for entry in schedule:
        if entry.is_active(step):
            desired[entry.subsystem] = True
    return desired


def apply_scheduled_subsystem_failures(
    backend: EclssBackend,
    schedule: Sequence[SubsystemFailureEntry],
    step: int,
    *,
    last_enabled: MutableMapping[str, bool],
) -> List[Dict[str, Any]]:
    """Apply schedule for ``step``; return events for state transitions only.

    Re-asserts the scheduled flag every step (schedule owns listed subsystems)
    so agent ``set_subsystem_failure`` cannot permanently clear an active fault.
    Events are emitted only when the desired flag changes.
    """
    if not schedule:
        return []
    desired = resolve_failure_flags(schedule, step)
    events: List[Dict[str, Any]] = []
    for subsystem, enabled in sorted(desired.items()):
        backend.set_subsystem_failure(subsystem, enabled)
        if last_enabled.get(subsystem) == enabled:
            continue
        last_enabled[subsystem] = enabled
        events.append(
            {
                "kind": EVENT_KIND,
                "subsystem": subsystem,
                "enabled": enabled,
                "source": "subsystem_failures",
            }
        )
    return events


def clear_scheduled_subsystem_failures(
    backend: EclssBackend,
    schedule: Sequence[SubsystemFailureEntry],
) -> None:
    """Clear all failure flags owned by a schedule.

    Backends can outlive a scenario run, notably when a ROS2 headless session
    is managed externally.  Cleanup therefore belongs to the scenario lifecycle
    rather than relying on a backend instance's initial in-memory flags.
    """
    for subsystem in sorted(scheduled_subsystems(schedule)):
        backend.set_subsystem_failure(subsystem, False)


def scheduled_subsystems(schedule: Iterable[SubsystemFailureEntry]) -> frozenset[str]:
    return frozenset(entry.subsystem for entry in schedule)


__all__ = [
    "EVENT_KIND",
    "SubsystemFailureEntry",
    "SubsystemFailureScheduleError",
    "apply_scheduled_subsystem_failures",
    "clear_scheduled_subsystem_failures",
    "parse_subsystem_failure_schedule",
    "resolve_failure_flags",
    "resolve_inject_subsystem_failures",
    "scheduled_subsystems",
]
