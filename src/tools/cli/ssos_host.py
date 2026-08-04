"""Host-side SSOS container run bridge (invoked from ea run)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict

from scenario.jobs.resolve import RESULTS_ROOT_ENV_VAR, default_results_root, resolve_run_id
from scenario.jobs.spec import RunResult, RunSpec
from scenario.runner import load_scenario_config
from scenario.ssos_eclss_loop.scenario_run import resolve_backend_kind as resolve_ssos_backend_kind
from tools.cli import exit_codes

_REPO_ROOT = Path(__file__).resolve().parents[3]
_HOST_RUN_SCRIPT = _REPO_ROOT / "scripts" / "ssos_host_run.sh"
_CONTAINER_RESULTS_ROOT = Path("/ea/results")
_HOST_RESULTS_MOUNT = _REPO_ROOT / "src" / "experiments" / "results"


def ssos_container_name() -> str:
    return os.environ.get("SSOS_CONTAINER") or os.environ.get("SSOS_CONTAINER_NAME") or "ssos"


def resolve_backend_kind(spec: RunSpec) -> str:
    if spec.scenario != "ssos_eclss_loop":
        return "mock"
    config = load_scenario_config(spec.scenario, spec.overrides)
    return resolve_ssos_backend_kind(config, spec.overrides)


def should_run_ssos_in_container(spec: RunSpec) -> bool:
    if os.environ.get("EA_RUN_IN_CONTAINER"):
        return False
    if not shutil.which("docker"):
        return False
    return spec.scenario == "ssos_eclss_loop" and resolve_backend_kind(spec) == "ros2"


def check_ssos_ros2_host_environment(spec: RunSpec) -> RunResult | None:
    """Return a failure RunResult when ros2 SSOS cannot run on the host; else None."""
    if spec.scenario != "ssos_eclss_loop" or resolve_backend_kind(spec) != "ros2":
        return None
    if os.environ.get("EA_RUN_IN_CONTAINER"):
        return None
    if shutil.which("docker"):
        return None
    return RunResult(
        run_dir=Path("."),
        exit_code=exit_codes.ENVIRONMENT_ERROR,
        error=(
            "Docker is required for ssos_eclss_loop with the default ros2 backend. "
            "Install Docker, start the SSOS container (./scripts/ssos/mac/ssos-run-detached.sh), "
            "or pass --backend mock / --backend plant_sim for local runs."
        ),
    )


def run_ssos_in_container(spec: RunSpec) -> RunResult:
    if spec.output_dir is not None:
        return RunResult(
            run_dir=spec.output_dir,
            exit_code=exit_codes.USER_ERROR,
            error=(
                "--output-dir is not supported for ssos_eclss_loop ros2 runs. "
                "Use --run-id with the mounted results directory."
            ),
        )

    results_error = _validate_host_results_root(spec)
    if results_error is not None:
        return RunResult(
            run_dir=_host_run_directory(spec),
            exit_code=exit_codes.USER_ERROR,
            error=results_error,
        )

    if not _HOST_RUN_SCRIPT.is_file():
        return RunResult(
            run_dir=Path("."),
            exit_code=exit_codes.ENVIRONMENT_ERROR,
            error=f"Missing host runner script: {_HOST_RUN_SCRIPT}",
        )

    container_apply_path: Path | None = None
    if spec.apply_proposals_path is not None:
        if not spec.apply_proposals_path.is_file():
            return RunResult(
                run_dir=_host_run_directory(spec),
                exit_code=exit_codes.USER_ERROR,
                error=f"design_proposals file not found: {spec.apply_proposals_path}",
            )
        container_apply_path = Path(f"/tmp/ea-apply-{os.getpid()}.json")
        copy = subprocess.run(
            [
                "docker",
                "cp",
                str(spec.apply_proposals_path),
                f"{ssos_container_name()}:{container_apply_path}",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if copy.returncode != 0:
            return RunResult(
                run_dir=_host_run_directory(spec),
                exit_code=exit_codes.ENVIRONMENT_ERROR,
                error=(
                    f"Failed to copy design_proposals into SSOS container "
                    f"({ssos_container_name()}): {copy.stderr.strip() or copy.stdout.strip()}"
                ),
            )

    container_spec = _container_spec(spec, apply_proposals_path=container_apply_path)
    start = time.monotonic()
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        delete=False,
        encoding="utf-8",
    ) as handle:
        job_path = Path(handle.name)
        handle.write(container_spec.to_json())

    try:
        proc = subprocess.run(
            ["bash", str(_HOST_RUN_SCRIPT), str(job_path)],
            cwd=_REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    finally:
        job_path.unlink(missing_ok=True)
        if container_apply_path is not None:
            subprocess.run(
                [
                    "docker",
                    "exec",
                    ssos_container_name(),
                    "rm",
                    "-f",
                    str(container_apply_path),
                ],
                check=False,
                capture_output=True,
            )

    duration_s = time.monotonic() - start
    host_run_dir = _host_run_directory(spec)
    if proc.returncode != 0:
        exit_code = exit_codes.USER_ERROR
        if proc.returncode == 3:
            exit_code = exit_codes.ENVIRONMENT_ERROR
        elif proc.returncode == 1:
            exit_code = exit_codes.RUN_FAILURE
        elif proc.returncode == 4:
            exit_code = exit_codes.USER_ERROR
        return RunResult(
            run_dir=host_run_dir,
            summary={},
            duration_s=duration_s,
            exit_code=exit_code,
            error=_failure_message(proc.returncode, proc.stderr),
        )

    summary_path = host_run_dir / "summary.json"
    if not summary_path.is_file():
        return RunResult(
            run_dir=host_run_dir,
            summary={},
            duration_s=duration_s,
            exit_code=exit_codes.RUN_FAILURE,
            error=(
                "SSOS container run exited 0 but summary.json is missing at "
                f"{summary_path}. Check volume mounts and container logs."
            ),
        )

    try:
        summary = _read_summary(host_run_dir)
    except ValueError as exc:
        return RunResult(
            run_dir=host_run_dir,
            summary={},
            duration_s=duration_s,
            exit_code=exit_codes.RUN_FAILURE,
            error=str(exc),
        )
    return RunResult(
        run_dir=host_run_dir,
        summary=summary,
        duration_s=duration_s,
        exit_code=exit_codes.SUCCESS,
    )


def _failure_message(returncode: int, stderr: str = "") -> str:
    detail = stderr.strip()
    if returncode == 3:
        base = (
            "SSOS environment not ready (container stopped, volume mounts missing, "
            "or headless failed to start). See messages above and docs/cli.md."
        )
    elif returncode == 2:
        base = "SSOS host run rejected invalid input (see messages above)."
    elif returncode == 4:
        base = "Another ea run is already in progress for this SSOS container."
    else:
        base = f"SSOS container run failed (exit {returncode})."
    if detail:
        return f"{base}\n{detail}"
    return base


def _container_spec(
    spec: RunSpec,
    *,
    apply_proposals_path: Path | None = None,
) -> RunSpec:
    return RunSpec(
        scenario=spec.scenario,
        overrides=spec.overrides,
        output_dir=None,
        run_id=spec.run_id,
        results_root=_CONTAINER_RESULTS_ROOT,
        recreate_output=spec.recreate_output,
        seed=spec.seed,
        apply_proposals_path=apply_proposals_path if apply_proposals_path is not None else spec.apply_proposals_path,
    )


def _validate_host_results_root(spec: RunSpec) -> str | None:
    host_root = spec.results_root or default_results_root()
    if host_root.resolve() != _HOST_RESULTS_MOUNT.resolve():
        if spec.results_root is not None:
            return (
                "--results-root is not supported for ssos_eclss_loop ros2 runs. "
                f"Results are written to the container mount: {_HOST_RESULTS_MOUNT}"
            )
        return (
            f"{RESULTS_ROOT_ENV_VAR} must point to the mounted results directory "
            f"({_HOST_RESULTS_MOUNT}) for ssos_eclss_loop ros2 runs."
        )
    return None


def _host_run_directory(spec: RunSpec) -> Path:
    config = load_scenario_config(spec.scenario, spec.overrides)
    agents_config = config.get("agents")
    host_root = spec.results_root or default_results_root()
    run_id = resolve_run_id(
        spec.scenario,
        config.get("output", {}),
        agents_config,
        spec.run_id,
    )
    return host_root / run_id


def _read_summary(run_dir: Path) -> Dict[str, Any]:
    summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        return {}
    try:
        return json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"summary.json is not valid JSON at {summary_path}: {exc}"
        ) from exc
