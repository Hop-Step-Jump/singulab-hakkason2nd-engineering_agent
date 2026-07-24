"""Canonical unit conversions for SSOS ECLSS in engineering_agents.

Internal (engineering_agents) conventions
-----------------------------------------
- CO₂ / O₂ storage and service amounts: **kilograms**
- Product / grey water volumes: **liters**
- ``OgsGoal.input_water_mass``: **kilograms**
- ``ArsGoal.initial_co2_mass``: **kilograms**
- ``ArsGoal.initial_moisture_content`` / ``initial_contaminants``: **percent** (0–100)
- ``OgsGoal.iodine_concentration``: **mg/L**
- ``WrsGoal.urine_volume``: **liters**

Upstream SSOS ROS topics / action mass fields use **grams**. Convert at the
Ros2EclssBridge boundary (topic read: g→kg, goal/service send: kg→g).

Liquid water mass↔volume uses density 1.0 kg/L.

``o2_generated_kg`` is **stoichiometric O₂ yield** (not a unit conversion). It is
kept here for shared mock/backend use; electrolysis yield follows SSOS teaching
notes: 0.89 kg O₂ per kg H₂O, scaled by ``o2_efficiency`` (default 0.95).
"""

from __future__ import annotations

G_TO_KG = 0.001
WATER_DENSITY_KG_PER_L = 1.0
O2_YIELD_KG_PER_KG_WATER = 0.89
DEFAULT_O2_EFFICIENCY = 0.95


def g_to_kg(mass_g: float) -> float:
    return float(mass_g) * G_TO_KG


def kg_to_g(mass_kg: float) -> float:
    return float(mass_kg) / G_TO_KG


def water_kg_to_l(mass_kg: float) -> float:
    return float(mass_kg) / WATER_DENSITY_KG_PER_L


def o2_generated_kg(
    water_mass_kg: float,
    *,
    efficiency: float = DEFAULT_O2_EFFICIENCY,
) -> float:
    """Stoichiometric O₂ yield from water mass (not a unit conversion)."""
    return float(water_mass_kg) * O2_YIELD_KG_PER_KG_WATER * float(efficiency)
