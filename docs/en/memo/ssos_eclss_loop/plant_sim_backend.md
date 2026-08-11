# SSOS Mock ECLSS — Plant Simulation Backend

- Updated: 2026-08-07
- Implementation: PR #40 (`PlantSimEclssBackend`, `backend.kind = plant_sim`)
- Package: `src/environment/ssos/eclss/plant_sim/`

> **Purpose:** Document what `plant_sim` reproduces from SSOS, what it deliberately omits, and how to run and configure it. This is **not** a Python port of SSOS — it is a deterministic, medium-fidelity mass-balance model for agent operation verification.

Japanese deep-dive (fidelity rationale, subsystem-by-subsystem): use the header language switcher → **日本語** → Development notes → **Plant Sim backend 解説**.

---

## Summary

`PlantSimEclssBackend` keeps the same `EclssBackend` contract as `LoopMockEclssBackend` and `Ros2EclssBridge`, but models:

- crew metabolism (CO₂, O₂, potable water, urine, condensate)
- ARS, OGS + Sabatier, and WRS mass flows
- inventory limits, partial operations, subsystem failures
- vent / brine / shortfall ledgers

It does **not** model ROS 2, device internals (PDE, electrochemistry, water quality), or cabin ppm/pressure.

Use `plant_sim` when you need **explainable mass balance and water-loop closure** on the host without Docker. Use `mock` for fastest contract/regression checks; use `ros2` for live SSOS fidelity.

---

## Three backends

```text
SsosEclssLoopTeam
        │ commands / telemetry
        ▼
EclssBackend Protocol
        │
        ├─ LoopMockEclssBackend     contract / simple storage dynamics
        ├─ PlantSimEclssBackend     mass-balance plant (this doc)
        └─ Ros2EclssBridge          SSOS Docker via ros2 CLI
```

| Aspect | LoopMock | Plant Sim | SSOS (ros2) |
| --- | --- | --- | --- |
| Purpose | API smoke, fast regression | Agent ECLSS operation verification | Full device simulation |
| Implementation | Python | Python | ROS 2 / C++ |
| Crew metabolism | Fixed CO₂ growth | CO₂, O₂, water, urine, condensate | Crew metabolic model |
| WRS | Not implemented | Urine/grey buffers, recovery, brine | Distillation, filtration, water quality |
| CO₂ state | Single storage pool | `cabin_co2_kg` + `captured_co2_kg` | Cabin + processing tanks |
| Mass ledger | Approximate | Per-operation ledgers in tests | Internal physics |
| Deterministic | Yes | Yes | Depends on run conditions |
| Docker required | No | No | Yes |

---

## Quick start

```bash
# Labeled rule-base run (no Docker)
python3 -m tools.cli run ssos_eclss_loop \
  --backend plant_sim --agents-mode labeled_rule_base --steps 72 \
  --run-id plant-sim-demo

# Or via scenario module
python3 -m scenario.ssos_eclss_loop.scenario_run \
  --backend plant_sim --agents-mode labeled_rule_base --steps 72
```

Set `backend.kind: plant_sim` in `scenario.yaml`, or export `SSOS_ECLSS_BACKEND=plant_sim`.

`plant_sim` implements `advance_step()` for crew metabolism (same hook as other step-advanceable backends). Scenario steps are 0-based (`0 .. steps-1`). Step 0 observes the configured initial state without advancing; before each later step the runner calls `advance_step()` once. At step index `N`, `advance_step` has run `N` times and `simulation_time_s = N * step_seconds`. An N-step run therefore ends at step `N-1` with clock `(N - 1) * step_seconds`.

---

## Configuration

Parameters load from `scenario.yaml` under `plant_sim:` (nested keys) plus `simulation:` initial inventories. See `PlantSimConfig.from_scenario_config()` in `config.py`.

```yaml
backend:
  kind: plant_sim

simulation:
  initial_co2_storage_kg: 1.5      # → initial_cabin_co2_kg
  initial_o2_storage_kg: 0.48
  initial_product_water_l: 100.0

plant_sim:
  time:
    step_seconds: 1200             # observation interval (20 min)
    ars_operation_seconds: 4800    # per ARS action quantum
  crew:
    size: 4
    co2_kg_day_person: 1.04        # BVAD-derived
  ars:
    capacity_kg_day: 4.50
    capture_efficiency: 0.83
    reference_goal_co2_kg: 1.8
  ogs:
    max_o2_kg_day: 9.25
  wrs:
    urine_recovery: 0.98
    grey_recovery: 0.90
    max_feed_l_per_operation: 10.0
```

### Parameter classes

| Class | Meaning | Examples |
| --- | --- | --- |
| **Source-derived** | SSOS-validated macro rates or exact stoichiometry | crew BVAD rates, ARS capacity, electrolysis ratios |
| **Scenario-tuned** | Chosen so the teaching scenario runs plausibly — **not** ISS limits | initial inventories, kg thresholds, `ogs_goal.input_water_mass: 0.15` in `agents.yaml` |

Do not describe scenario-tuned values as physical ISS limits.

---

## Telemetry mapping

`poll_telemetry()` exposes the standard `EclssTelemetrySnapshot` fields agents already use:

| Snapshot field | Plant Sim source |
| --- | --- |
| `co2_storage_kg` | `cabin_co2_kg` (danger signal — **not** captured tank) |
| `o2_storage_kg` | `available_o2_kg` |
| `product_water_reserve_l` | `product_water_l` |
| `grey_water_collected_l` | `grey_water_l` |

Extra state is under `raw_topics.plant_sim`. Example at scenario step 5 with `step_seconds: 1200` (`simulation_time_s = 5 * 1200` after five advances):

```json
{
  "step": 5,
  "co2_storage_kg": 1.42,
  "o2_storage_kg": 0.51,
  "product_water_reserve_l": 98.2,
  "raw_topics": {
    "plant_sim": {
      "simulation_time_s": 6000.0,
      "captured_co2_kg": 0.12,
      "urine_buffer_l": 0.35,
      "total_co2_vented_kg": 0.08,
      "total_h2_vented_kg": 0.01,
      "total_ch4_vented_kg": 0.02,
      "total_wrs_brine_loss_l": 0.15,
      "total_o2_shortfall_kg": 0.0,
      "total_water_shortfall_l": 0.0
    }
  }
}
```

The Streamlit dashboard shows a **plant_sim ledgers** panel when these topics are present (`ssos_views.render_plant_sim_panel`).

---

## Subsystem behavior (high level)

```text
product water ──► crew ──► urine / condensate ──► WRS ──► product water
                 │                              └──► brine loss
                 └──► OGS ──► O₂ + H₂ ──► Sabatier ──► water + CH₄ vent
cabin CO₂ ──► ARS ──► captured CO₂ ──► Sabatier
              └──► CO₂ vent
```

- **ARS:** goal-scaled removal from cabin CO₂; capture efficiency splits captured vs vented.
- **OGS:** electrolysis from product water; stoichiometry from molecular weights (`stoichiometry.py`).
- **Sabatier:** runs inside OGS action; uses `captured_co2_kg` (default policy does **not** call `request_co2` before OGS).
- **WRS:** processes internal urine/grey buffers; `WrsGoal.urine_volume` is max liters from the urine buffer, not external makeup water.

### Failure and validation

- Subsystem failure (`set_subsystem_failure`) blocks mutations for that subsystem's actions.
- Invalid goals (negative, NaN, Inf) are rejected before state changes.
- Partial grants when inventory or capacity is insufficient; services return `success=False` when the full request cannot be met.

---

## Mass balance

The plant is **not** a closed system (vents, brine, unrecoverable crew water). Tests verify per-operation ledgers — see `tests/environment/test_plant_sim_mass_balance.py`.

---

## Guarantees and non-guarantees

### Guarantees

- Same config and command sequence → same results (deterministic).
- Inventories stay finite and non-negative.
- Major operations have explainable mass ledgers.
- Agents can swap `mock` / `plant_sim` / `ros2` through the same `EclssBackend` API.

### Non-guarantees

- Numerical match with SSOS or ISS exposure limits.
- Device startup transients, breakthrough, thermal, or electrical behavior.
- Potable-water quality or ROS communication faults.

---

## Related

| Document / path | Content |
| --- | --- |
| [scenario-ssos-eclss-loop.md](../../scenario-ssos-eclss-loop.md) | Scenario spec and run commands |
| [ssos/eclss-integration.md](../../ssos/eclss-integration.md) | `EclssBackend` implementations |
| [api-contracts.md](../../api-contracts.md) | JSONL schemas |
| `src/environment/ssos/eclss/plant_sim/` | Implementation |
| `tests/environment/test_plant_sim_*.py` | Model, backend, balance, invariant tests |
