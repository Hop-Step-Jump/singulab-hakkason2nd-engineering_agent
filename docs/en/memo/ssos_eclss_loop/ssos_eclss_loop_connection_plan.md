
# SSOS ECLSS Loop Integration Plan

> **Scope**: `engineering_agents` agents operate Space Station OS ECLSS (ARS / OGS / WRS) instead of Crew Simulation. `scrubber_degradation` remains a separate scenario with Mock frozen.  
> **Follow-up (Phase 8 onward)**: [backlog.md](../backlog.md) (BL-003–BL-005)

---

## Implementation Status

| Item | Value |
|------|-----|
| Branch | `feat/ssos-eclss-loop` (PR #9 vs `main`) |
| Latest commit | `95ebd1b` — Phase 7 (graph_rewire client / Team ABC / Dashboard) |
| Tests | `pytest` → **140 passed**, 4 skipped |
| User-facing documentation | Branch **`docs/ssos-mkdocs`** |
| E2E records | `memo/ssos_eclss_loop/e2e_records/` (repo only) |

---

## Milestone Overview

| Phase | Content | Status | Completion criteria / notes |
|-------|------|------|-----------------|
| **0** | DesignChange removal | ✅ | All scrubber tests pass; no `SimulatorProtocol.apply_design_change` |
| **1a** | ARS headless smoke | ✅ | In-container `ssos_eclss_ars_smoke`; topic/action reachability |
| **1b** | ARS + OGS + `EclssBackend` | ✅ | O₂/CO₂ Sabatier contention appears in telemetry |
| **2** | WRS bridge | ✅ | `run_ssos_eclss_2_smoke.sh`, water tradeoff signal |
| **3** | EPS integration (scrubber power) | ✅ | [ssos_eps_ros2_connection_plan.md](ssos_eps_ros2_connection_plan.md), `run_ssos_eps_smoke.sh` |
| **4** | `ssos_eclss_loop` + `SsosEclssLoopTeam` | ✅ | mock/ros2 scenarios, telemetry JSONL |
| **5** | `design_proposals.json` + `--apply-proposals` | ✅ | `design_domain: ssos_graph`, merge into next run |
| **6** | LLM agents | ✅ | deliberation → operational → post-run design; mock pytest + container E2E |
| **6.1** | Docker run UX (`ea-loop`) | ✅ | Default `ros2`, `OLLAMA_BASE_URL=host.docker.internal` |
| **7** | graph_rewire (client) + Team ABC + Dashboard | ✅ | `graph_rewire.py`, `ssos_views.py`, re-arm improvements; E2E `run_graph_rewire_e2e.sh` |
| **8** | ROS launch remap (A) + gateway | 📋 backlog | [backlog.md BL-003](../backlog.md#bl-003) |

---

## Agreements (Phase 0)

| Item | Status |
|------|------|
| Runtime `DesignChange` | **Removed** |
| scrubber_degradation | **Frozen** — post-run `design_proposals.json` + dashboard After preview retained |
| New scenario | `ssos_eclss_loop` — **Implemented** |
| Post-run proposals | `design_proposals.json` (`design_domain: ssos_graph`) — **Implemented** |

---

## Architecture

```
SsosEclssLoopTeam(Team) → scenario_run → EclssBackend
                                            ├── LoopMockEclssBackend (dev)
                                            └── Ros2EclssBridge (SSOS Docker, topic_remap)
```

Startup: `~/dev/ssos/ssos-run.sh` → in-container `bash /root/ssos-eclss-headless.sh` → `ea-loop`

---

## Action/Service — C++ Rebuild Required?

**Proposals against existing SSOS interfaces can be applied with rclpy only (no rebuild required).**

| Proposal type | Application method |
|----------|----------|
| `action_profile` | `ActionClient.send_goal()` — goal fields specified each time |
| `service_config` | `ServiceClient.call()` |
| `set_parameter` | Replace launch YAML for next run (C++ reads at startup) |
| New Action/Service/BT | SSOS upstream PR (fork required) |

### Existing Interfaces

- **Actions**: `air_revitalisation`, `water_recovery_systems`, `oxygen_generation`
- **Services**: `/ogs/request_o2`, `wrs/product_water_request`, `/ars/request_co2`, `/grey_water`
- **Topics**: `/co2_storage`, `/o2_storage`, `/wrs/product_water_reserve`, diagnostics, self_diagnosis

### Action/Service Types (fixed in Phase 1a)

In the current SSOS Jazzy image, the type prefix is **`space_station_interfaces`** (not `space_station_eclss`).

| Kind | Type |
|------|-----|
| ARS Action | `space_station_interfaces/action/AirRevitalisation` |
| OGS Action | `space_station_interfaces/action/OxygenGeneration` |
| WRS Action | `space_station_interfaces/action/WaterRecovery` |
| O₂ / CO₂ Service | `space_station_interfaces/srv/O2Request`, `.../Co2Request` |
| Product water / Grey water | `space_station_interfaces/srv/RequestProductWater`, `.../GreyWater` |

Constants are centralized in `src/environment/ssos/eclss_topics.py`.

---

## Phase 1a Deliverables (complete)

| File | Role |
|----------|------|
| `src/environment/ssos/eclss_topics.py` | SSOS ECLSS Action/Service/Topic constants |
| `src/environment/ssos/eclss_types.py` | `ArsGoal`, `EclssSmokeReport`, etc. |
| `src/scripts/ssos_eclss_ars_smoke.py` | In-container smoke |
| `scripts/run_ssos_eclss_smoke.sh` | Host Mac wrapper |

#### Phase 1a Verification Procedure (2 terminals)

**Prerequisites**: SSOS Docker container is running. Example on this machine: container name `ssos`, image `ghcr.io/space-station-os/space_station_os:latest` (verify with `docker ps`). `engineering_agents` is not auto-mounted into the container; the script syncs `src/` to `/tmp/engineering_agents/src` via `docker cp`.

**Terminal 1 — Start ECLSS headless (in container)**

```bash
docker exec -it ssos bash
bash /root/ssos-eclss-headless.sh
# Stop with Ctrl+C. Keep running while smoke runs in another shell.
```

**Terminal 2 — smoke (host Mac repo root)**

```bash
cd /path/to/engineering_agents
chmod +x scripts/run_ssos_eclss_smoke.sh   # first time only
./scripts/run_ssos_eclss_smoke.sh
# Save JSON: ./scripts/run_ssos_eclss_smoke.sh --json-out /tmp/eclss_smoke.json
```

Running `PYTHONPATH=src python3 -m scripts.ssos_eclss_ars_smoke` in the host `.venv` is **expected to fail with `ros2 CLI not found`** (no ROS 2 on Mac host). In the container, setting only `PYTHONPATH=src` overwrites the ROS workspace `PYTHONPATH` and breaks `ros2` — **prepend like `PYTHONPATH=/tmp/engineering_agents/src:$PYTHONPATH`** (the wrapper does this automatically).

**Manual (no wrapper)**

```bash
docker exec ssos mkdir -p /tmp/engineering_agents
docker cp src/. ssos:/tmp/engineering_agents/src/
docker exec -it ssos bash -lc '
  source /opt/ros/jazzy/setup.bash
  source ~/ssos_ws/install/setup.bash
  cd /tmp/engineering_agents
  PYTHONPATH=/tmp/engineering_agents/src:\${PYTHONPATH} python3 -m scripts.ssos_eclss_ars_smoke
'
```

**Pass criteria**: exit code 0; `/co2_storage` and `/ars/diagnostics` topics exist; `air_revitalisation` action exists; goal SUCCEEDED.

**Troubleshooting**: If `send_goal` hangs on "Waiting for an action server...", the action **name** may be visible but the **type** may differ. In the current SSOS image, the type for `ros2 action send_goal` is `space_station_interfaces/action/AirRevitalisation` (not `space_station_eclss/action/...`). Verify: `ros2 node info /air_revitalisation | grep -A1 'Action Servers'`.

```bash
# In container (ECLSS running) — equivalent to wrapper above
source ~/ssos_ws/install/setup.bash
cd /path/to/engineering_agents
PYTHONPATH=src python3 -m scripts.ssos_eclss_ars_smoke
```

### Phase 1b Deliverables (complete — ARS + OGS)

| File | Role |
|----------|------|
| `src/environment/ssos/eclss_backend.py` | `EclssBackend` Protocol |
| `src/environment/ssos/mock_eclss_backend.py` | Local dev / contract tests |
| `src/environment/ssos/ros2_eclss_bridge.py` | `ros2` CLI bridge (Docker minimum) — Jazzy `ros2 service call` output parsing |
| `src/scripts/ssos_eclss_1b_smoke.py` | ARS+OGS bridge smoke (telemetry + OGS goal + Sabatier signal) |
| `scripts/run_ssos_eclss_1b_smoke.sh` | Run 1b from host Mac via `docker exec` |

**Phase 1b completion criteria**: O₂/CO₂ Sabatier contention appears in `poll_telemetry()` (SSOS container + ECLSS running).

```python
from environment.ssos.mock_eclss_backend import MockEclssBackend
from environment.ssos.ros2_eclss_bridge import Ros2EclssBridge

backend = MockEclssBackend()  # tests / local
# backend = Ros2EclssBridge()  # SSOS Docker

snap = backend.poll_telemetry()
backend.send_air_revitalisation_goal(ArsGoal())
backend.send_oxygen_generation_goal(OgsGoal())
backend.request_o2(500.0)
backend.request_co2(100.0)
backend.set_subsystem_failure("ars", enabled=True)
```

#### Phase 1b Verification Procedure (2 terminals)

**Prerequisites**: Same as Phase 1a (container `ssos`, ECLSS headless running). Wrapper syncs `src/` to `/tmp/engineering_agents/src`.

**Terminal 1 — Start ECLSS headless (in container)**

```bash
docker exec -it ssos bash
bash /root/ssos-eclss-headless.sh
# Keep running while 1b smoke executes.
```

**Terminal 2 — 1b smoke (host Mac repo root)**

```bash
cd /path/to/engineering_agents
chmod +x scripts/run_ssos_eclss_1b_smoke.sh   # first time only
./scripts/run_ssos_eclss_1b_smoke.sh
# Save JSON: ./scripts/run_ssos_eclss_1b_smoke.sh --json-out /tmp/eclss_1b_smoke.json
```

**Manual (no wrapper)**

```bash
docker exec ssos mkdir -p /tmp/engineering_agents
docker cp src/. ssos:/tmp/engineering_agents/src/
docker exec -it ssos bash -lc '
  source /opt/ros/jazzy/setup.bash
  source ~/ssos_ws/install/setup.bash
  cd /tmp/engineering_agents
  PYTHONPATH=/tmp/engineering_agents/src:\${PYTHONPATH} python3 -m scripts.ssos_eclss_1b_smoke
'
```

**Pass criteria**: exit code 0; `poll_telemetry()` obtains `/co2_storage` and `/o2_storage`; `oxygen_generation` goal SUCCEEDED; O₂/CO₂ Sabatier contention signal (`sabatier_signal: true`). `request_co2` **succeeds** or **expected rejection due to insufficient CO₂** (`request_co2_expected_insufficient: true` — headless real plant typically has `/co2_storage=0 kg`).

**Troubleshooting — `Insufficient CO₂ in storage`**: Normal response when **SSOS plant real storage** is 0 kg, not this repo's mock initial values. Without Crew Simulation, headless mode does not accumulate CO₂. Smoke verifies service reachability + OGS success (PASS with `request_co2_expected_insufficient` when insufficient). To see `request_co2` succeed with CO₂ available, re-run after Crew is running.

**Troubleshooting — parsing**: Jazzy `ros2 service call` output may be Python repr instead of YAML. `Ros2EclssBridge` parses both formats. Manual: `ros2 service call /ars/request_co2 space_station_interfaces/srv/Co2Request "{amount: 25.0}"`.

WRS Action/Service added to `Ros2EclssBridge` in Phase 2 (`2700fda`).

### Phase 2 Deliverables (complete — `2700fda`)

| File | Role |
|----------|------|
| `src/environment/ssos/ros2_eclss_bridge.py` | WRS action, `request_product_water` / grey water service |
| `src/environment/ssos/mock_eclss_backend.py` | WRS mock + water tradeoff dynamics |
| `src/environment/ssos/eclss_types.py` | `WrsGoal`, etc. |
| `src/scripts/ssos_eclss_2_smoke.py` | Phase 2 smoke (`water_tradeoff_signal`) |
| `scripts/run_ssos_eclss_2_smoke.sh` | Host Mac wrapper |

**Completion criteria**: Potable water vs electrolysis water tradeoff appears in smoke JSON / telemetry.

```bash
./scripts/run_ssos_eclss_2_smoke.sh
```

### Phase 3 Deliverables (complete — `3b4b0b4`)

Details: [ssos_eps_ros2_connection_plan.md](ssos_eps_ros2_connection_plan.md)

| File | Role |
|----------|------|
| `src/environment/ssos/eps_backend.py` | `EpsBackend` Protocol |
| `src/environment/ssos/mock_eps_backend.py` | Mock SARJ + BCDU |
| `src/environment/ssos/ros2_eps_bridge.py` | SSOS EPS topic CLI bridge |
| `src/environment/ssos/topic_map.py` | Real plant topic name map |
| `src/environment/ssos/message_adapters.py` | BCDU / SARJ message parsing |
| `src/environment/ssos/station_simulator.py` | Power integration via `EpsBackend` |
| `src/environment/ssos/adapter.py` | `build_ssos_eps_station()` helper |
| `src/scenario/runner.py` | `build_eps_backend()` — `mock` \| `ssos_eps` |
| `src/scripts/ssos_eps_smoke.py` | EPS smoke |
| `scripts/run_ssos_eps_smoke.sh` | Wrapper |

```bash
./scripts/run_ssos_eps_smoke.sh
```

### Phase 4 Deliverables (complete — `7196812`)

| File | Role |
|----------|------|
| `src/scenario/ssos_eclss_loop/scenario.yaml` | Design / verification requirement stubs |
| `src/scenario/ssos_eclss_loop/agents.yaml` | Agent configuration |
| `src/scenario/ssos_eclss_loop/scenario_run.py` | Scenario runner |
| `src/scenario/ssos_eclss_loop/loop_mock_backend.py` | Loop mock dynamics |
| `src/scenario/ssos_eclss_loop/health.py` | Deterministic health checks |
| `src/scenario/agents/ssos_eclss_loop_team.py` | Crew Simulation replacement team |
| `src/scenario/agents/eclss_loop_types.py` | Proposal / command types |
| `src/scenario/runner.py` | `_scenario_registry()` + `SsosEclssLoopTeam` |

#### Phase 4 / 5 / 6 Execution (recommended procedure)

**Prerequisites (container ros2)**: Terminal 1 runs `bash /root/ssos-eclss-headless.sh`. Terminal 2 runs loop.

**One command from host** (sync + in-container execution; backend auto ros2):

```bash
./scripts/run_ssos_eclss_loop.sh --agents-mode labeled_rule_base
./scripts/run_ssos_eclss_loop.sh --agents-mode llm   # Ollama on Mac required
```

**Enter container, one command** (sync from host first time only):

```bash
# Host (once — re-run on each code update)
./scripts/run_ssos_eclss_loop.sh --sync-only

# In container (ea-loop = /usr/local/bin/ea-loop → run.sh)
docker exec -it ssos bash
ea-loop --agents-mode labeled_rule_base    # backend default ros2
ea-loop --agents-mode llm                  # ros2 + host.docker.internal:11434
ea-loop --backend mock --agents-mode llm   # mock override (development)
```

**mock (no Docker / ROS — host Mac)**:

```bash
./scripts/run_ssos_eclss_loop.sh --mock --agents-mode labeled_rule_base
./scripts/run_ssos_eclss_loop.sh --mock --agents-mode llm
# or
PYTHONPATH=src python3 -m scenario.ssos_eclss_loop.scenario_run --backend mock --agents-mode llm
```

**Second run — apply previous run's design_proposals**:

```bash
ea-loop --agents-mode labeled_rule_base \
  --apply-proposals /tmp/engineering_agents/src/experiments/results/ssos_eclss_loop_labeled_rule_base/design_proposals.json
```

**Environment variables (auto-set by in-container `ea-loop`)**:

| Variable | Default (container) | Purpose |
|------|------------------------|------|
| `SSOS_ECLSS_BACKEND` | `ros2` | mock override: `--backend mock` |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | Mac host Ollama (llm mode) |

If ECLSS is not running, `ea-loop` fails immediately (empty ros2 graph detected).

---

## Phase 5 Deliverables (complete — `d5bf9af`)

| File | Role |
|----------|------|
| `src/scenario/ssos_eclss_loop/design_proposals.py` | Load, validate, apply plugin (`design_domain: ssos_graph`) |
| `scenario_run.py` | Output `design_proposals.json` at run end, `--apply-proposals` |
| `scripts/run_ssos_eclss_loop.sh` | Host wrapper (sync + exec / `--mock`) |
| `scripts/ssos_container_run.sh` | In-container `ea-loop` entry |

`change_kind`: `action_profile` | `service_config` | `set_parameter` | `graph_rewire`

---

## Phase 6 Deliverables (complete — `d62ca77`)

| File | Role |
|----------|------|
| `src/scenario/agents/ssos_eclss_loop_team.py` | `_run_step_llm` (deliberation + action), `propose_post_run_design` |
| `src/core/agents/persona.py` | `eclss_operational_action_contract` / `eclss_design_proposal_contract` |
| `src/core/llm/ollama.py` | `resolve_ollama_base_url()` — `OLLAMA_BASE_URL` env var |
| `src/core/agents/memory.py` | Payload recording for `EclssOperationalCommand` |
| `tests/scenario/test_ssos_eclss_loop.py` | `test_ssos_eclss_loop_llm_agents_invoke_ars` (Fake LLM) |
| `tests/scenario/test_ssos_eclss_loop_team.py` | LLM parse unit tests |

**LLM flow** (aligned with scrubber pattern):

1. All members deliberation (`message_contract`)
2. Action rep operational command (`eclss_operational_action_contract`)
3. Post-run design after run ends (`eclss_design_proposal_contract` → `design_proposals.json`, `decision_source: llm`)

**pytest (mock)**:

```bash
PYTHONPATH=src pytest tests/scenario/test_ssos_eclss_loop.py::test_ssos_eclss_loop_llm_agents_invoke_ars -q
```

**Container E2E (ros2) — recorded**: See `memo/ssos_eclss_loop/e2e_records/` (repo only)

| run | Result |
|-----|------|
| `labeled_rule_base` | `operational_command_count=2`, OGS SUCCEEDED |
| `llm` (3 steps) | Ollama connection OK, `decision_source=llm`, operational hold (CO₂=0) |

---

## Phase 7 Deliverables (complete — `95ebd1b`)

### 7a — `graph_rewire` (client-side remap)

| Item | Content |
|------|------|
| Layer | **C — `Ros2EclssBridge` client remap** (not ROS launch remap) |
| Module | `environment/ssos/eclss/ros2/graph_rewire.py` |
| Consumer | `build_eclss_backend()` → `Ros2EclssBridge(topic_remap=…)` |
| Tests | `tests/environment/test_graph_rewire.py`, `scripts/run_graph_rewire_e2e.sh` |

Launch remap (A) is [backlog.md BL-003](../backlog.md#bl-003).

### 7b — `Team` ABC unification

| Item | Content |
|------|------|
| `Team` | `run_step(context, observation)` / `apply_outcome(context, outcome)` |
| `SsosEclssLoopTeam` | Extends `Team`, `context` = `EclssBackend` |

### 7c — Dashboard (`ssos_eclss_loop`)

| Item | Content |
|------|------|
| Module | `tools/dashboard/ssos_views.py` |
| Branch | `summary.scenario == "ssos_eclss_loop"` |

```bash
PYTHONPATH=src python3 -m scenario.ssos_eclss_loop.scenario_run \
  --backend mock --agents-mode labeled_rule_base \
  --output-dir src/experiments/results/ssos_eclss_loop_dashboard_demo
PYTHONPATH=src python3 -m streamlit run src/tools/dashboard/app.py
```

### 7d — Edge cases (re-arm implemented; others in backlog)

| Item | Status |
|------|------|
| re-arm boundary / invalid ARS·OGS retry | **Implemented** |
| `co2_critical` unused, provenance heuristics, command failure ignored, `set_parameter` optional path | [backlog.md BL-004](../backlog.md#bl-004) |

---

## Retrospective (2026-06-14)

### What we achieved

1. **Gradual integration Mock → SSOS real plant** — ARS/OGS/WRS smoke → `Ros2EclssBridge` → scenario loop end-to-end.
2. **Design separation from scrubber** — Retired runtime topology changes; unified on post-run `design_proposals.json` (scrubber uses mock topology; SSOS uses `ssos_graph` domain).
3. **Crew Simulation replacement** — `SsosEclssLoopTeam` operates ARS/OGS/CO₂ services with both labeled_rule_base and LLM.
4. **Docker development UX** — `ea-loop` one command, sync scripts, container defaults for ros2/Ollama.

### Lessons learned / pitfalls

| Problem | Cause | Mitigation |
|------|------|------|
| In-container `ModuleNotFoundError: scenario` | `src/` not synced | `run_ssos_eclss_loop.sh --sync-only` |
| `ea-loop` stays mock | `--backend` not specified + scenario.yaml default mock | Built `SSOS_ECLSS_BACKEND=ros2` into `ea-loop` |
| All LLM failures, command 0 | In-container `localhost:11434` does not reach host Ollama | `OLLAMA_BASE_URL=http://host.docker.internal:11434` |
| ros2 smoke fails on Mac host | No ROS 2 on host | **Expected** — run in container |
| SSOS topic names ≠ initial contract | Real plant uses `/solar_controller/ssu_voltage_v`, etc. | Constants in `topic_map.py` / `eclss_topics.py` |

### Unverified / risks

- **ARS path on real plant** — SSOS initial CO₂=0 so labeled/LLM both skip ARS (verified via OGS path)
- **Ollama model** — `gemma4:e4b` in `agents.yaml` fails LLM if missing on host.
- **Action wait** — ros2 bridge is CLI-based with 120s action timeout. Many steps can be slow.
- **One Piece provenance** — ssos_eclss_loop reports record 0 (integration is separate).

---

## Review fixes (2026-06-20)

| Item | Fix |
|------|------|
| labeled policy ← derived from thresholds | `merge_labeled_policy_from_thresholds()` |
| Codex: LLM health keys | Fixed to `co2_status` / `o2_status` |
| Codex: labeled recovery re-fire | re-arm in safe band |
| Codex: One Piece operational provenance | `/eclss/events/operational_applied` export |
| Codex: EPS smoke missing topics | `poll_topics()` returns `None` |
| Codex: smoke script fall-through | `exit` after local ros2 run |
| Codex: action_profile unknown fields | Validation via `ACTION_PROFILE_FIELDS_BY_SUBSYSTEM` |

---

## Recommended demo scenario (hackathon showcase)

```bash
# 1. Rule-based SSOS real plant operation + design proposals
ea-loop --agents-mode labeled_rule_base

# 2. Apply proposals to next run
ea-loop --agents-mode labeled_rule_base --apply-proposals .../design_proposals.json

# 3. LLM judges the same plant (Ollama running)
ea-loop --agents-mode llm
```

---

## Follow-up

Outstanding items are consolidated in **[backlog.md](../backlog.md)**:

| ID | Content |
|----|------|
| BL-003 | Phase 8 — ROS launch remap + gateway |
| BL-004 | SSOS ECLSS loop (WRS team, ECLSS+EPS integration, rclpy, etc.) |
| BL-005 | SSOS EPS (3b/3c, PR-5 documentation, BCDU action) |

### Review feedback summary (reference)

| # | Item | Approach |
|---|------|------|
| 6 | `LoopMockEclssBackend` placement | Keep as-is (under `scenario/`) |
| 7 | diagnosis / self_diagnosis | Out of scope (labeled diagnosis removed) |
| 8 | `request_o2` mock | `/o2_storage` decrease is correct (scale fixed) |

---

## Related

- [ssos_eps_ros2_connection_plan.md](ssos_eps_ros2_connection_plan.md) — EPS Phase 3 details
- [backlog.md](../backlog.md) — Phase 8 onward · EPS follow-up
- [ssos_ros2_graph_design_investigation.md](ssos_ros2_graph_design_investigation.md)
- SSOS MkDocs — `docs/ssos-mkdocs`
- [docs/api-contracts.md](../../api-contracts.md)
