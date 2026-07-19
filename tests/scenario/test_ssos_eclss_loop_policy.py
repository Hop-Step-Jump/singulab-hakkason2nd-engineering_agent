"""Tests for labeled policy derivation from scenario thresholds."""

from scenario.ssos_eclss_loop.policy import merge_labeled_policy_from_thresholds


def test_merge_labeled_policy_from_thresholds_copies_bands():
    agents_config = {
        "mode": "labeled_rule_base",
        "policy": {
            "request_co2_amount": 0.025,
            "ars_goal": {"initial_co2_mass": 1.8},
        },
    }
    thresholds = {
        "co2_storage_high_kg": 1.55,
        "o2_storage_low_kg": 0.44,
        "product_water_low_l": 55.0,
    }
    merged = merge_labeled_policy_from_thresholds(agents_config, thresholds)
    assert merged["policy"]["co2_storage_high_kg"] == 1.55
    assert merged["policy"]["o2_storage_low_kg"] == 0.44
    assert merged["policy"]["product_water_low_l"] == 55.0
    assert merged["policy"]["request_co2_amount"] == 0.025


def test_merge_labeled_policy_skips_llm_mode():
    agents_config = {"mode": "llm", "policy": {"co2_storage_high_kg": 0.999}}
    merged = merge_labeled_policy_from_thresholds(
        agents_config,
        {"co2_storage_high_kg": 1.5},
    )
    assert merged["policy"]["co2_storage_high_kg"] == 0.999
