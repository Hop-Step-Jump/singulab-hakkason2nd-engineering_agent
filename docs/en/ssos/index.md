# SSOS ECLSS + EPS Integration — Overview

This document describes the integration layer for operating Space Station OS (SSOS) **ECLSS** (life support) and **EPS** (power) from `engineering_agents`. Instead of the Crew Simulation GUI, agents control ARS, OGS, WRS, and BCDU via `EclssBackend` / `EpsBackend`.

For scenario specification (agents, outputs, dashboard), see [ssos_eclss_loop scenario](../scenario-ssos-eclss-loop.md). This section focuses on **Docker / ROS 2 operational integration**.

!!! note "Scope"
    - The primary goal is **virtual verification**. Connecting to the physical world (on-orbit hardware) is out of scope for this demo.
    - The reference scenario `scrubber_degradation` remains **Mock-frozen**. SSOS integration is validated with the new scenario `ssos_eclss_loop`.
    - Persistent topology changes at runtime (legacy `DesignChange`) were **removed in Phase 0**.

---

## Why integrate

| Before (Crew Simulation) | After integration (engineering_agents) |
| --- | --- |
| Human operator controls ARS/OGS via GUI | AI agent reproduces the same operations via `EclssBackend` API |
| Pass/fail can be subjective | Verification via telemetry JSONL + deterministic `health_metrics` |
| Design and operations easily conflated | Runtime uses **operational commands only**; persistent changes are post-run `design_proposals.json` (Phase 5) |

Agents must not become a **self-grading** loop where an LLM declares pass in place of a physics simulator. Pass/fail is decided from raw telemetry on the SSOS Docker ROS 2 graph against scenario YAML thresholds (see [AGENTS.md](../AGENTS.md)).

---

## Tier Model

Integration deepens in stages. Each tier can be smoke-tested independently.

| Tier | Phase | Content | Backend | Verification |
| --- | --- | --- | --- | --- |
| **T0** | 0 | Remove `DesignChange`, freeze `scrubber_degradation` | Mock only | `pytest` |
| **T1a** | 1a | ARS Action smoke | `ros2` CLI → SSOS | `run_ssos_eclss_smoke.sh` |
| **T1b** | 1b | ARS + OGS + Service | `Ros2EclssBridge` | `run_ssos_eclss_1b_smoke.sh` |
| **T2** | 2 | + WRS (potable water vs electrolysis water) | `Ros2EclssBridge` | `run_ssos_eclss_2_smoke.sh` |
| **T3** | 3 | EPS read + `request_eps_boost` interim | `Ros2EpsBridge` | `run_ssos_eps_smoke.sh` |
| **T4** | 4 | `ssos_eclss_loop` scenario + agents | mock \| ros2 switch | `scenario_run.py` |
| **T5** | 5 | `design_proposals.json` + `--apply-proposals` | — | `scenario_run.py` |
| **Regression** | — | Container E2E orchestrator (pytest + smoke chain + ea-loop) | `run_ssos_regression.sh` | `.github/workflows/ssos-e2e.yml` |

---

## Container regression

`scripts/run_ssos_regression.sh` is the single entry point for SSOS integration regression:

| Tier | Scope | Requires Docker |
| --- | --- | --- |
| **Tier 1** | Full `pytest` (default; excludes `tests/e2e`) | No |
| **Tier 2** | Managed container → headless ECLSS → ARS/1b/WRS/graph-rewire smokes → `ea-loop` | Yes (`SSOS_E2E=1`) |

Artifacts land in `artifacts/ssos-regression/<timestamp>/` (JSON smoke reports, `ea-loop` output). See [Quickstart — Container E2E regression](quickstart.md#container-e2e-regression-one-command).

---

## Architecture

```mermaid
flowchart TB
  subgraph agents [scenario/ — agent layer]
    Team[SsosEclssLoopTeam]
    Runner[SsosEclssLoopScenario]
  end

  subgraph backends [environment/ssos/ — backend layer]
    EclssProto[EclssBackend Protocol]
    EpsProto[EpsBackend Protocol]
    MockEclss[LoopMockEclssBackend / MockEclssBackend]
    Ros2Eclss[Ros2EclssBridge]
    MockEps[MockEpsBackend]
    Ros2Eps[Ros2EpsBridge]
  end

  subgraph ssos [SSOS Docker — ROS 2 Jazzy]
    ARS[air_revitalisation]
    OGS[oxygen_generation]
    WRS[water_recovery_systems]
    BCDU[/bcdu/status]
    Solar[/solar_controller/ssu_voltage_v]
  end

  Team --> Runner
  Runner --> EclssProto
  EclssProto --> MockEclss
  EclssProto --> Ros2Eclss
  Ros2Eclss -->|ros2 CLI| ARS
  Ros2Eclss --> OGS
  Ros2Eclss --> WRS

  subgraph scrubber [scrubber_degradation — frozen]
    Station[StationSimulator]
    Station --> EpsProto
    EpsProto --> MockEps
    EpsProto --> Ros2Eps
    Ros2Eps -->|ros2 CLI| BCDU
    Ros2Eps --> Solar
  end
```

### Execution paths

| Scenario | Simulator | ECLSS | EPS |
| --- | --- | --- | --- |
| `scrubber_degradation` | `StationSimulator` | `MockEclssSimulator` | `mock` \| `ssos_eps` |
| `ssos_eclss_loop` | None (`EclssBackend` direct) | `mock` \| `ros2` | Not used (Phase 4) |

---

## Key files

| Path | Role |
| --- | --- |
| `src/environment/ssos/eclss/backend.py` | `EclssBackend` Protocol |
| `src/environment/ssos/eclss/types.py` | Goal / Report datatypes |
| `src/environment/ssos/eclss/mock/backend.py` | Mock for contract tests |
| `src/environment/ssos/eclss/ros2/bridge.py` | SSOS ECLSS bridge (CLI) |
| `src/environment/ssos/eclss/ros2/topics.py` | Action / Service / Topic constants |
| `src/environment/ssos/eclss/ros2/graph_rewire.py` | Client-side graph remap |
| `src/environment/ssos/ros2/cli.py` | Shared `ros2` subprocess helpers |
| `src/environment/scrubber/eps/backend.py` | `EpsBackend` Protocol (scrubber) |
| `src/environment/scrubber/eps/mock/backend.py` | SARJ/BCDU Mock wrapper |
| `src/environment/ssos/eps/ros2/bridge.py` | SSOS EPS bridge (CLI) |
| `src/environment/ssos/eps/ros2/topic_map.py` | SSOS live topics ↔ contract names |
| `src/environment/ssos/eps/ros2/adapters.py` | ROS messages ↔ dataclass |
| `src/scenario/ssos_eclss_loop/` | New scenario (YAML + runner + health) |
| `src/scenario/agents/ssos_eclss_loop_team.py` | Crew-replacement agents |
| `scripts/run_ssos_eclss_*.sh` | Host → Docker smoke wrappers |
| `scripts/run_ssos_eps_smoke.sh` | EPS smoke wrapper |
| `scripts/run_ssos_regression.sh` | Tier 1 pytest + optional Tier 2 container E2E |
| `scripts/lib/ssos_docker.sh` | Shared Docker sync, headless launch, graph wait |
| `.github/workflows/ssos-e2e.yml` | CI: PR pytest + scheduled/manual Tier 2 |

---

## Related links

- [Docker setup](quickstart.md) — `ea run` and smoke tests
- [ECLSS integration](eclss-integration.md) — topics and actions in detail
- [EPS integration](eps-integration.md) — interim power-boost approach
- [ssos_eclss_loop scenario](../scenario-ssos-eclss-loop.md) — scenario spec and reading outputs
- [Troubleshooting](troubleshooting.md)
- [API reference](api-reference.md)
- Development memos: [SSOS ECLSS integration plan](../memo/ssos_eclss_loop/ssos_eclss_loop_connection_plan.md), [SSOS EPS ROS2 integration plan](../memo/ssos_eclss_loop/ssos_eps_ros2_connection_plan.md)
