"""Deterministic mass-balance plant simulation backend for SSOS ECLSS.

Public surface:
- :class:`PlantSimConfig` — validated configuration (kg / L / s).
- :class:`PlantModel` / :class:`PlantState` — pure physics + bookkeeping.
- :class:`PlantSimEclssBackend` — EclssBackend adapter used by scenarios.
"""

from __future__ import annotations

from environment.ssos.eclss.plant_sim.backend import PlantSimEclssBackend
from environment.ssos.eclss.plant_sim.config import PlantConfigError, PlantSimConfig
from environment.ssos.eclss.plant_sim.model import (
    PlantInvariantError,
    PlantModel,
    PlantState,
)

__all__ = [
    "PlantSimConfig",
    "PlantConfigError",
    "PlantModel",
    "PlantState",
    "PlantInvariantError",
    "PlantSimEclssBackend",
]
