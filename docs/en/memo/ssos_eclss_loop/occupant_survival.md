# Occupant survival (`plant_sim`)

This is the design that shipped: occupants and operators shrink together when tanks cannot support the roster. It merges three Cursor plans (capacity floor → band dwell → CO2 fractions) into the code in `src/scenario/ssos_eclss_loop/` and `src/environment/ssos/eclss/plant_sim/`.

Survival runs only on the **`plant_sim` backend**. `mock` / `ros2` do not apply dwell or the physics floor. The ops cheatsheet / sensitivity app keep `plant_sim.survival.enabled: false`.

Canonical count: `plant_sim.crew.size` in `src/scenario/ssos_eclss_loop/scenario.yaml`. When agents run, `agents.yaml` `team.count` must match. Occupants never return.

## Why the first floor was not enough

`PlantModel.apply_capacity_drop` originally kept everyone until the **next 20-minute interval** could not be paid (`floor(tank / per_person_demand)`). With a small O2 tank that is many person-steps, so a large roster stayed intact until the tank was almost empty, then dropped in one cliff.

Band dwell is **ops-stress policy** (linger in the same health bands that trigger ARS/OGS/WRS). The physics floor remains a **hard cap** so mass balance is not ignored.

## Pipeline (after each step's operations)

```text
post-ops inventories
  → health bands (same `thresholds` as labeled_rule_base)
  → SurvivalDwellPolicy.apply_dwell
  → backend.set_crew_alive
  → apply_capacity_drop  (O2/water next-interval floor; skipped on the last step)
  → team.set_crew_alive
```

The last step has no following `advance_step`, so the look-ahead floor is skipped (`physics_floor=step + 1 < steps`). Dwell still runs.

The scenario does not write `model.state` directly.

## Health bands (scenario defaults)

Ops triggers and survival bands are the **same** YAML keys. Current `ssos_eclss_loop` defaults (50 occupants):

| Resource | SAFE | WARNING | CRITICAL |
| --- | --- | --- | --- |
| Cabin CO2 (kg) | < 2.0 | 2.0 to < 8.0 | ≥ 8.0 |
| O2 (kg) | > 6.0 | 1.0 to 6.0 | ≤ 1.0 |
| Product water (L) | > 50 | 25 to 50 | ≤ 25 |

`o2_storage_critical_kg` and `product_water_critical_l` are explicit in YAML. If omitted, health falls back to `low * 0.75` and `low * 0.5`.

Default tanks start **SAFE** on O2 and water: `initial_o2_storage_kg` 8.0 (above LOW 6.0) and `initial_product_water_l` 80.0 (above LOW 50). Cabin CO2 starts at 1.3 kg (below HIGH 2.0). Default `simulation.steps` is 50.

## Band dwell (`survival.py`)

YAML lives under `plant_sim.survival`. CRITICAL does not increment that resource's WARNING streak.

### O2 and water (fixed headcount)

| Band | Consecutive steps | Loss | After a loss |
| --- | --- | --- | --- |
| O2 WARNING | 2 | 1 person | counter resets; another 2 steps in band → another −1 |
| O2 CRITICAL | 1 | 2 people | counter resets |
| Water WARNING | 2 | 1 person | same as O2 WARNING |
| Water CRITICAL | 1 | 1 person | counter resets |
| Leave SAFE | — | — | that resource's counter resets |

### CO2 (fraction, once per stay)

| Band | Consecutive steps | Loss | Re-fire |
| --- | --- | --- | --- |
| WARNING (HIGH) | 2 | `n // 4` | not again until leave and re-enter |
| CRITICAL | 2 | `n // 2` | same; **no wipe** |

A lone occupant: `1 // 4` and `1 // 2` are 0, so CO2 bands alone do not kill the last person. Example at 50: HIGH for 2 steps → 50→38; CRITICAL for 2 steps → 38→19.

### Same-step stacking

Each resource computes a **requested** loss independently. Applied `lost = min(alive, sum(requests))`. Cause slices, highest first:

1. `co2_critical`
2. `co2_warning`
3. `o2_critical`
4. `water_critical`
5. `o2_warning`
6. `water_warning`

Event `limiting` lists every requester. `crew_lost_by_cause` is the sliced count, not a copy of the total onto every cause.

## Physics floor (`apply_capacity_drop`)

Keep only people the **next** metabolism interval can pay in O2 and water. **Cabin CO2 does not cut crew here** (otherwise CO2 CRITICAL dwell would never be visible). Events use `o2_physics` / `water_physics` / `co2_physics` (the last is unused while CO2 wipe is off). When O2 and water both bind, the lost headcount is attributed to O2.

## Artifacts

| Where | What |
| --- | --- |
| `events.jsonl` | `/eclss/events/crew_lost` (`lost`, `remaining`, `limiting`, `crew_lost_by_cause`, `agent_ids`) |
| `summary.json` | `crew_initial`, `crew_remaining`, `crew_lost`, `crew_lost_by_cause` |
| `telemetry.jsonl` | `raw_topics.plant_sim.crew_alive` / `survival.lost_this_step` (dwell + physics that step) |
| Dashboard | plant_sim ledgers: crew alive vs step |

## Try (`plant_sim` only)

```bash
python3 -m tools.cli run ssos_eclss_loop \
  --backend plant_sim --agents-mode labeled_rule_base --steps 50 \
  --run-id survival-try
```

`--agents-mode none` leaves the tanks in band so dwell is easier to see. OGS/ARS/WRS can lift the plant out of WARNING.

## Code

| Path | Role |
| --- | --- |
| `src/scenario/ssos_eclss_loop/survival.py` | Dwell tables, streaks, stacking |
| `src/scenario/ssos_eclss_loop/scenario_run.py` `_apply_survival_after_ops` | Compose dwell then floor |
| `src/environment/ssos/eclss/plant_sim/model.py` `apply_capacity_drop` | O2/water floor |
| `src/environment/ssos/eclss/plant_sim/backend.py` `set_crew_alive` | Scenario → plant |
| `src/scenario/ssos_eclss_loop/health.py` | WARNING/CRITICAL from thresholds |
| `tests/scenario/test_ssos_eclss_loop_survival.py` | Dwell unit tables |

Plant mass-balance (not survival) is in [plant_sim_backend.md](plant_sim_backend.md).
