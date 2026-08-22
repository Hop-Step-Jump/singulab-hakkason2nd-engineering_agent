"""Tests for nested ssos actor / design agent config."""

import pytest

from scenario.runner import load_agents_config, load_scenario_config
from scenario.ssos_eclss_loop.agent_config import (
    flatten_actor_config,
    flatten_design_config,
    iter_ssos_llm_targets,
    normalize_ssos_agents_section,
    resolve_ssos_modes,
    ssos_agents_enabled,
    ssos_run_id_mode_key,
)
from scenario.ssos_eclss_loop.policy import merge_labeled_policy_from_thresholds


def test_legacy_mode_overrides_existing_actor_mode():
    normalized = normalize_ssos_agents_section(
        {"mode": "labeled_rule_base", "actor": {"mode": "none"}}
    )
    actor_mode, design_mode = resolve_ssos_modes(normalized)
    assert actor_mode == "labeled_rule_base"
    assert design_mode == "labeled_rule_base"


def test_legacy_mode_lifts_to_actor_and_design_inherits():
    normalized = normalize_ssos_agents_section({"mode": "labeled_rule_base", "team": {"count": 4}})
    actor_mode, design_mode = resolve_ssos_modes(normalized)
    assert actor_mode == "labeled_rule_base"
    assert design_mode == "labeled_rule_base"
    assert normalized["actor"]["team"]["count"] == 4


def test_explicit_design_none_does_not_inherit():
    actor_mode, design_mode = resolve_ssos_modes(
        {"actor": {"mode": "llm"}, "design": {"mode": "none"}}
    )
    assert actor_mode == "llm"
    assert design_mode == "none"


def test_ssos_agents_enabled_design_only():
    assert ssos_agents_enabled({"actor": {"mode": "none"}, "design": {"mode": "llm"}})
    assert not ssos_agents_enabled({"actor": {"mode": "none"}, "design": {"mode": "none"}})


def test_flatten_keeps_nested_modes():
    cfg = {
        "actor": {"mode": "labeled_rule_base", "policy": {"request_co2_amount": 0.02}},
        "design": {"mode": "llm", "team": {"count": 4}},
    }
    assert flatten_actor_config(cfg)["mode"] == "labeled_rule_base"
    assert flatten_design_config(cfg)["mode"] == "llm"


def test_merge_labeled_policy_nested_actor():
    agents_config = {
        "actor": {"mode": "labeled_rule_base", "policy": {"request_co2_amount": 0.025}},
        "design": {"mode": "labeled_rule_base"},
    }
    merged = merge_labeled_policy_from_thresholds(
        agents_config,
        {"co2_storage_high_kg": 1.55, "o2_storage_low_kg": 0.44},
    )
    assert merged["actor"]["policy"]["co2_storage_high_kg"] == 1.55
    assert merged["actor"]["policy"]["request_co2_amount"] == 0.025


def test_flat_max_actions_override_wins_over_nested_actor():
    normalized = normalize_ssos_agents_section(
        {"max_actions_per_step": 8, "actor": {"max_actions_per_step": 2}}
    )
    assert normalized["actor"]["max_actions_per_step"] == 8


def test_flat_cli_set_reaches_loaded_actor_config():
    config = load_scenario_config(
        "ssos_eclss_loop", {"agents": {"max_actions_per_step": 8, "actor": {"mode": "llm"}}}
    )
    agents = load_agents_config("ssos_eclss_loop", config)
    assert agents is not None
    assert agents["actor"]["max_actions_per_step"] == 8


def test_resolve_ssos_modes_rejects_typo():
    with pytest.raises(ValueError, match="Unsupported actor mode"):
        resolve_ssos_modes({"actor": {"mode": "wizard"}})


def test_ssos_run_id_mode_key_mixed_and_matching():
    assert ssos_run_id_mode_key({"actor": {"mode": "llm"}, "design": {"mode": "llm"}}) == "llm"
    assert (
        ssos_run_id_mode_key(
            {"actor": {"mode": "none"}, "design": {"mode": "llm"}}
        )
        == "none_llm"
    )


def test_iter_ssos_llm_targets_includes_every_enabled_side():
    both = iter_ssos_llm_targets(
        {
            "actor": {"mode": "llm", "llm": {"provider": "ollama"}},
            "design": {"mode": "llm", "llm": {"provider": "vllm"}},
        }
    )
    assert [side for side, _cfg in both] == ["actor", "design"]
    design_only = iter_ssos_llm_targets(
        {
            "actor": {"mode": "labeled_rule_base"},
            "design": {"mode": "llm", "llm": {"base_url": "http://design"}},
        }
    )
    assert [side for side, cfg in design_only] == ["design"]
    assert design_only[0][1]["base_url"] == "http://design"
