#!/usr/bin/env python3
"""Phase 1a: SSOS ECLSS ARS headless smoke test.

Run inside the SSOS Docker container after sourcing the workspace:

    source ~/ssos_ws/install/setup.bash
    ros2 launch space_station eclss.launch.py   # headless — no crew GUI

In another shell (same container):

    PYTHONPATH=src python3 -m scripts.ssos_eclss_ars_smoke
    PYTHONPATH=src python3 -m scripts.ssos_eclss_ars_smoke --json-out /tmp/eclss_smoke.json

Exit code 0 when smoke passes; 1 otherwise.

On host Mac (no ros2): use ./scripts/run_ssos_eclss_smoke.sh from repo root.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from environment.ssos.eclss.units import g_to_kg, kg_to_g
from environment.ssos.eclss.ros2.topics import (
    ACTION_AIR_REVITALISATION,
    ACTION_TYPE_AIR_REVITALISATION,
    ALL_ECLSS_ACTIONS,
    ALL_ECLSS_TELEMETRY_TOPICS,
    LAUNCH_HEADLESS_ECLSS,
    TOPIC_ARS_DIAGNOSTICS,
    TOPIC_CO2_STORAGE,
    normalize_ros_name,
    parse_ros_graph_line,
    ros_cli_action_name,
)
from environment.ssos.eclss.types import ArsActionResult, ArsGoal, EclssSmokeReport

_ECLSS_TOPIC_PATTERN = re.compile(r"(co2|o2|ars|ogs|wrs|grey)", re.IGNORECASE)

_HOST_DOCKER_HELP = """\
ros2 CLI not found — Phase 1a smoke must run inside the SSOS Docker container.

From repo root on host Mac:
  ./scripts/run_ssos_eclss_smoke.sh

Manual (2 terminals):
  # Terminal 1 — launch headless ECLSS inside container
  docker exec -it ssos bash
  bash /root/ssos-eclss-headless.sh

  # Terminal 2 — sync repo and run smoke (container name: ssos)
  docker exec ssos mkdir -p /opt/engineering_agents
  docker cp src/. ssos:/opt/engineering_agents/src/
  docker exec -it ssos bash -lc '
    source /opt/ros/jazzy/setup.bash
    source ~/ssos_ws/install/setup.bash
    cd /opt/engineering_agents
    PYTHONPATH=/opt/engineering_agents/src:${PYTHONPATH} python3 -m scripts.ssos_eclss_ars_smoke
  '
"""


def _run_ros2_cli(args: Sequence[str], timeout_s: float = 30.0) -> Tuple[int, str, str]:
    proc = subprocess.run(
        ["ros2", *args],
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=False,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def _discover_ros_graph_snapshot() -> Tuple[List[str], List[str], Optional[str]]:
    """Return (topics, actions, error) from a single ros2 graph snapshot."""
    try:
        code, out, err = _run_ros2_cli(["topic", "list"])
        if code != 0:
            return [], [], err or f"ros2 topic list exited {code}"
        topics = [
            parse_ros_graph_line(line) for line in out.splitlines() if line.strip()
        ]
        topics = [t for t in topics if t]

        code, out, err = _run_ros2_cli(["action", "list"])
        if code != 0:
            return topics, [], err or f"ros2 action list exited {code}"
        actions = [
            parse_ros_graph_line(line) for line in out.splitlines() if line.strip()
        ]
        actions = [a for a in actions if a]
        return topics, actions, None
    except FileNotFoundError:
        return [], [], _HOST_DOCKER_HELP.strip()
    except subprocess.TimeoutExpired:
        return [], [], "ros2 CLI timed out"


def discover_ros_graph(
    *,
    wait_timeout_s: float = 30.0,
    poll_interval_s: float = 2.0,
) -> Tuple[List[str], List[str], Optional[str]]:
    """Poll ros2 graph until required ECLSS interfaces appear or timeout."""
    deadline = time.monotonic() + wait_timeout_s
    topics: List[str] = []
    actions: List[str] = []

    while True:
        topics, actions, discover_err = _discover_ros_graph_snapshot()
        if discover_err:
            return topics, actions, discover_err

        missing = _match_expected(topics, actions)
        if missing:
            if time.monotonic() >= deadline:
                return (
                    topics,
                    actions,
                    (
                        f"ECLSS not ready / not launched "
                        f"(required interfaces missing after {wait_timeout_s:.0f}s: "
                        f"{'; '.join(missing)})"
                    ),
                )
            time.sleep(poll_interval_s)
            continue

        return topics, actions, None


def _filter_eclss_topics(topics: List[str]) -> List[str]:
    return sorted(
        normalize_ros_name(t)
        for t in topics
        if _ECLSS_TOPIC_PATTERN.search(normalize_ros_name(t))
    )


def _match_expected(topics: List[str], actions: List[str]) -> List[str]:
    errors: List[str] = []
    topic_set = {parse_ros_graph_line(t) for t in topics if t}
    action_set = {parse_ros_graph_line(a) for a in actions if a}

    if normalize_ros_name(TOPIC_CO2_STORAGE) not in topic_set:
        errors.append(f"missing topic {TOPIC_CO2_STORAGE}")
    if normalize_ros_name(TOPIC_ARS_DIAGNOSTICS) not in topic_set:
        errors.append(f"missing topic {TOPIC_ARS_DIAGNOSTICS}")

    if normalize_ros_name(ACTION_AIR_REVITALISATION) not in action_set:
        errors.append(f"missing action {ACTION_AIR_REVITALISATION}")

    return errors


def send_ars_goal_cli(goal: ArsGoal, timeout_s: float = 120.0) -> Tuple[Optional[ArsActionResult], Optional[str]]:
    """Send air_revitalisation goal via ros2 CLI (works in SSOS container without extra pip deps).

    ``ArsGoal.initial_co2_mass`` is kilograms; SSOS action fields are grams.
    """
    goal_yaml = (
        f"{{initial_co2_mass: {kg_to_g(goal.initial_co2_mass)}, "
        f"initial_moisture_content: {goal.initial_moisture_content}, "
        f"initial_contaminants: {goal.initial_contaminants}}}"
    )
    try:
        proc = subprocess.run(
            [
                "ros2",
                "action",
                "send_goal",
                "--feedback",
                ros_cli_action_name(ACTION_AIR_REVITALISATION),
                ACTION_TYPE_AIR_REVITALISATION,
                goal_yaml,
            ],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except FileNotFoundError:
        return None, "ros2 CLI not found"
    except subprocess.TimeoutExpired:
        return None, f"action goal timed out after {timeout_s}s"

    combined = f"{proc.stdout}\n{proc.stderr}"
    if proc.returncode != 0:
        return None, combined.strip() or f"ros2 action send_goal exited {proc.returncode}"

    success = "Goal finished with status: SUCCEEDED" in combined or "Result:" in combined
    cycles = _extract_int(combined, r"cycles_completed:\s*(-?\d+)")
    vents = _extract_int(combined, r"total_vents:\s*(-?\d+)")
    co2_vented = _extract_float(combined, r"total_co2_vented:\s*([-+]?[0-9]*\.?[0-9]+)")
    summary = _extract_line(combined, r"summary_message:\s*'([^']*)'") or _extract_line(
        combined, r'summary_message:\s*"([^"]*)"'
    )

    if "cabin_co2_level" not in combined and not success:
        return None, "no feedback received — is air_revitalisation running?"

    return (
        ArsActionResult(
            success=success,
            cycles_completed=cycles or 0,
            total_vents=vents or 0,
            total_co2_vented=g_to_kg(co2_vented) if co2_vented is not None else 0.0,
            summary_message=summary or "",
        ),
        None,
    )


def _extract_int(text: str, pattern: str) -> Optional[int]:
    match = re.search(pattern, text)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _extract_float(text: str, pattern: str) -> Optional[float]:
    match = re.search(pattern, text)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _extract_line(text: str, pattern: str) -> Optional[str]:
    match = re.search(pattern, text)
    return match.group(1) if match else None


def run_ars_smoke(
    goal: Optional[ArsGoal] = None,
    *,
    send_goal: bool = True,
    goal_timeout_s: float = 120.0,
    wait_timeout_s: float = 30.0,
) -> EclssSmokeReport:
    """Execute Phase 1a smoke checks against a running SSOS ECLSS stack."""
    goal = goal or ArsGoal()
    launch_hint = f"bash /root/ssos-eclss-headless.sh  # or: ros2 launch {LAUNCH_HEADLESS_ECLSS}"
    report = EclssSmokeReport(ok=False, launch_hint=launch_hint)

    topics, actions, discover_err = discover_ros_graph(wait_timeout_s=wait_timeout_s)
    if discover_err:
        report.errors.append(discover_err)
        if topics or actions:
            report.topics_found = _filter_eclss_topics(topics)
            report.actions_found = sorted(
                normalize_ros_name(a)
                for a in actions
                if normalize_ros_name(a) in ALL_ECLSS_ACTIONS
            )
        return report

    report.topics_found = _filter_eclss_topics(topics)
    report.actions_found = sorted(
        normalize_ros_name(a) for a in actions if normalize_ros_name(a) in ALL_ECLSS_ACTIONS
    )

    report.errors.extend(_match_expected(topics, actions))

    if send_goal and not report.errors:
        result, send_err = send_ars_goal_cli(goal, timeout_s=goal_timeout_s)
        if send_err:
            report.errors.append(send_err)
        else:
            report.ars_goal_sent = True
            report.ars_result = result
            if result is not None and not result.success:
                report.errors.append("air_revitalisation goal did not succeed")

    report.ok = not report.errors
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="SSOS ECLSS ARS Phase 1a smoke test")
    parser.add_argument("--json-out", type=Path, help="Write JSON report to this path")
    parser.add_argument("--no-goal", action="store_true", help="Only list topics/actions")
    parser.add_argument("--co2-mass", type=float, default=1.8,
                        help="ARS initial_co2_mass in kilograms (converted to grams for SSOS)")
    parser.add_argument("--moisture", type=float, default=25.0)
    parser.add_argument("--contaminants", type=float, default=5.0)
    parser.add_argument("--goal-timeout", type=float, default=120.0)
    parser.add_argument(
        "--wait-timeout",
        type=float,
        default=30.0,
        help="Seconds to retry DDS discovery for required topics/actions (default: 30)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    goal = ArsGoal(
        initial_co2_mass=args.co2_mass,
        initial_moisture_content=args.moisture,
        initial_contaminants=args.contaminants,
    )
    report = run_ars_smoke(
        goal,
        send_goal=not args.no_goal,
        goal_timeout_s=args.goal_timeout,
        wait_timeout_s=args.wait_timeout,
    )
    payload = report.to_dict()

    print(json.dumps(payload, indent=2, ensure_ascii=False))
    if args.json_out:
        args.json_out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if not report.ok:
        print(f"\nSmoke FAILED. Start ECLSS with: {report.launch_hint}", file=sys.stderr)
        for err in report.errors:
            if err.startswith("ros2 CLI not found"):
                print(f"\n{err}", file=sys.stderr)
            else:
                print(f"  - {err}", file=sys.stderr)
        return 1

    print("\nSmoke PASSED.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
