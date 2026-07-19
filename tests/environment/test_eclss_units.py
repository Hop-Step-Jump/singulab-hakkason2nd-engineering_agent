"""Unit tests for SSOS ECLSS unit helpers."""

import pytest

from environment.ssos.eclss.units import (
    mass_g_to_kg,
    mass_kg_to_g,
    o2_generated_kg,
    water_mass_kg_to_liters,
)


def test_mass_round_trip():
    assert mass_g_to_kg(1234.5) == pytest.approx(1.2345)
    assert mass_kg_to_g(1.2345) == pytest.approx(1234.5)


def test_water_mass_to_liters():
    assert water_mass_kg_to_liters(5.0) == 5.0


def test_o2_stoichiometry():
    # 0.89 kg O2 / kg H2O * 0.95 efficiency
    assert o2_generated_kg(1.0) == pytest.approx(0.8455)
    assert o2_generated_kg(0.015) == pytest.approx(0.0126825)
