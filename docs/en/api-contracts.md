
# API Contracts — Simulator Boundaries and Event Logs

When you change protocols or JSONL formats, **update this document at the same time**.

This repository has **two independent tracks**. Backend, telemetry, runtime commands, and post-run proposal schemas are **not shared** (only filenames overlap).

| | `scrubber_degradation` | `ssos_eclss_loop` |
| --- | --- | --- |
| Narrative | [scenario-scrubber-degradation.md](scenario-scrubber-degradation.md) | [scenario-ssos-eclss-loop.md](scenario-ssos-eclss-loop.md) |
| Backend | `SimulatorProtocol` | `EclssBackend` |
| Team | `ScrubberDegradationTeam` | `SsosEclssLoopTeam` |
| Telemetry | CO₂ ppm, power margin | CO₂/O₂/water storage (kg / L) |
| Runtime | `RecoveryCommand` | `EclssOperationalCommand` |
| Events | `recovery_applied` | `operational_applied` |
| Post-run | scrubber topology (`add_edge`, etc.) | `design_domain: ssos_graph` |
| provenance | `record_type: recovery` | `record_type: operational` |

---

## Shared

### Output directory

`src/experiments/results/<run_id>/` — use `scenario` in `summary.json` to identify the track.

Files present in both tracks:

| File | Role |
| --- | --- |
| `telemetry.jsonl` | Per-step telemetry (**schema differs per track**) |
| `health_metrics.jsonl` | Per-step health bands (**threshold definitions differ**) |
| `messages.jsonl` | Agent utterances (`message_type` differs) |
| `events.jsonl` | Runtime events (`kind` differs) |
| `design_state.jsonl` | Design snapshot at step start |
| `design_proposals.json` | Post-run permanent proposals (**`change_kind` differs**) |
| `summary.json` | Run summary |
| `provenance.jsonl` | One Piece compatible lineage ([one-piece-integration.md](one-piece-integration.md)) |

### design_proposals.json — shared fields

Both tracks write one file after the run. The simulator / SSOS graph is **not changed at runtime**.

| Field | Description |
| --- | --- |
| `proposed_by` | Action representative ID at final step |
| `decision_source` | `rule` or `llm` |
| `message` / `reasoning` | Proposal explanation |
| `changes` | List of permanent changes (`change_kind` + `payload` each) |
| `parse_notes` | LLM parse warnings (optional) |

Corresponds to `design_proposals_path` and `design_proposal_count` in `summary.json`.

### messages.jsonl — shared and track differences

| Field | Description |
| --- | --- |
| `step` | Step number |
| `from_role` / `to_role` | Speaker / recipient |
| `message` / `reasoning` | Body / rationale |
| `decision_source` | `rule` / `llm` / `llm_parse_fail`, etc. |
| `deliberation_phase` | `deliberation` / `action` / `post_run_proposal` (llm) |

| `message_type` | scrubber | ssos |
| --- | --- | --- |
| `alert` | ✓ threshold exceeded | — |
| `diagnosis` | ✓ anomaly flags | — |
| `recovery_command` | ✓ recovery decision | — |
| `operational_command` | — | ✓ operational decision |
| `comment` | ✓ deliberation | ✓ deliberation |
| `skip` | ✓ parse failure, etc. | ✓ parse failure, etc. |

Representative IDs: scrubber uses `engineer_*`, ssos uses `eclss_operator_*`. Full Persona text and `policy` values are not logged.

### provenance.jsonl — overview

Generated at run end by `src/integrations/one_piece/client.py`. Schema: `src/integrations/one_piece/ssot_schema.json`.

| `record_type` | Track | Source event |
| --- | --- | --- |
| `recovery` | scrubber | `/eclss/events/recovery_applied` (`request_eps_boost`) |
| `operational` | ssos | `/eclss/events/operational_applied` |

Post-run `design_proposals.json` → provenance is **not yet exported** (planned for both tracks).

---

## scrubber_degradation

CO₂ scrubber anomaly on Python mock (`StationSimulator`). Frozen.

### SimulatorProtocol

| Class | Purpose |
| --- | --- |
| `StationSimulator` | **Default** — ECLSS + EPS |
| `MockEclssSimulator` | Plant only (unit tests) |

| Method | Returns | Description |
| --- | --- | --- |
| `step()` | `TelemetrySnapshot` | Advance plant one tick |
| `apply_command(cmd)` | `CommandResult` | Temporary recovery action |
| `get_topology()` | `TopologyGraph` | Nodes / edges |
| `get_design_parameters()` | `dict[str, float]` | Mutable parameters |
| `get_design_state()` | `DesignState` | Topology + parameters |
| `inject_anomaly(spec)` | `None` | Anomaly schedule |

`apply_design_change` was removed in Phase 0. Permanent changes are post-run proposals only.

### TelemetrySnapshot — `telemetry.jsonl`

```json
{
  "step": 20,
  "co2_ppm": 1240.5,
  "scrubber_efficiency": 0.72,
  "power_margin_w": 45.0,
  "fan_speed": 0.7,
  "bypass_enabled": false,
  "load_reduced": false,
  "eps_support_w": 120.0,
  "eps_support_steps_remaining": 4,
  "anomaly_flags": ["scrubber_degradation"]
}
```

| Field | Description |
| --- | --- |
| `co2_ppm` | Habitable-space CO₂ concentration |
| `scrubber_efficiency` | Effective removal efficiency |
| `power_margin_w` | ECLSS net power margin |
| `eps_support_w` | Temporary EPS support watts |
| `anomaly_flags` | Active anomaly names |

When recovery commands run in a step, a second row may be appended with `"post_ops": true` (L5), mirroring `ssos_eclss_loop`. Readers prefer `post_ops` / the last row for that step so UI matches `summary.json`.

### RecoveryCommand — runtime

Temporary operation via `apply_command()`.

```json
{
  "kind": "set_fan_speed",
  "value": 1.0,
  "issued_by": "engineer_2"
}
```

| `kind` | `value` type | Description |
| --- | --- | --- |
| `set_fan_speed` | float 0–1 | Fan speed |
| `enable_bypass` | bool | Temporary bypass |
| `reduce_load` | bool | Reduce metabolic load |
| `request_eps_boost` | float W (0, 500] | EPS discharge support |

### Health — `health_metrics.jsonl`

`compute_health_metrics()` — `src/environment/scrubber/eclss_ops/telemetry.py`

```json
{"step": 5, "co2_status": "safe", "power_status": "safe", "overall": "safe"}
```

Same optional `"post_ops": true` duplicate-row rule as scrubber `telemetry.jsonl` when ops refresh health in-step.

| Metric | safe | warning | critical |
| --- | --- | --- | --- |
| CO₂ (ppm) | < 800 | 800 to < 1200 | ≥ 1200 |
| Power margin (W) | > 0 | 0 to < −150 | ≤ −150 |

`policy.co2_recovery_ppm` (default 1000), etc. are **recovery triggers**, separate from health bands.

### design_proposals.json — scrubber domain

| `change_kind` | Purpose |
| --- | --- |
| `add_edge` | New edge (flow / bypass / power) |
| `add_node` | New node |
| `set_parameter` | Design parameter |

```json
{
  "proposed_by": "engineer_2",
  "decision_source": "rule",
  "message": "Propose permanent bypass plumbing between manifold and scrubber.",
  "changes": [
    {
      "change_kind": "add_edge",
      "payload": {"node_a": "manifold", "node_b": "scrubber", "kind": "bypass"}
    }
  ],
  "baseline_topology": {
    "nodes": [{"id": "cabin", "name": "Cabin", "kind": "volume"}],
    "edges": [{"source": "manifold", "target": "scrubber", "kind": "flow"}]
  }
}
```

### Agent modes

| `agents.mode` | Team | Runtime | Post-run |
| --- | --- | --- | --- |
| `none` | — | sim only | — |
| `labeled_rule_base` | `ScrubberDegradationTeam` | policy-driven recovery | rule |
| `llm` | same | LLM `commands` | llm |

#### messages.jsonl examples

```json
{
  "step": 33,
  "from_role": "engineer_2",
  "to_role": "team",
  "message": "CO2 at 1016 ppm exceeds recovery band 1000 ppm.",
  "message_type": "alert",
  "decision_source": "rule"
}
```

```json
{
  "step": 17,
  "from_role": "engineer_1",
  "message": "EPS boost critical for CO2 reduction.",
  "message_type": "recovery_command",
  "decision_source": "llm",
  "deliberation_phase": "action"
}
```

### events.jsonl

```json
{"step": 20, "kind": "/eclss/events/anomaly", "flags": ["scrubber_degradation"]}
{"step": 33, "kind": "/eclss/events/recovery_applied", "command": {"kind": "set_fan_speed", "value": 1.0, "issued_by": "engineer_2"}, "message": "fan_speed set to 1.0"}
```

`/eclss/events/design_change` does not occur at runtime (post-run proposals are in `design_proposals.json`).

### design_state.jsonl

Every step, **before** agent action. Topology is invariant at runtime.

```json
{
  "step": 36,
  "topology": {
    "nodes": [{"id": "cabin", "name": "Cabin", "kind": "volume"}],
    "edges": [{"source": "manifold", "target": "scrubber", "kind": "flow"}]
  },
  "parameters": {"scrubber_base_efficiency": 0.95}
}
```

### eps_telemetry.jsonl

Only with `StationSimulator`.

```json
{
  "step": 22,
  "solar_voltage_v": 113.14,
  "bcdu_mode": "discharging",
  "support_w": 120.0,
  "support_steps_remaining": 3
}
```

May also carry `"post_ops": true` when L5 refreshes EPS after recovery commands in the same step.

### summary.json

```json
{
  "scenario": "scrubber_degradation",
  "simulator": "mock_station",
  "agents_mode": "labeled_rule_base",
  "steps": 50,
  "peak_co2_ppm": 1016.34,
  "final_co2_ppm": 967.2,
  "final_power_margin_w": -42.5,
  "eps_boost_applied_step": 28,
  "final_health": {"co2_status": "safe", "power_status": "warning", "overall": "warning"},
  "design_proposal_count": 1,
  "provenance_record_count": 2,
  "archetypes": {
    "engineer_1": "first_principles",
    "engineer_2": "failure_mode",
    "engineer_3": "improviser",
    "engineer_4": "systems_integrator"
  }
}
```

| Field | Description |
| --- | --- |
| `archetypes` | `agent_id` → thinking lens name from `team.archetypes` in `agents.yaml`. Empty object `{}` when archetypes are omitted or `[]`. Present in scrubber runs; logged even in `labeled_rule_base` (personas ignored there). Not used by `ssos_eclss_loop` unless that scenario adds `team.archetypes` |

### ROS2-style topics (mock contract)

`environment/ssos/topics.py` — for `StationSimulator` / mock adapter. **Separate namespace from ssos live ECLSS.**

| Topic | Direction | Payload |
| --- | --- | --- |
| `/eclss/telemetry/co2_ppm` | pub | float |
| `/eclss/command/set_fan_speed` | sub | float 0–1 |
| `/eclss/command/request_eps_boost` | sub | float W |
| `/eclss/events/recovery_applied` | event | command result |
| `/eclss/events/anomaly` | event | anomaly flags |

### EPS topics (scrubber power)

`environment/ssos/eps_topics.py` — `MockSarj` / `MockBcdu` and `Ros2EpsBridge` (Phase 3).

| Topic | Direction | Payload |
| --- | --- | --- |
| `/solar/voltage` | pub | float V |
| `/bcdu/operation` | sub | `{support_w, duration_steps}` |
| `/bcdu/status` | pub | `BcduStatus` |

### provenance — recovery record

```json
{
  "record_type": "recovery",
  "scenario": "scrubber_degradation",
  "change_kind": "request_eps_boost",
  "actor": "engineer_3",
  "payload": {"support_w": 120.0, "eps": {"bcdu_mode": "discharging"}},
  "trace": {"event_kind": "/eclss/events/recovery_applied", "decision_source": "rule"}
}
```

### Examples

```bash
python src/scripts/run_mock_eclss.py
python -c "from scenario.runner import run_scenario; run_scenario('scrubber_degradation', overrides={'agents': {'mode': 'labeled_rule_base'}})"
python -c "from scenario.runner import run_scenario; run_scenario('scrubber_degradation', overrides={'agents': {'mode': 'llm'}})"
```

---

## ssos_eclss_loop

Operates live ROS2 ECLSS inside SSOS Docker (or `LoopMockEclssBackend`). Does **not** use `SimulatorProtocol`.

### EclssBackend

`build_eclss_backend()` — `src/scenario/ssos_eclss_loop/scenario_run.py`

| Class | Purpose |
| --- | --- |
| `LoopMockEclssBackend` | Host dev / pytest (simple storage dynamics) |
| `Ros2EclssBridge` | SSOS Docker — ros2 CLI bridge |

Backend selection: `scenario.yaml` `backend.kind`, env var `SSOS_ECLSS_BACKEND`, CLI `--backend mock|ros2` (or `ea run … --backend mock`).

| Method | Description |
| --- | --- |
| `poll_telemetry()` | Read `/co2_storage`, etc. |
| `send_air_revitalisation_goal(goal)` | ARS Action |
| `send_oxygen_generation_goal(goal)` | OGS Action |
| `send_water_recovery_goal(goal)` | WRS Action |
| `request_co2(amount)` / `request_o2(amount)` | Service |
| `request_product_water(liters)` | Service |
| `set_subsystem_failure(name, enabled)` | Failure injection |

Implementation: `environment/ssos/eclss/backend.py`, `eclss/ros2/bridge.py`, `eclss/ros2/graph_rewire.py` (client remap).

### EclssTelemetrySnapshot — `telemetry.jsonl`

```json
{
  "step": 3,
  "co2_storage_kg": 1680.0,
  "o2_storage_kg": 465.0,
  "product_water_reserve_l": 100.0,
  "ars_failure_enabled": false
}
```

| Field | ROS2 topic |
| --- | --- |
| `co2_storage_kg` | `/co2_storage` |
| `o2_storage_kg` | `/o2_storage` |
| `product_water_reserve_l` | `/wrs/product_water_reserve` |

When operational commands run in a step, a second row may be appended with `"post_ops": true` (L5). Readers (dashboard) prefer `post_ops` / the last row for that step so UI matches `summary.json`.

### EclssOperationalCommand — runtime

`SsosEclssLoopTeam.apply_outcome()` → `EclssBackend`

```json
{
  "kind": "air_revitalisation",
  "payload": {"initial_co2_mass": 1800.0, "initial_moisture_content": 25.0},
  "issued_by": "eclss_operator_1"
}
```

| `kind` | Backend |
| --- | --- |
| `air_revitalisation` | `send_air_revitalisation_goal()` |
| `oxygen_generation` | `send_oxygen_generation_goal()` |
| `water_recovery_systems` | `send_water_recovery_goal()` |
| `request_co2` | `request_co2(amount)` |
| `request_o2` | `request_o2(amount)` |

### Health — `health_metrics.jsonl`

`compute_eclss_storage_health()` — `src/scenario/ssos_eclss_loop/health.py`  
Thresholds from `scenario.yaml` `thresholds`.

```json
{"step": 3, "co2_status": "warning", "o2_status": "safe", "water_status": "safe", "overall": "warning"}
```

Same optional `"post_ops": true` duplicate-row rule as `telemetry.jsonl` when ops refresh health in-step.

| Metric | safe | warning | critical |
| --- | --- | --- | --- |
| CO₂ storage (kg) | < 1500 (high) | 1500 to < 2200 | ≥ 2200 |
| O₂ storage (kg) | > 450 (low) | 337.5 to 450 | ≤ 337.5 |
| Product water (L) | > 50 (low) | 25 to 50 | ≤ 25 |

`thresholds.co2_storage_high_kg`, etc. are **operational triggers**, separate from health bands.

### design_proposals.json — `design_domain: ssos_graph`

| `change_kind` | Purpose |
| --- | --- |
| `action_profile` | Action goal fields (ARS / OGS / WRS) |
| `service_config` | Service call amounts and order |
| `set_parameter` | Threshold / policy parameters |
| `graph_rewire` | Client `topic_remap` for next run (Phase 7). Launch remap: [BL-003](memo/backlog.md#bl-003) |

`--apply-proposals` merges into `scenario.yaml` / `ssos_graph.rewires`. Implementation: `scenario/ssos_eclss_loop/design_proposals.py`.

```json
{
  "design_domain": "ssos_graph",
  "proposed_by": "eclss_operator_2",
  "decision_source": "rule",
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

### Agent modes

| `agents.mode` | Team | Runtime | Post-run |
| --- | --- | --- | --- |
| `none` | — | `poll_telemetry` only | — |
| `labeled_rule_base` | `SsosEclssLoopTeam` | storage thresholds → ARS/OGS | `ssos_graph` (rule) |
| `llm` | same | deliberation + operational | `ssos_graph` (llm) |

#### messages.jsonl example

```json
{
  "step": 2,
  "from_role": "eclss_operator_1",
  "message": "Starting ARS air_revitalisation to vent CO2 from storage.",
  "message_type": "operational_command",
  "decision_source": "rule"
}
```

### events.jsonl

```json
{
  "step": 2,
  "kind": "/eclss/events/operational_applied",
  "command": {"kind": "air_revitalisation", "issued_by": "eclss_operator_1", "payload": {"initial_co2_mass": 1800.0}},
  "result": {"success": true},
  "message": "ARS goal dispatched"
}
```

On failure: `/eclss/events/operational_rejected`.

### design_state.jsonl

Every step, **before** agent action. Snapshot of `ssos_graph` (includes `rewires`).

```json
{
  "step": 1,
  "ssos_graph": {
    "rewires": [{"public": "/co2_storage", "backend": "/co2_storage"}]
  }
}
```

### summary.json

```json
{
  "scenario": "ssos_eclss_loop",
  "backend": "ros2",
  "agents_mode": "labeled_rule_base",
  "steps": 8,
  "peak_co2_storage_kg": 1680.0,
  "final_co2_storage_kg": 1330.0,
  "final_o2_storage_kg": 465.0,
  "operational_command_count": 3,
  "ogs_invoked_step": 2,
  "final_health": {"co2_status": "safe", "o2_status": "warning", "overall": "warning"},
  "agent_ids": ["eclss_operator_1", "eclss_operator_2", "eclss_operator_3"],
  "provenance_record_count": 3
}
```

**Fields not in scrubber**: `backend`, `peak_co2_storage_kg`, `operational_command_count`, etc.  
**Fields not in ssos**: `co2_ppm`, `eps_boost_applied_step`, entire `eps_telemetry.jsonl`.

### ROS2 topics (SSOS live ECLSS)

`environment/ssos/eclss_topics.py` — used by `Ros2EclssBridge`. **Separate from scrubber `/eclss/telemetry/co2_ppm`.**

| Kind | Name |
| --- | --- |
| Action | `air_revitalisation`, `oxygen_generation`, `water_recovery_systems` |
| Service | `/ars/request_co2`, `/ogs/request_o2`, `/wrs/product_water_request` |
| Topic | `/co2_storage`, `/o2_storage`, `/wrs/product_water_reserve` |

`Ros2EclssBridge(topic_remap=...)` — client topic replacement from `graph_rewire` proposals (Phase 7).

### provenance — operational record

```json
{
  "record_type": "operational",
  "scenario": "ssos_eclss_loop",
  "change_kind": "air_revitalisation",
  "actor": "eclss_operator_1",
  "payload": {"initial_co2_mass": 1800.0},
  "trace": {"event_kind": "/eclss/events/operational_applied", "result_success": true}
}
```

### Examples

```bash
# mock (host)
python -m scenario.ssos_eclss_loop.scenario_run --backend mock --agents-mode labeled_rule_base

# ros2 (SSOS Docker)
./scripts/run_ssos_eclss_loop.sh --agents-mode labeled_rule_base

# graph_rewire E2E
./scripts/run_graph_rewire_e2e.sh
```

---

## Related documentation

- [architecture.md](architecture.md) — layers and execution flow
- [one-piece-integration.md](one-piece-integration.md) — provenance details
- [development-plan.md](development-plan.md) — incomplete items
