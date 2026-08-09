"""Tests for persisting effective run YAML configs."""

from __future__ import annotations

from pathlib import Path

import yaml

from scenario.runner import write_effective_configs


def test_write_effective_configs_scenario_only(tmp_path: Path):
    paths = write_effective_configs(
        tmp_path,
        scenario_config={"name": "demo", "simulation": {"steps": 3}},
        agents_config=None,
    )
    assert set(paths) == {"scenario_config_path"}
    loaded = yaml.safe_load(Path(paths["scenario_config_path"]).read_text(encoding="utf-8"))
    assert loaded["simulation"]["steps"] == 3
    assert not (tmp_path / "agents_config.yaml").exists()


def test_write_effective_configs_with_agents(tmp_path: Path):
    paths = write_effective_configs(
        tmp_path,
        scenario_config={"agents": {"mode": "labeled_rule_base"}},
        agents_config={"mode": "labeled_rule_base", "policy": {"request_co2_amount": 0.03}},
    )
    assert "agents_config_path" in paths
    agents = yaml.safe_load(Path(paths["agents_config_path"]).read_text(encoding="utf-8"))
    assert agents["policy"]["request_co2_amount"] == 0.03
