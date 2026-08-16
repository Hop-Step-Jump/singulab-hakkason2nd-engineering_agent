"""CLI integration tests."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from tools.cli.main import app

runner = CliRunner()


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout


def test_scenarios_lists_registered_scenarios():
    result = runner.invoke(app, ["scenarios"])
    assert result.exit_code == 0
    assert "scrubber_degradation" in result.stdout
    assert "ssos_eclss_loop" in result.stdout


def test_run_scrubber_short(tmp_path: Path):
    output_dir = tmp_path / "cli-run"
    result = runner.invoke(
        app,
        [
            "run",
            "scrubber_degradation",
            "--agents-mode",
            "none",
            "--steps",
            "2",
            "--output-dir",
            str(output_dir),
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    assert str(output_dir) in result.stdout.replace("\n", "")
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["steps"] == 2


def test_run_unknown_scenario():
    result = runner.invoke(app, ["run", "missing_scenario"])
    assert result.exit_code == 2
    assert "Unknown scenario" in result.output


def test_run_rejects_invalid_agents_mode():
    result = runner.invoke(
        app,
        ["run", "scrubber_degradation", "--agents-mode", "labelled_rule_base"],
    )
    assert result.exit_code == 2
    assert "Unsupported agents mode" in result.output


def test_run_rejects_invalid_backend():
    result = runner.invoke(
        app,
        ["run", "ssos_eclss_loop", "--backend", "ros3"],
    )
    assert result.exit_code == 2
    assert "Unsupported backend kind" in result.output


def test_run_rejects_invalid_agents_mode_via_set():
    result = runner.invoke(
        app,
        ["run", "scrubber_degradation", "--set", "agents.mode=evil"],
    )
    assert result.exit_code == 2
    assert "Unsupported agents mode" in result.output


def test_run_scrubber_default_agents_mode_from_scenario(tmp_path: Path):
    output_dir = tmp_path / "default-mode"
    result = runner.invoke(
        app,
        [
            "run",
            "scrubber_degradation",
            "--steps",
            "2",
            "--output-dir",
            str(output_dir),
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["agents_mode"] == "none"


def test_run_ssos_mock_env_with_docker(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("SSOS_ECLSS_BACKEND", "mock")
    monkeypatch.delenv("EA_RUN_IN_CONTAINER", raising=False)
    monkeypatch.setattr("tools.cli.ssos_host.shutil.which", lambda _: "/usr/bin/docker")
    output_dir = tmp_path / "mock-env"
    result = runner.invoke(
        app,
        [
            "run",
            "ssos_eclss_loop",
            "--agents-mode",
            "none",
            "--steps",
            "2",
            "--output-dir",
            str(output_dir),
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    assert (output_dir / "summary.json").exists()


def test_run_ssos_without_docker_blocks(monkeypatch):
    monkeypatch.delenv("EA_RUN_IN_CONTAINER", raising=False)
    monkeypatch.setattr("tools.cli.ssos_host.shutil.which", lambda _: None)
    result = runner.invoke(
        app,
        ["run", "ssos_eclss_loop", "--agents-mode", "none", "--steps", "1"],
    )
    assert result.exit_code == 3
    assert "Docker is required" in result.output


def test_run_ssos_mock_without_docker_allowed(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("EA_RUN_IN_CONTAINER", raising=False)
    monkeypatch.setattr("tools.cli.ssos_host.shutil.which", lambda _: None)
    output_dir = tmp_path / "mock-run"
    result = runner.invoke(
        app,
        [
            "run",
            "ssos_eclss_loop",
            "--backend",
            "mock",
            "--agents-mode",
            "none",
            "--steps",
            "2",
            "--output-dir",
            str(output_dir),
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    assert (output_dir / "summary.json").exists()


def test_run_ssos_inject_failures_flag(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("EA_RUN_IN_CONTAINER", raising=False)
    monkeypatch.setattr("tools.cli.ssos_host.shutil.which", lambda _: None)
    output_dir = tmp_path / "inject-failures"
    result = runner.invoke(
        app,
        [
            "run",
            "ssos_eclss_loop",
            "--backend",
            "mock",
            "--agents-mode",
            "none",
            "--steps",
            "12",
            "--inject-failures",
            "--output-dir",
            str(output_dir),
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    telemetry = [
        json.loads(line)
        for line in (output_dir / "telemetry.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    by_step = {row["step"]: row for row in telemetry if not row.get("post_ops")}
    assert summary["inject_failures"] is True
    assert by_step[9]["ars_failure_enabled"] is False
    assert by_step[10]["ars_failure_enabled"] is True


def test_run_ssos_plant_sim_without_docker_allowed(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("EA_RUN_IN_CONTAINER", raising=False)
    monkeypatch.setattr("tools.cli.ssos_host.shutil.which", lambda _: None)
    output_dir = tmp_path / "plant-sim-run"
    result = runner.invoke(
        app,
        [
            "run",
            "ssos_eclss_loop",
            "--backend",
            "plant_sim",
            "--agents-mode",
            "none",
            "--steps",
            "2",
            "--output-dir",
            str(output_dir),
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary.get("backend") == "plant_sim"


def test_run_dry_run_write_spec(tmp_path: Path):
    spec_path = tmp_path / "job.json"
    result = runner.invoke(
        app,
        [
            "run",
            "scrubber_degradation",
            "--agents-mode",
            "none",
            "--steps",
            "2",
            "--dry-run",
            "--write-spec",
            str(spec_path),
        ],
    )
    assert result.exit_code == 0
    assert spec_path.exists()
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
    assert payload["scenario"] == "scrubber_degradation"


def test_job_run_from_spec(tmp_path: Path):
    output_dir = tmp_path / "job-run"
    spec_path = tmp_path / "job.json"
    spec_path.write_text(
        json.dumps(
            {
                "scenario": "scrubber_degradation",
                "overrides": {"agents": {"mode": "none"}, "simulation": {"steps": 2}},
                "output_dir": str(output_dir),
                "recreate_output": True,
            }
        ),
        encoding="utf-8",
    )
    result = runner.invoke(app, ["job", "run", str(spec_path), "--quiet"])
    assert result.exit_code == 0
    assert (output_dir / "summary.json").exists()


def test_run_writes_duration_wall_s(tmp_path: Path):
    output_dir = tmp_path / "duration-run"
    result = runner.invoke(
        app,
        [
            "run",
            "scrubber_degradation",
            "--agents-mode",
            "none",
            "--steps",
            "2",
            "--output-dir",
            str(output_dir),
        ],
    )
    assert result.exit_code == 0
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert "duration_wall_s" in summary
    assert summary["duration_wall_s"] >= 0
