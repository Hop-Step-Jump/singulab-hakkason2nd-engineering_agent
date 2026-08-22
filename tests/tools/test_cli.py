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


def test_run_ssos_rejects_actor_and_agents_mode_together():
    result = runner.invoke(
        app,
        [
            "run",
            "ssos_eclss_loop",
            "--backend",
            "mock",
            "--actor-mode",
            "labeled_rule_base",
            "--agents-mode",
            "llm",
            "--dry-run",
        ],
    )
    assert result.exit_code == 2
    assert "only one of --actor-mode and --agents-mode" in result.output


def test_run_ssos_actor_and_design_mode_dry_run(tmp_path: Path):
    spec_path = tmp_path / "spec.json"
    result = runner.invoke(
        app,
        [
            "run",
            "ssos_eclss_loop",
            "--backend",
            "mock",
            "--actor-mode",
            "labeled_rule_base",
            "--design-mode",
            "llm",
            "--dry-run",
            "--write-spec",
            str(spec_path),
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
    assert payload["overrides"]["agents"]["actor"]["mode"] == "labeled_rule_base"
    assert payload["overrides"]["agents"]["design"]["mode"] == "llm"


def test_run_rejects_invalid_design_mode():
    result = runner.invoke(
        app,
        ["run", "ssos_eclss_loop", "--backend", "mock", "--design-mode", "wizard"],
    )
    assert result.exit_code == 2
    assert "Unsupported design mode" in result.output


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


def test_run_rejects_invalid_llm_provider():
    result = runner.invoke(
        app,
        ["run", "scrubber_degradation", "--llm-provider", "llamacpp", "--dry-run"],
    )
    assert result.exit_code == 2
    assert "Unsupported LLM provider" in result.output


def test_run_llm_provider_vllm_dry_run_writes_spec(tmp_path: Path):
    spec_path = tmp_path / "spec.json"
    result = runner.invoke(
        app,
        [
            "run",
            "scrubber_degradation",
            "--agents-mode",
            "llm",
            "--llm-provider",
            "vllm",
            "--llm-model",
            "qwen3-32b",
            "--dry-run",
            "--write-spec",
            str(spec_path),
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
    assert payload["overrides"]["agents"]["mode"] == "llm"
    assert payload["overrides"]["agents"]["llm"]["provider"] == "vllm"
    assert payload["overrides"]["agents"]["llm"]["model"] == "qwen3-32b"
    assert payload["overrides"]["agents"]["llm"]["base_url"].endswith("/v1")


def test_run_llm_provider_from_env_writes_spec(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "vllm")
    monkeypatch.delenv("VLLM_BASE_URL", raising=False)
    monkeypatch.delenv("VLLM_MODEL", raising=False)
    spec_path = tmp_path / "spec.json"
    result = runner.invoke(
        app,
        [
            "run",
            "scrubber_degradation",
            "--agents-mode",
            "llm",
            "--dry-run",
            "--write-spec",
            str(spec_path),
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
    assert payload["overrides"]["agents"]["llm"]["provider"] == "vllm"
    assert payload["overrides"]["agents"]["llm"]["model"] == "qwen3-8b"
    assert "10.10.0.108:8000" in payload["overrides"]["agents"]["llm"]["base_url"]


def test_run_ssos_plan_shows_actor_and_design_modes():
    result = runner.invoke(
        app,
        [
            "run",
            "ssos_eclss_loop",
            "--backend",
            "mock",
            "--actor-mode",
            "labeled_rule_base",
            "--design-mode",
            "llm",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "actor=labeled_rule_base" in result.stdout
    assert "design=llm" in result.stdout


def test_run_ssos_llm_provider_only_patches_llm_side(tmp_path: Path):
    spec_path = tmp_path / "spec.json"
    result = runner.invoke(
        app,
        [
            "run",
            "ssos_eclss_loop",
            "--backend",
            "mock",
            "--actor-mode",
            "labeled_rule_base",
            "--design-mode",
            "llm",
            "--llm-provider",
            "ollama",
            "--dry-run",
            "--write-spec",
            str(spec_path),
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
    actor_llm = ((payload["overrides"].get("agents") or {}).get("actor") or {}).get("llm") or {}
    design_llm = ((payload["overrides"].get("agents") or {}).get("design") or {}).get("llm") or {}
    assert actor_llm.get("provider") != "ollama"
    assert design_llm.get("provider") == "ollama"


def test_preflight_targets_cover_both_ssos_llm_sides():
    from tools.cli.commands.run import _preflight_llm_targets

    both = _preflight_llm_targets(
        "ssos_eclss_loop",
        {"agents": {"actor": {"mode": "llm"}, "design": {"mode": "llm"}}},
    )
    assert [side for side, _cfg in both] == ["actor", "design"]
    design_only = _preflight_llm_targets(
        "ssos_eclss_loop",
        {"agents": {"actor": {"mode": "labeled_rule_base"}, "design": {"mode": "llm"}}},
    )
    assert [side for side, _cfg in design_only] == ["design"]
