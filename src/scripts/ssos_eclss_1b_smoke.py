#!/usr/bin/env python3
"""Phase 1b: SSOS ECLSS ARS + OGS smoke via Ros2EclssBridge.

Verifies poll_telemetry(), OGS action, and O2/CO2 storage dynamics (Sabatier competition).

Run inside SSOS Docker after headless ECLSS is up:

    bash /root/ssos-eclss-headless.sh   # terminal 1

    PYTHONPATH=src python3 -m scripts.ssos_eclss_1b_smoke   # terminal 2 (container)

From host Mac: ./scripts/run_ssos_eclss_1b_smoke.sh
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from environment.ssos.eclss.ros2.topics import (
    LAUNCH_HEADLESS_ECLSS,
    TOPIC_CO2_STORAGE,
    TOPIC_O2_STORAGE,
)
from environment.ssos.eclss.types import OgsGoal, ServiceResult
from environment.ssos.eclss.ros2.bridge import Ros2EclssBridge


def _expected_insufficient_co2(
    result: ServiceResult,
    co2_storage_kg: Optional[float],
    requested_kg: float,
) -> bool:
    """Headless SSOS often starts with /co2_storage=0; service rejection is valid."""
    if result.success or co2_storage_kg is None:
        return False
    if co2_storage_kg >= requested_kg:
        return False
    message = (result.message or "").lower()
    return "insufficient" in message and "co" in message


@dataclass
class Eclss1bSmokeReport:
    ok: bool
    launch_hint: str
    telemetry_before: Optional[Dict[str, Any]] = None
    telemetry_after: Optional[Dict[str, Any]] = None
    ogs_action: Optional[Dict[str, Any]] = None
    request_co2: Optional[Dict[str, Any]] = None
    request_co2_expected_insufficient: bool = False
    co2_storage_delta: Optional[float] = None
    o2_storage_delta: Optional[float] = None
    sabatier_signal: bool = False
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def run_1b_smoke(
    *,
    ogs_goal: Optional[OgsGoal] = None,
    action_timeout_s: float = 120.0,
    topic_timeout_s: float = 15.0,
    request_co2_amount: float = 0.025,
) -> Eclss1bSmokeReport:
    """Exercise Ros2EclssBridge against a live SSOS ECLSS stack."""
    ogs_goal = ogs_goal or OgsGoal()
    launch_hint = f"bash /root/ssos-eclss-headless.sh  # or: ros2 launch {LAUNCH_HEADLESS_ECLSS}"
    report = Eclss1bSmokeReport(ok=False, launch_hint=launch_hint)

    if not Ros2EclssBridge.ros2_available():
        report.errors.append("ros2 CLI not found — run inside SSOS container")
        return report

    bridge = Ros2EclssBridge(
        action_timeout_s=action_timeout_s,
        topic_timeout_s=topic_timeout_s,
    )

    before = bridge.poll_telemetry()
    report.telemetry_before = before.to_dict()

    if before.co2_storage_kg is None:
        report.errors.append(f"missing telemetry from {TOPIC_CO2_STORAGE}")
    if before.o2_storage_kg is None:
        report.errors.append(f"missing telemetry from {TOPIC_O2_STORAGE}")

    co2_result = bridge.request_co2(request_co2_amount)
    report.request_co2 = co2_result.to_dict()
    report.request_co2_expected_insufficient = _expected_insufficient_co2(
        co2_result,
        before.co2_storage_kg,
        request_co2_amount,
    )
    if report.request_co2_expected_insufficient:
        report.request_co2["expected_insufficient"] = True
    elif not co2_result.success:
        report.errors.append(f"request_co2 failed: {co2_result.message or 'unknown'}")

    ogs_result = bridge.send_oxygen_generation_goal(ogs_goal)
    report.ogs_action = ogs_result.to_dict()
    if not ogs_result.success:
        report.errors.append("oxygen_generation goal did not succeed")

    after = bridge.poll_telemetry()
    report.telemetry_after = after.to_dict()

    if before.co2_storage_kg is not None and after.co2_storage_kg is not None:
        report.co2_storage_delta = after.co2_storage_kg - before.co2_storage_kg
    if before.o2_storage_kg is not None and after.o2_storage_kg is not None:
        report.o2_storage_delta = after.o2_storage_kg - before.o2_storage_kg

    ch4_vented = (ogs_result.details or {}).get("total_ch4_vented")
    o2_generated = (ogs_result.details or {}).get("total_o2_generated")
    report.sabatier_signal = bool(
        (report.o2_storage_delta is not None and report.o2_storage_delta > 0)
        or (o2_generated is not None and o2_generated > 0)
        or (ch4_vented is not None and ch4_vented > 0)
        or (report.co2_storage_delta is not None and report.co2_storage_delta != 0)
    )
    if not report.sabatier_signal:
        report.errors.append(
            "no O2/CO2 Sabatier competition signal in telemetry or OGS result"
        )

    report.ok = not report.errors
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="SSOS ECLSS Phase 1b smoke (ARS + OGS bridge)")
    parser.add_argument("--json-out", type=Path, help="Write JSON report to this path")
    parser.add_argument("--input-water-mass", type=float, default=10.0)
    parser.add_argument("--iodine", type=float, default=2.0)
    parser.add_argument("--action-timeout", type=float, default=120.0)
    parser.add_argument("--topic-timeout", type=float, default=15.0)
    parser.add_argument("--co2-request", type=float, default=25.0)
    args = parser.parse_args(list(argv) if argv is not None else None)

    goal = OgsGoal(input_water_mass=args.input_water_mass, iodine_concentration=args.iodine)
    report = run_1b_smoke(
        ogs_goal=goal,
        action_timeout_s=args.action_timeout,
        topic_timeout_s=args.topic_timeout,
        request_co2_amount=args.co2_request,
    )
    payload = report.to_dict()
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    if args.json_out:
        args.json_out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if not report.ok:
        print(f"\nPhase 1b smoke FAILED. Start ECLSS with: {report.launch_hint}", file=sys.stderr)
        for err in report.errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    if report.request_co2_expected_insufficient:
        co2 = (report.telemetry_before or {}).get("co2_storage_kg")
        print(
            f"\nPhase 1b smoke PASSED (request_co2 rejected as expected: CO₂ storage={co2} kg).",
            file=sys.stderr,
        )
    else:
        print("\nPhase 1b smoke PASSED.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
