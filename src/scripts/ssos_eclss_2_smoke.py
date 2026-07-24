#!/usr/bin/env python3
"""Phase 2: SSOS ECLSS WRS smoke via Ros2EclssBridge.

Verifies WRS action, product water / grey water services, and drinking vs
electrolysis water tradeoffs visible in poll_telemetry().

Run inside SSOS Docker after headless ECLSS is up:

    bash /root/ssos-eclss-headless.sh   # terminal 1

    PYTHONPATH=src python3 -m scripts.ssos_eclss_2_smoke   # terminal 2 (container)

From host Mac: ./scripts/run_ssos_eclss_2_smoke.sh
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
    TOPIC_WRS_PRODUCT_WATER_RESERVE,
)
from environment.ssos.eclss.types import OgsGoal, WrsGoal
from environment.ssos.eclss.ros2.bridge import Ros2EclssBridge


@dataclass
class Eclss2SmokeReport:
    ok: bool
    launch_hint: str
    telemetry_before: Optional[Dict[str, Any]] = None
    telemetry_after: Optional[Dict[str, Any]] = None
    wrs_action: Optional[Dict[str, Any]] = None
    product_water_request: Optional[Dict[str, Any]] = None
    grey_water_submit: Optional[Dict[str, Any]] = None
    ogs_action: Optional[Dict[str, Any]] = None
    product_water_delta: Optional[float] = None
    water_tradeoff_signal: bool = False
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def run_2_smoke(
    *,
    wrs_goal: Optional[WrsGoal] = None,
    ogs_goal: Optional[OgsGoal] = None,
    action_timeout_s: float = 120.0,
    topic_timeout_s: float = 15.0,
    product_water_liters: float = 5.0,
    grey_water_liters: float = 3.0,
) -> Eclss2SmokeReport:
    """Exercise WRS paths on Ros2EclssBridge against a live SSOS ECLSS stack."""
    wrs_goal = wrs_goal or WrsGoal(urine_volume=2.0)
    ogs_goal = ogs_goal or OgsGoal()
    launch_hint = f"bash /root/ssos-eclss-headless.sh  # or: ros2 launch {LAUNCH_HEADLESS_ECLSS}"
    report = Eclss2SmokeReport(ok=False, launch_hint=launch_hint)

    if not Ros2EclssBridge.ros2_available():
        report.errors.append("ros2 CLI not found — run inside SSOS container")
        return report

    bridge = Ros2EclssBridge(
        action_timeout_s=action_timeout_s,
        topic_timeout_s=topic_timeout_s,
    )

    before = bridge.poll_telemetry()
    report.telemetry_before = before.to_dict()

    if before.product_water_reserve_l is None:
        report.errors.append(f"missing telemetry from {TOPIC_WRS_PRODUCT_WATER_RESERVE}")

    grey_result = bridge.submit_grey_water(grey_water_liters)
    report.grey_water_submit = grey_result.to_dict()
    if not grey_result.success:
        report.errors.append(f"submit_grey_water failed: {grey_result.message or 'unknown'}")

    wrs_result = bridge.send_water_recovery_goal(wrs_goal)
    report.wrs_action = wrs_result.to_dict()
    if not wrs_result.success:
        report.errors.append("water_recovery_systems goal did not succeed")

    mid = bridge.poll_telemetry()
    water_after_recovery = mid.product_water_reserve_l

    product_result = bridge.request_product_water(product_water_liters)
    report.product_water_request = product_result.to_dict()
    if not product_result.success:
        report.errors.append(f"request_product_water failed: {product_result.message or 'unknown'}")

    ogs_result = bridge.send_oxygen_generation_goal(ogs_goal)
    report.ogs_action = ogs_result.to_dict()
    if not ogs_result.success:
        report.errors.append("oxygen_generation goal did not succeed (electrolysis water draw)")

    after = bridge.poll_telemetry()
    report.telemetry_after = after.to_dict()

    if before.product_water_reserve_l is not None and after.product_water_reserve_l is not None:
        report.product_water_delta = after.product_water_reserve_l - before.product_water_reserve_l

    purified = (wrs_result.details or {}).get("total_purified_water")
    water_granted = product_result.response_value
    report.water_tradeoff_signal = bool(
        (purified is not None and purified > 0)
        or (water_granted is not None and water_granted > 0)
        or (water_after_recovery is not None and before.product_water_reserve_l is not None
            and water_after_recovery > before.product_water_reserve_l)
        or (report.product_water_delta is not None and report.product_water_delta != 0)
        or grey_result.success
    )
    if not report.water_tradeoff_signal:
        report.errors.append(
            "no drinking vs electrolysis / grey water tradeoff signal in telemetry or WRS results"
        )

    report.ok = not report.errors
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="SSOS ECLSS Phase 2 smoke (WRS bridge)")
    parser.add_argument("--json-out", type=Path, help="Write JSON report to this path")
    parser.add_argument("--urine-volume", type=float, default=2.0)
    parser.add_argument(
        "--input-water-mass",
        type=float,
        default=0.015,
        help="OGS input_water_mass in kilograms (converted to grams for SSOS)",
    )
    parser.add_argument("--product-water-liters", type=float, default=5.0)
    parser.add_argument("--grey-water-liters", type=float, default=3.0)
    parser.add_argument("--action-timeout", type=float, default=120.0)
    parser.add_argument("--topic-timeout", type=float, default=15.0)
    args = parser.parse_args(list(argv) if argv is not None else None)

    wrs_goal = WrsGoal(urine_volume=args.urine_volume)
    ogs_goal = OgsGoal(input_water_mass=args.input_water_mass)
    report = run_2_smoke(
        wrs_goal=wrs_goal,
        ogs_goal=ogs_goal,
        action_timeout_s=args.action_timeout,
        topic_timeout_s=args.topic_timeout,
        product_water_liters=args.product_water_liters,
        grey_water_liters=args.grey_water_liters,
    )
    payload = report.to_dict()
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    if args.json_out:
        args.json_out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if not report.ok:
        print(f"\nPhase 2 smoke FAILED. Start ECLSS with: {report.launch_hint}", file=sys.stderr)
        for err in report.errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print("\nPhase 2 smoke PASSED.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
