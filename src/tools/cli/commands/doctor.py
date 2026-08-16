"""Environment checks for CLI users."""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys

import typer

from core.llm.ollama import resolve_ollama_base_url
from core.llm.vllm import resolve_vllm_base_url, vllm_auth_headers
from scenario.jobs.resolve import RESULTS_ROOT_ENV_VAR, default_results_root
from tools.cli import exit_codes
from tools.cli.output import print_doctor_report
from tools.cli.ssos_host import _HOST_RESULTS_MOUNT, ssos_container_name

MIN_PYTHON_VERSION = (3, 11)


def register(app: typer.Typer) -> None:
    app.command("doctor")(doctor)


def _docker_status() -> str:
    if not shutil.which("docker"):
        return "not installed"
    try:
        subprocess.run(
            ["docker", "info"],
            check=True,
            capture_output=True,
            timeout=5,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        return f"daemon unreachable ({exc.__class__.__name__})"
    return "ok"


def _ssos_container_status() -> str:
    if not shutil.which("docker"):
        return "skipped (no docker)"
    container = ssos_container_name()
    try:
        proc = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        return f"check failed ({exc.__class__.__name__})"
    names = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    if container in names:
        return f"running ({container})"
    return f"not running (expected: {container})"


def _ssos_mount_status() -> str:
    if not shutil.which("docker"):
        return "skipped (no docker)"
    container = ssos_container_name()
    try:
        subprocess.run(
            ["docker", "exec", container, "test", "-d", "/ea/src/scenario/ssos_eclss_loop"],
            check=True,
            capture_output=True,
            timeout=5,
        )
        subprocess.run(
            ["docker", "exec", container, "test", "-f", "/root/ssos-eclss-headless.sh"],
            check=True,
            capture_output=True,
            timeout=5,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return f"missing or incomplete (container: {container})"
    return "ok"


def _python_version_label() -> str:
    return sys.version.split()[0]


def _python_support_status() -> tuple[str, bool]:
    version = sys.version_info[:3]
    if version >= MIN_PYTHON_VERSION:
        return "ok", True
    minimum = ".".join(str(part) for part in MIN_PYTHON_VERSION)
    return (
        f"unsupported (requires {minimum}+, found {_python_version_label()}; "
        "use python3.11 -m venv .venv)",
        False,
    )


def doctor() -> None:
    python_support, python_ok = _python_support_status()
    report = {
        "python": _python_version_label(),
        "python_min": f"{MIN_PYTHON_VERSION[0]}.{MIN_PYTHON_VERSION[1]}+",
        "python_support": python_support,
        "platform": platform.platform(),
        "results_root": str(default_results_root()),
        "results_root_env": RESULTS_ROOT_ENV_VAR,
        "ssos_results_mount": str(_HOST_RESULTS_MOUNT),
        "docker": _docker_status(),
        "ssos_container": _ssos_container_status(),
        "ssos_mounts": _ssos_mount_status(),
    }

    try:
        import numpy  # noqa: F401
        import yaml  # noqa: F401

        report["dependencies"] = "ok"
    except ImportError as exc:
        report["dependencies"] = f"missing: {exc.name}"

    ollama_url = resolve_ollama_base_url()
    report["ollama_url"] = ollama_url
    vllm_url = resolve_vllm_base_url()
    report["vllm_url"] = vllm_url
    try:
        import requests

        try:
            response = requests.get(f"{ollama_url}/api/tags", timeout=2)
            response.raise_for_status()
            report["ollama"] = "reachable"
        except Exception as exc:
            report["ollama"] = f"unreachable ({exc.__class__.__name__})"
        try:
            response = requests.get(
                f"{vllm_url}/models",
                headers=vllm_auth_headers(),
                timeout=2,
            )
            response.raise_for_status()
            report["vllm"] = "reachable"
        except Exception as exc:
            report["vllm"] = f"unreachable ({exc.__class__.__name__})"
    except ImportError as exc:
        report["ollama"] = f"unreachable ({exc.__class__.__name__})"
        report["vllm"] = f"unreachable ({exc.__class__.__name__})"

    print_doctor_report(report)
    if not python_ok:
        raise typer.Exit(exit_codes.ENVIRONMENT_ERROR)
    raise typer.Exit(exit_codes.SUCCESS)
