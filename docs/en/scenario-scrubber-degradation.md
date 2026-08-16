
# Scenario: scrubber_degradation

Reference scenario for the **ECLSS** (Environmental Control and Life Support System) resilience-loop MVP. Observe how an agent team detects and recovers from a single anomaly — CO2 scrubber performance degradation in life-support equipment — and what permanent design it proposes afterward.

> Run commands: [Overview](overview.md#how-to-run). Architecture: [architecture.md](architecture.md).

---

## Background and purpose

In a closed space-station environment, scrubber (CO2 removal) efficiency loss leads to CO2 accumulation and trade-offs with the power system (fan load, EPS support).

This scenario is a **minimal reproducible experiment** to answer:

1. How telemetry degrades after anomaly injection (baseline)
2. Whether a rule-based team recovers according to thresholds (reproducible scaffold)
3. Whether an LLM team differs in timing, utterances, and proposals in the same situation (comparison experiment)
4. What permanent design (bypass plumbing, parameter changes, etc.) is proposed after the run

**Topology does not change at runtime.** Temporary operations (recovery commands) are separated from permanent proposals (`design_proposals.json`).

---

## Narrative (timeline)

### No agents (`agents.mode: none`)

| Phase | Steps | Contents |
| --- | --- | --- |
| Equilibrium | 1–19 | CO2 ≈ 800 ppm (health warning band boundary), scrubber efficiency ≈ 0.95 |
| Anomaly start | 20 | `scrubber_degradation` injected |
| Degradation | 20–50 | efficiency −0.02/step, CO2 production 1.4×, power margin −3 W/step |
| Health worsening | ~30+ | CO2 exceeds 1200 ppm → **critical** (`CO2_WARNING_PPM`) |
| Response | — | **none** (no agents) |

The baseline run is the reference curve for “what happens if the anomaly is left alone.”

### labeled_rule_base (rule team)

| Phase | Steps (approx.) | Contents |
| --- | --- | --- |
| Equilibrium | 1–19 | same as above |
| Anomaly | 20+ | diagnosis messages, efficiency drop |
| Policy alert | CO2 ≥ 1000 ppm | alert, full fan (`co2_recovery_ppm` — **separate from health thresholds**) |
| Power crisis | power margin ≤ −150 W | load reduction, `request_eps_boost` (`power_status: critical`) |
| Additional recovery | high CO2 + fan applied | `enable_bypass` (temporary) |
| Recovery | ~40+ | CO2 returns below warning band (< 1200 ppm) |
| Post-run | after run | permanent bypass **edge** proposal (`design_proposals.json`) |

Regression expects `final_co2_ppm < CO2_WARNING_PPM` (1200).

### llm (LLM team)

Life-support simulation phases are the same. Recovery **order, timing, and utterances** depend on the model. Post-run proposals are LLM-generated `changes` (e.g. `set_parameter` to raise scrubber efficiency, `add_node` for a bypass valve). Compare with labeled or other models in the dashboard.

---

## Configuration files

| File | Purpose |
| --- | --- |
| [`scenario.yaml`](https://github.com/hirototamura/engineering_agents/blob/main/src/scenario/scrubber_degradation/scenario.yaml) | Step count, initial state, design parameters, anomaly, `agents.mode`, run ID |
| [`agents.yaml`](https://github.com/hirototamura/engineering_agents/blob/main/src/scenario/scrubber_degradation/agents.yaml) | Team, Persona, memory, `policy` (labeled only), Ollama / vLLM settings |

### scenario.yaml (main fields)

```yaml
simulation:
  steps: 50
  initial_co2_ppm: 800.0
  initial_power_margin_w: 150.0

anomalies:
  - name: scrubber_degradation
    start_step: 20
    scrubber_efficiency_decay_per_step: 0.02
    power_margin_decay_per_step: 3.0
    co2_production_multiplier: 1.4

agents:
  mode: none  # none | labeled_rule_base | llm

output:
  run_id: scrubber_degradation_baseline
  run_id_labeled_rule_base: scrubber_degradation_labeled_rule_base
  run_id_llm: scrubber_degradation_llm
```

### agents.yaml (main fields)

```yaml
team:
  count: 4
  id_prefix: engineer
  # Optional thinking-style lenses (round-robin → engineer_1..N). Affect llm prompts only;
  # labeled_rule_base ignores personas. Logged in summary.json["archetypes"] always.
  archetypes: [first_principles, failure_mode, improviser, systems_integrator]
  persona: |
    Closed-habitat ECLSS colleague engineer. ...

policy:          # labeled_rule_base only
  co2_recovery_ppm: 1000
  fan_speed: 1.0
  enable_bypass: true
  request_eps_boost_on_power_critical: true
  eps_boost_w: 120.0
  bypass_edge:
    node_a: manifold
    node_b: scrubber
    kind: bypass

llm:
  base_url: http://localhost:11434
  model: gemma4:e4b
  temperature: 0.45
```

Runtime override:

```python
from scenario.runner import run_scenario

run_scenario(
    "scrubber_degradation",
    overrides={"agents": {"mode": "llm"}},
)
```

Example with a different model and run name:

```python
run_scenario(
    "scrubber_degradation",
    overrides={
        "agents": {"mode": "llm", "llm": {"model": "qwen2.5:latest"}},
        "output": {"run_id_llm": "scrubber_degradation_llm_qwen2.5_latest"},
    },
)
```

---

## Simulation world

### Terminology

| Abbrev. | English name | Meaning in this scenario |
| --- | --- | --- |
| **ECLSS** | Environmental Control and Life Support System | **Life-support equipment** — graph of scrubber, manifold, habitable space (cabin) |
| **EPS** | Electrical Power System | Generation, storage, distribution. Temporary support to ECLSS via `request_eps_boost` |
| **SARJ** | Solar Alpha Rotary Joint | Solar-array generation (`MockSarj`) |
| **BCDU** | Battery Charge/Discharge Unit | Battery discharge. `bcdu_mode` in `eps_telemetry.jsonl` |
| **MBSU** | Main Bus Switching Unit | Real EPS main bus (not individually implemented in this MVP mock) |
| **DDCU** | Direct Current-to-Direct Current Converter Unit | Real EPS DC-DC conversion (not individually implemented in this MVP mock) |
| **Node** | — | `cabin`, `manifold`, `scrubber`, `power_bus` |
| **Recovery command** | — | Temporary runtime operation (table below) |
| **Design proposal** | — | Permanent post-run change (`design_proposals.json`) |

### Health thresholds (telemetry)

`health_metrics.jsonl` — same as [api-contracts.md](api-contracts.md):

| Metric | safe | warning | critical |
| --- | --- | --- | --- |
| CO2 (ppm) | < 800 | 800 to < 1200 | ≥ 1200 |
| Power margin (W) | > 0 | 0 to < −150 | ≤ −150 |

### Initial topology

```text
  cabin ──flow──► manifold ──flow──► scrubber ──flow──► cabin
                                        ▲
                                        │ power
                                   power_bus
```

| Node | kind | Role |
| --- | --- | --- |
| `cabin` | volume | CO2 production, habitable space |
| `manifold` | manifold | Air distribution |
| `scrubber` | scrubber | CO2 removal (efficiency drops under anomaly) |
| `power_bus` | electrical | Scrubber drive power |

### Recovery commands (runtime)

| kind | Effect (summary) |
| --- | --- |
| `set_fan_speed` | Faster scrubber airflow → higher removal rate, higher power draw |
| `enable_bypass` | Temporary bypass path → flow bonus |
| `reduce_load` | Reduce metabolic load → lower CO2 production |
| `request_eps_boost` | BCDU discharge → grant `eps_support_w` for a fixed number of steps |

None of these **change permanent topology**. `enable_bypass` is an operational flag, separate from `add_edge` in `design_proposals` (permanent bypass plumbing).

---

## Agent team design

### N engineers + representative action (+ optional archetypes)

| Concept | Description |
| --- | --- |
| `team.count` | Number of engineers (default 4) |
| `team.archetypes` | Optional list of thinking lenses (`first_principles`, `failure_mode`, `improviser`, `systems_integrator`). Round-robin assignment. Omit or `[]` for homogeneous persona |
| deliberation | llm: one round for all agents (persona includes lens when archetypes set). labeled: rules emit alert/diagnosis |
| action rep | `engineer_{(step-1) % N}` issues commands for that step |
| post-run rep | representative at the final step writes `design_proposals.json` |

### labeled_rule_base vs llm

| | labeled_rule_base | llm |
| --- | --- | --- |
| Decision | `policy` thresholds | Persona + Telemetry + discussion |
| Reproducibility | High | Model-dependent |
| Post-run proposal | Fixed `bypass_edge` | LLM generates `changes` |
| Research use | Ground-truth comparison, regression | Model comparison, utterance analysis |

Why the LLM does not read `policy`: to avoid mixing rule answers into the prompt and enable **fair comparison experiments**. Design details: [memo/agents/homogeneous_agent_team_plan.md](memo/agents/homogeneous_agent_team_plan.md).

---

## How to read outputs

### File list

| File | When to read |
| --- | --- |
| `telemetry.jsonl` | CO2, efficiency, power time series |
| `eps_telemetry.jsonl` | EPS boost, BCDU mode |
| `messages.jsonl` | Agent utterances, reasoning |
| `events.jsonl` | Anomaly injection, `recovery_applied` |
| `design_state.jsonl` | Topology during run (effectively invariant) |
| `design_proposals.json` | **Post-run permanent proposal** (source for dashboard After preview) |
| `summary.json` | One-page summary (peak CO2, eps_boost step, etc.) |
| `provenance.jsonl` | One Piece compatible (currently mainly EPS recovery) |

### design_proposals.json (example: labeled_rule_base)

```json
{
  "proposed_by": "engineer_2",
  "decision_source": "rule",
  "message": "Propose permanent bypass plumbing between manifold and scrubber.",
  "reasoning": "Repeated anomaly and high CO2 during the run; ...",
  "changes": [
    {
      "change_kind": "add_edge",
      "payload": {"node_a": "manifold", "node_b": "scrubber", "kind": "bypass"}
    }
  ],
  "baseline_topology": { "nodes": [...], "edges": [...] }
}
```

In LLM mode, `decision_source: "llm"` and `changes` may include `add_node` (`bypass_valve`), `set_parameter`, etc.

### KPIs in summary.json

| Field | Meaning |
| --- | --- |
| `peak_co2_ppm` | Maximum CO2 during run |
| `final_co2_ppm` | CO2 at final step |
| `eps_boost_applied_step` | First step EPS boost took effect |
| `co2_above_threshold_step` | Step when CO2 reached `CO2_WARNING_PPM` (1200 ppm) or above |
| `co2_recovered_below_threshold_step` | Step when CO2 returned below `CO2_WARNING_PPM` (1200 ppm) (after `co2_above_threshold_step` was set) |
| `design_proposal_count` | Number of post-run change entries |
| `provenance_record_count` | Number of provenance lines (mainly recovery) |
| `archetypes` | Map `agent_id` → lens name for composition→outcome studies (`{}` when archetypes disabled) |

---

## Using the dashboard

1. **Overview** — select two runs and compare CO2, power, and efficiency at the same step
2. **Step replay** — follow one run step by step; read reasoning at step 17, etc., to see why EPS boost was requested
3. **Design proposal section** — confirm permanent change proposals in Before / After graphs (red dashed line = proposed edge)

Screenshots: [Overview](overview.md#dashboard-at-a-glance).

---

## Tests

| Test | Mode | Verification |
| --- | --- | --- |
| `test_scrubber_baseline.py` | `none` | Anomaly, CO2 rise, no agents |
| `test_scrubber_with_agents.py` | `labeled_rule_base` | Recovery, final CO2 < 1200 (below warning), post-run bypass proposal, no bypass edge at runtime |
| same | `llm` (Fake) | deliberation/action, post-run proposal, no rule fallback |

```bash
pytest tests/scenario/test_scrubber_baseline.py -q
pytest tests/scenario/test_scrubber_with_agents.py -q
```

---

## Related documentation

- [architecture.md](architecture.md) — layers and execution flow
- [api-contracts.md](api-contracts.md) — JSONL schemas
- [one-piece-integration.md](one-piece-integration.md) — provenance
- [development-plan.md](development-plan.md) — completion status and next tasks (CLI, Phase 8, provenance extension)
- [scenario-ssos-eclss-loop.md](scenario-ssos-eclss-loop.md) — SSOS live ECLSS scenario (Phase 0–7 complete)
- [memo/ssos_eclss_loop/ssos_eclss_loop_connection_plan.md](memo/ssos_eclss_loop/ssos_eclss_loop_connection_plan.md) — connection plan details and verification steps
- [memo/backlog.md](memo/backlog.md) — BL-001–BL-005
