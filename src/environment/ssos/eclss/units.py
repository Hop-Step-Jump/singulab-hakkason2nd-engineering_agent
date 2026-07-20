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
"""

from __future__ import annotations

G_TO_KG = 0.001
WATER_DENSITY_KG_PER_L = 1.0


def g_to_kg(mass_g: float) -> float:
    return float(mass_g) * G_TO_KG


def kg_to_g(mass_kg: float) -> float:
    return float(mass_kg) / G_TO_KG


def water_kg_to_l(mass_kg: float) -> float:
    return float(mass_kg) / WATER_DENSITY_KG_PER_L
