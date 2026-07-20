"""Unit tests for SSOS ECLSS unit helpers."""

import pytest

from environment.ssos.eclss.units import (
    g_to_kg,
    kg_to_g,
    water_kg_to_l,
)


def test_mass_round_trip():
    assert g_to_kg(1234.5) == pytest.approx(1.2345)
    assert kg_to_g(1.2345) == pytest.approx(1234.5)


def test_water_kg_to_l():
    assert water_kg_to_l(5.0) == 5.0
