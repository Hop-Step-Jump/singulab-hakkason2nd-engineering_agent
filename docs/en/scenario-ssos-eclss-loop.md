
# Scenario: ssos_eclss_loop

Reference scenario where an **agent team** operates real ROS2 **ECLSS** (Environmental Control and Life Support System) inside **SSOS** (Space Station OS) Docker instead of Crew Simulation. The team monitors **storage kg** for CO₂ / O₂ / product water, issues operational commands (ARS / OGS, etc.) when thresholds are exceeded, and proposes permanent `ssos_graph` design after the run.

> Run commands: [Overview](overview.md#how-to-run) and [How to run](#how-to-run) below. Architecture: [architecture.md](architecture.md). Contrast with scrubber: [scenario-scrubber-degradation.md](scenario-scrubber-degradation.md).

---

## Difference from scrubber_degradation

| Aspect | scrubber_degradation | ssos_eclss_loop |
| --- | --- | --- |
| Backend | `StationSimulator` (Python mock) | `EclssBackend` (`LoopMockEclssBackend` / `PlantSimEclssBackend` / `Ros2EclssBridge`) |
| Telemetry | CO₂ ppm, scrubber efficiency, power margin | `/co2_storage`, `/o2_storage`, `/wrs/product_water_reserve` (kg / L) |
| Runtime ops | Recovery commands (fan, EPS boost, etc.) | Operational commands (ARS Action, OGS Action, CO₂ Service, etc.) |
| Post-run proposals | Scrubber topology (`add_edge`, etc.) | `design_domain: ssos_graph` (`action_profile`, `graph_rewire`, etc.) |
| Environment | Host Python only | `mock` / `plant_sim` on host OK. **ros2** requires SSOS Docker + ECLSS headless |
| Status | Mock frozen | Phase 0–7 complete (launch remap is Phase 8 backlog) |

---

## Background and goals

SSOS ECLSS controls **CO₂ removal (ARS)**, **O₂ generation (OGS / Sabatier)**, and **water recovery (WRS)** via ROS2 Actions and Services. This scenario replaces Crew Simulation with a **homogeneous team of N engineers** calling the same interfaces through `EclssBackend`.

Questions this scenario answers:

1. When storage thresholds are exceeded, can a rule-based team start ARS / OGS in the correct order?
2. How does an LLM team judge Sabatier CO₂ requests and OGS timing?
3. Do operational logs (`operational_applied`) and provenance align with the One Piece model?
4. After the run, can permanent proposals (`action_profile`, `graph_rewire`, etc.) be applied to the next run via `--apply-proposals`?

**The SSOS graph does not change at runtime.** Operational commands and post-run `design_proposals.json` are separated (same design principle as scrubber).

---

## SSOS ECLSS subsystems

```text
  [habitat / metabolism] ──CO₂──► /co2_storage ──► ARS (air_revitalisation)
                                                      │
  /o2_storage ◄── OGS (oxygen_generation) ◄──┘  Sabatier (CO₂ feedstock)
       │
       └── request_o2 / request_co2 (Service)

  /wrs/product_water_reserve ◄── WRS (water_recovery_systems)  ※ ros2 bridge implemented
```

| Abbrev. | Full name | Role in this scenario |
| --- | --- | --- |
| **ARS** | Air Revitalisation System | CO₂ removal from storage (`air_revitalisation` Action) |
| **OGS** | Oxygen Generation System | O₂ generation (`oxygen_generation` Action). Sabatier needs CO₂ feedstock |
| **WRS** | Water Recovery System | Water recovery (`water_recovery_systems` Action) — team operation is backlog (BL-004) |

### ROS2 interfaces (main)

| Kind | Name | Purpose |
| --- | --- | --- |
| Action | `air_revitalisation` | Start ARS cycle |
| Action | `oxygen_generation` | Start OGS cycle |
| Action | `water_recovery_systems` | Start WRS cycle |
| Service | `/ars/request_co2` | CO₂ supply for Sabatier |
| Service | `/ogs/request_o2` | O₂ withdrawal |
| Topic | `/co2_storage` | CO₂ storage (kg) |
| Topic | `/o2_storage` | O₂ storage (kg) |
| Topic | `/wrs/product_water_reserve` | Product water (L) |

Type constants: `src/environment/ssos/eclss/ros2/topics.py`. Bridge: `src/environment/ssos/eclss/ros2/bridge.py`.

---

## Narrative (timeline)

### No agents (`agents.mode: none`)

| Phase | Content |
| --- | --- |
| Each step | `poll_telemetry()` only. No operational commands |
| mock | CO₂ increases by `co2_growth_kg_per_step` each step (default +0.06 kg/step) |
| ros2 | Natural dynamics of the live SSOS plant (left idle without Crew Simulation) |
| Post-run | No `design_proposals.json` |

Baseline runs show how storage evolves without agent intervention.

### labeled_rule_base

`thresholds` in `scenario.yaml` are **storage thresholds**; `policy` in `agents.yaml` is the **operational profile** (goal fields, whether to request CO₂ before OGS).

| Condition (typical) | Operational command |
| --- | --- |
| CO₂ ≥ `co2_storage_high_kg` (default 1.5 kg) | `air_revitalisation` (ARS) |
| O₂ ≤ `o2_storage_low_kg` (default 0.45 kg) | `oxygen_generation` (OGS); optional `request_co2` first when `request_co2_before_ogs: true` (default **false**) |

**`request_co2_before_ogs`:** default off so feedstock matches real SSOS (OGS calls `/ars/request_co2` itself). Opt-in `true` (including via design proposals) can **double-debit CO₂ on LoopMock** in the same step: explicit `request_co2` plus OGS Sabatier storage subtract — LoopMock has no intermediate CO₂ buffer.

**Re-arm**: If storage does not improve after ARS / OGS, the next step can retry (`co2_at_ars_dispatch` / `o2_at_ogs_dispatch` boundaries).

Steps are 0-based (`0 .. steps-1`). Representative operator `eclss_operator_{step % N}` issues commands for that step. Post-run, the representative outputs `design_proposals.json` (`ssos_graph`).

### llm

Each step: all N agents deliberate → representative issues `operational_command` (JSON `commands`) → one post-run `changes` proposal. `policy` thresholds are not included in prompts (same as scrubber).

---

## Configuration files

| File | Purpose |
| --- | --- |
| [`scenario.yaml`](https://github.com/hirototamura/engineering_agents/blob/main/src/scenario/ssos_eclss_loop/scenario.yaml) | Step count, initial storage, backend kind, thresholds, `agents.mode`, run ID |
| [`agents.yaml`](https://github.com/hirototamura/engineering_agents/blob/main/src/scenario/ssos_eclss_loop/agents.yaml) | Team (`eclss_operator_*`), Persona, `policy` (labeled only), Ollama |

### scenario.yaml (main fields)

```yaml
simulation:
  steps: 8
  initial_co2_storage_kg: 1.5
  initial_o2_storage_kg: 0.48
  initial_product_water_l: 100.0

backend:
  kind: mock  # mock | plant_sim | ros2 — also overridable via SSOS_ECLSS_BACKEND env var

mock_dynamics:
  co2_growth_kg_per_step: 0.06
  ars_co2_reduction_kg: 0.35
  ogs_o2_gain_kg: 0.1

thresholds:
  co2_storage_high_kg: 1.5
  co2_storage_critical_kg: 2.2
  o2_storage_low_kg: 0.45
  product_water_low_l: 50.0

# Off by default. Enable with --inject-failures or inject_failures: true
inject_failures: false
subsystem_failures:
  - subsystem: ars   # ars | ogs | wrs
    start_step: 10   # inclusive (0-based)
    end_step: 20     # optional, exclusive

agents:
  mode: none  # none | labeled_rule_base | llm

output:
  run_id: ssos_eclss_loop_baseline
  run_id_labeled_rule_base: ssos_eclss_loop_labeled_rule_base
  run_id_llm: ssos_eclss_loop_llm
```

`ssos_graph.rewires` (optional) — when merged via `--apply-proposals` from a prior `graph_rewire` proposal, client remaps are passed to `Ros2EclssBridge` on the next run.

### Subsystem failure schedule (`subsystem_failures`)

Inject ARS / OGS / WRS failures at chosen steps. **Off by default** (`inject_failures: false`). Enable with `ea run ssos_eclss_loop --inject-failures` or `--set inject_failures=true`. The scenario layer then calls `EclssBackend.set_subsystem_failure` each step; the same YAML works for `mock`, `plant_sim`, and `ros2`.

| Field | Required | Meaning |
| --- | --- | --- |
| `subsystem` | yes | `ars` / `ogs` / `wrs` (`ARS_failure` form also accepted) |
| `start_step` | yes | Failure onset step (inclusive, 0-based) |
| `end_step` | no | End step (**exclusive**). If omitted, stays failed until run end |
| `duration_steps` | no | Alternative to `end_step` (cannot set both; must be >= 1) |

- Any subsystem listed in the schedule is owned by the schedule for the run (cleared when no entry is active).
- Transitions emit `subsystem_failure_applied` in `events.jsonl`.
- Telemetry flags (`ars_failure_enabled`, etc.) feed the dashboard anomaly view.
- Separate from scrubber `anomalies:` / `inject_anomaly` (not an efficiency-decay schedule).

### agents.yaml (main fields)

```yaml
team:
  count: 3
  id_prefix: eclss_operator

policy:   # labeled_rule_base only. Thresholds merged from scenario.yaml at runtime
  request_co2_before_ogs: false
  request_co2_amount: 0.025
  ars_goal:
    initial_co2_mass: 1.8
  ogs_goal:
    input_water_mass: 0.015

llm:
  base_url: http://localhost:11434   # Docker: host.docker.internal (set by ea-loop)
  model: gemma4:e4b
```

---

## Simulation world

### Health thresholds (storage)

`health_metrics.jsonl` — `compute_eclss_storage_health()` (`src/scenario/ssos_eclss_loop/health.py`):

| Metric | safe | warning | critical |
| --- | --- | --- | --- |
| CO₂ storage (kg) | < high (1.5) | high to < critical | ≥ critical (2.2) |
| O₂ storage (kg) | > low (0.45) | low×0.75 to low | ≤ low×0.75 (0.3375) |
| Product water (L) | > low (50) | low×0.5 to low | ≤ low×0.5 (25) |
| `overall` | all safe | worse of the two | worse of the two |

Agent operational triggers (`co2_storage_high_kg`, etc.) come from `scenario.yaml` `thresholds`. Health bands are recorded independently from telemetry.

### Operational commands (runtime)

| `kind` | Backend call | Effect (summary) |
| --- | --- | --- |
| `air_revitalisation` | `send_air_revitalisation_goal()` | ARS cycle — CO₂ removal |
| `oxygen_generation` | `send_oxygen_generation_goal()` | OGS cycle — O₂ generation |
| `water_recovery_systems` | `send_water_recovery_goal()` | WRS cycle (`plant_sim` and `ros2`; LoopMock not implemented) |
| `request_co2` | `request_co2(amount)` | Sabatier feedstock supply |
| `request_o2` | `request_o2(amount)` | O₂ withdrawal |

None of these are **permanent graph changes**. In `events.jsonl` they are recorded as `/eclss/events/operational_applied`.

### graph_rewire (client remap — Phase 7)

`graph_rewire` in `design_proposals.json` or `ssos_graph.rewires` in `scenario.yaml` causes `Ros2EclssBridge` on the **next run** to replace topic names client-side for `ros2 topic echo`, etc. (`environment/ssos/eclss/ros2/graph_rewire.py`).

ROS launch-file remap (Phase 8): [backlog BL-003](memo/backlog.md#bl-003).

---

## Agent team design

### Homogeneous N agents + representative action

| Concept | ssos_eclss_loop |
| --- | --- |
| IDs | `eclss_operator_1` … `eclss_operator_N` (default 3) |
| deliberation | llm: one round for all. labeled: operational decision messages |
| action rep | `eclss_operator_{step % N}` (0-based steps) |
| post-run rep | Representative at final step outputs `design_proposals.json` when `changes` is non-empty |

`SsosEclssLoopTeam` extends the `Team` ABC. Signatures: `run_step(backend, obs)` / `apply_outcome(backend, outcome)`.

### labeled_rule_base vs llm

| | labeled_rule_base | llm |
| --- | --- | --- |
| Decisions | `thresholds` + `policy` profile | Persona + storage telemetry + discussion |
| Reproducibility | High | Model-dependent |
| Post-run proposals | Rule-based `ssos_graph` (non-empty when written; L8 fallback bumps goals/thresholds) | LLM generates `changes` (file omitted if empty) |
| provenance | `operational_applied` → `record_type: operational` | Same |

---

## How to run { #how-to-run }

### mock (host, no ROS2)

```bash
python -m scenario.ssos_eclss_loop.scenario_run --backend mock --agents-mode labeled_rule_base
python -m scenario.ssos_eclss_loop.scenario_run --backend mock --agents-mode llm
```

### plant_sim (host, mass-balance plant)

Deterministic crew + ARS/OGS/Sabatier/WRS model with explainable ledgers. No Docker.

```bash
python -m scenario.ssos_eclss_loop.scenario_run --backend plant_sim --agents-mode labeled_rule_base --steps 72
python3 -m tools.cli run ssos_eclss_loop --backend plant_sim --agents-mode labeled_rule_base --steps 72
```

Details: [Plant Sim backend](memo/ssos_eclss_loop/plant_sim_backend.md).

### ros2 (SSOS Docker)

```bash
# Terminal 1: ECLSS headless inside SSOS container
~/dev/ssos/ssos-run.sh
# Inside container: bash /root/ssos-eclss-headless.sh

# Terminal 2: host repo root
./scripts/run_ssos_eclss_loop.sh --agents-mode labeled_rule_base
./scripts/run_ssos_eclss_loop.sh --agents-mode llm
```

Inside container directly: `ea-loop --agents-mode labeled_rule_base` (default `OLLAMA_BASE_URL=host.docker.internal`).

### Apply prior run design proposals to next run

`--apply-proposals` merges into the **in-memory** config **before simulation starts**; on-disk `scenario.yaml` / `agents.yaml` are not rewritten. The effective configs are written to `scenario_config.yaml` / `agents_config.yaml` in the run directory.

```bash
python -m scenario.ssos_eclss_loop.scenario_run --backend mock --agents-mode llm \
  --apply-proposals src/experiments/results/ssos_eclss_loop_llm/design_proposals.json
```

### graph_rewire E2E smoke

```bash
./scripts/run_graph_rewire_e2e.sh   # requires ECLSS headless
```

---

## Reading outputs

### File list

| File | When to read |
| --- | --- |
| `telemetry.jsonl` | CO₂/O₂/water storage time series (kg / L) |
| `health_metrics.jsonl` | Storage-based safe / warning / critical |
| `messages.jsonl` | `operational_command`, deliberation, reasoning |
| `events.jsonl` | `operational_applied` / `operational_rejected` |
| `design_state.jsonl` | `ssos_graph` snapshot each step (includes rewires) |
| `design_proposals.json` | Post-run permanent `ssos_graph` proposals (written only when `changes` is non-empty) |
| `scenario_config.yaml` | Effective scenario config (after overrides / `--apply-proposals`) |
| `agents_config.yaml` | Effective agents config (when mode ≠ none) |
| `summary.json` | Peak CO₂, operational count, backend kind, etc. |
| `provenance.jsonl` | Operational records (`record_type: operational`) |

**Scrubber-only fields not in ssos**: `eps_telemetry.jsonl`, ppm-based recovery events.

### telemetry.jsonl (example)

```json
{
  "step": 3,
  "co2_storage_kg": 1.68,
  "o2_storage_kg": 0.465,
  "product_water_reserve_l": 100.0
}
```

### design_proposals.json (ssos_graph)

```json
{
  "design_domain": "ssos_graph",
  "proposed_by": "eclss_operator_2",
  "decision_source": "rule",
  "message": "Raise ARS initial_co2_mass for faster vent cycles.",
  "changes": [
    {
      "change_kind": "action_profile",
      "payload": {
        "action": "air_revitalisation",
        "fields": {"initial_co2_mass": 2000.0}
      }
    }
  ],
  "baseline_graph": {"rewires": []}
}
```

| `change_kind` | Purpose |
| --- | --- |
| `action_profile` | Permanent Action goal field adjustments |
| `service_config` | Service call amounts and order |
| `set_parameter` | Threshold / policy parameters |
| `graph_rewire` | Client topic remap manifest for next run |

### KPIs in summary.json

| Field | Meaning |
| --- | --- |
| `backend` | `mock` or `ros2` |
| `peak_co2_storage_kg` | Maximum CO₂ storage during run |
| `final_co2_storage_kg` / `final_o2_storage_kg` | Storage at final step |
| `operational_command_count` | Operational commands issued |
| `ogs_invoked_step` / `co2_requested_step` | First OGS / request_co2 step |
| `design_proposal_count` | Post-run change count |
| `provenance_record_count` | Operational provenance row count |
| `telemetry_topics_read` | Topic names read in ros2 mode |

---

## Dashboard views

Runs with `summary.scenario == "ssos_eclss_loop"` branch to `src/tools/dashboard/ssos_views.py`. Overview / replay sliders use telemetry min/max, so 0-based ssos steps (`0 .. steps-1`) work alongside 1-based scrubber runs.

1. **Overview** — CO₂ / O₂ / water storage kg plots, health cards, 2-run compare
2. **Step replay** — `operational_applied` timeline, utterances / reasoning, storage plots
3. **Design proposals** — `ssos_graph` `action_profile` / `graph_rewire` preview

Scrubber screenshots: [Overview](overview.md#dashboard-at-a-glance).

---

## Tests

| Test | Content |
| --- | --- |
| `test_ssos_eclss_loop_team.py` | `SsosEclssLoopTeam`, labeled / llm, Team inheritance |
| `test_ssos_eclss_loop_scenario.py` | mock scenario end-to-end |
| `test_graph_rewire.py` | client remap unit |
| `test_graph_rewire_integration.py` | `Ros2EclssBridge` integration (skipped without ROS) |

```bash
pytest tests/scenario/test_ssos_eclss_loop*.py -q
pytest tests/environment/test_graph_rewire*.py -q
```

Container E2E records: `memo/ssos_eclss_loop/e2e_records/` (repo only).

---

## Related documentation

- [architecture.md](architecture.md) — layers and ssos execution flow
- [api-contracts.md](api-contracts.md) — `EclssBackend`, JSONL, operational commands
- [one-piece-integration.md](one-piece-integration.md) — operational provenance
- [development-plan.md](development-plan.md) — Phase 0–7 complete, next tasks
- [memo/ssos_eclss_loop/ssos_eclss_loop_connection_plan.md](memo/ssos_eclss_loop/ssos_eclss_loop_connection_plan.md) — connection plan details and verification steps
- [memo/backlog.md](memo/backlog.md) — BL-003 (Phase 8), BL-004 (ECLSS follow-ups)
