"""Exact stoichiometric ratios for the plant-sim ECLSS mock.

Ratios are derived from molecular weights (not hand-typed rounded constants) so
they always close under mass-balance tests. All values are dimensionless
kg-per-kg ratios.

Electrolysis (OGS):      2 H2O -> 2 H2 + O2
Sabatier:                CO2 + 4 H2 -> CH4 + 2 H2O
"""

from __future__ import annotations

# Molecular weights [g/mol]
MW_H2 = 2.01588
MW_O2 = 31.998
MW_H2O = 18.01528
MW_CO2 = 44.0095
MW_CH4 = 16.0425

# Electrolysis: per kg O2 produced
WATER_PER_O2 = (2 * MW_H2O) / MW_O2  # ~1.1260 kg H2O consumed
H2_PER_O2 = (2 * MW_H2) / MW_O2      # ~0.1260 kg H2 produced

# Sabatier: per kg H2 consumed
CO2_PER_H2 = MW_CO2 / (4 * MW_H2)    # ~5.4577 kg CO2 consumed
H2O_PER_H2 = (2 * MW_H2O) / (4 * MW_H2)  # ~4.4683 kg H2O produced
CH4_PER_H2 = MW_CH4 / (4 * MW_H2)    # ~1.9895 kg CH4 produced

__all__ = [
    "MW_H2",
    "MW_O2",
    "MW_H2O",
    "MW_CO2",
    "MW_CH4",
    "WATER_PER_O2",
    "H2_PER_O2",
    "CO2_PER_H2",
    "H2O_PER_H2",
    "CH4_PER_H2",
]
