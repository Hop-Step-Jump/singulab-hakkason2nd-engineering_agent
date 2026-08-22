# Engineering Agents — ECLSS Resilience Loop

**→ [Quick start](index.md)** — install, run your first simulation, find result files

Research repository that simulates how an **agent team detects and responds to anomalies in ECLSS** (Environmental Control and Life Support System) and **proposes design changes afterward**. ECLSS is not a physical experiment apparatus; it refers to **life-support equipment** required for crew survival.

This repository has **two scenario tracks**:

- **`scrubber_degradation`** — CO₂ scrubber anomaly on a Python mock (`StationSimulator`). Reproduces the life-support plant (ECLSS) and power system (**EPS**) with a ROS2-style topic contract.
- **`ssos_eclss_loop`** — Connects to live ROS2 ECLSS inside **Space Station OS (SSOS)** Docker (`Ros2EclssBridge`). Verifies ARS/OGS/WRS operations and post-run `ssos_graph` design proposals (Phase 0–7 complete).

Both target research toward future space-station operations software (SSOS). The goal is to validate the loop: **in-flight anomaly → team judgment → permanent design proposal**.

---

## Two scenarios

| | [scrubber_degradation](scenario-scrubber-degradation.md) | [ssos_eclss_loop](scenario-ssos-eclss-loop.md) |
| --- | --- | --- |
| Purpose | Mock CO₂ scrubber anomaly with EPS coupling | SSOS live ECLSS operations (Crew Simulation replacement) |
| Backend | `StationSimulator` | `EclssBackend` (mock / plant_sim / `Ros2EclssBridge`) |
| Telemetry | CO₂ ppm, power margin | CO₂/O₂/water storage (kg / L) |
| Runtime | Recovery commands (fan, EPS boost) | Operational commands (ARS, OGS, request_co2) |
| Post-run | Scrubber topology | `ssos_graph` (`action_profile`, `graph_rewire`) |

---

## Dashboard at a glance { #dashboard-at-a-glance }

Simulation results are recorded in JSONL and reviewed in the [Streamlit dashboard](#dashboard). `scrubber_degradation` shows CO₂ ppm, EPS, and topology Before/After; `ssos_eclss_loop` shows storage kg, operational timeline, and `ssos_graph` design proposals.

### 1. Overview — side-by-side comparison of two runs (scrubber)

For the same `scrubber_degradation` anomaly, compare step-by-step how **different LLM agents** (e.g. `qwen2.5` vs `gemma4:e4b`) produce different trajectories.

<p align="center">
  <img src="../images/dashboard-overview-compare.png" alt="ECLSS Resilience Dashboard — Overview comparing two LLM runs side by side at step 49" width="900"/>
</p>

### 2. Design proposals — topology Before / After (scrubber)

After a run ends, the lead engineer agent proposes **permanent design changes** (bypass valve, emergency power source, etc.).

<p align="center">
  <img src="../images/dashboard-topology-proposals.png" alt="Design proposals — two topology change options: bypass valve and emergency power source" width="900"/>
</p>

### 3. Step replay — step-by-step detailed playback (scrubber)

Follow one run step by step with synchronized timeline, agent messages, reasoning, and telemetry plots.

<p align="center">
  <img src="../images/dashboard-step-replay.png" alt="Step replay — scrubber_degradation_llm at step 17, EPS boost applied and agent reasoning" width="900"/>
</p>

### ssos_eclss_loop — storage and operational timeline

When you select an `ssos_eclss_loop` run, the dashboard shows **CO₂ / O₂ / product water storage kg** plots, health cards (safe / warning / critical), and an **operational timeline** (`air_revitalisation`, `oxygen_generation`, `request_co2`, etc. as `operational_applied`). Compare labeled vs LLM or different models across two runs. Post-run `ssos_graph` proposals (`action_profile`, `graph_rewire`) are available from Step replay.

Details: [scenario-ssos-eclss-loop.md](scenario-ssos-eclss-loop.md#dashboard-views).

---

## Why this simulation

### scrubber_degradation (mock experiment)

On a space station, cascading degradation of CO₂ removal (scrubber) and power margin directly affects crew safety. In reality:

1. Anomalies are detected from telemetry  
2. The operations team shares situational awareness and applies temporary recovery actions  
3. Permanent hardware / plumbing / power design changes are considered as lasting countermeasures  

In [`scrubber_degradation`](scenario-scrubber-degradation.md), scrubber efficiency drops from step 20 onward. Agents issue recovery commands during the run and leave topology proposals in `design_proposals.json` **after the run ends**.

### ssos_eclss_loop (SSOS live ECLSS)

SSOS ECLSS controls **CO₂ removal (ARS)**, **O₂ generation (OGS)**, and **water recovery (WRS)** via ROS2 Actions and Services. This scenario verifies that an agent team can call the same interfaces Crew Simulation used.

In [`ssos_eclss_loop`](scenario-ssos-eclss-loop.md):

1. Monitor `/co2_storage`, `/o2_storage`, etc. each step  
2. Issue ARS / OGS (and Sabatier `request_co2`) as operational commands when thresholds are exceeded  
3. Leave permanent proposals (`action_profile`, `graph_rewire`, etc.) in `design_proposals.json` (`ssos_graph`) after the run  

**ros2** mode connects to the live plant inside SSOS Docker. **mock** mode runs on the host for pytest and development (simple storage dynamics).

---

## Why LLM (vs rule-based)

Both scenarios use `none` / `labeled_rule_base` / `llm`. Scrubber keeps a flat `agents.mode`. ssos splits **actor** (`agents.actor.mode`) and **design** (`agents.design.mode`; omitted inherits actor). Shared pattern: homogeneous N + representative action (scrubber: `engineer_*`, ssos actors: `eclss_actor_*`, ssos designers: `eclss_designer_*`).

| | `labeled_rule_base` | `llm` |
| --- | --- | --- |
| Source of decisions | `policy` / thresholds (scrubber: CO₂ ppm; ssos: storage kg) | Persona + telemetry + team messages (**does not read policy**) |
| Discussion | Fixed rule-driven messages | N homogeneous engineers deliberate one round |
| Actions | Representative issues commands per thresholds | Representative executes LLM `commands` |
| scrubber runtime | Recovery commands (fan, EPS boost) | Same |
| ssos runtime | Operational commands (ARS, OGS, request_co2) | Same |
| Reproducibility | High (regression tests) | Model-dependent (comparison experiments) |

Rule-based mode is **scaffolding for correct behavior**. LLM mode observes **situational understanding, team consensus, and timing differences** that fixed thresholds cannot express. Important LLM design points (details: [homogeneous agent team plan](memo/agents/homogeneous_agent_team_plan.md)):

- **Separate Persona from scenario** — thresholds and numbers appear only in prompt `### Telemetry` / `### World state`
- **Homogeneous N agents + representative action** — avoid rigid roles; rotate speakers and executors each step
- **No topology changes at runtime** — separate simulation from design proposals; align with One Piece provenance
- **Isolate policy from LLM** — do not mix rule answers into prompts; enable comparison experiments

---

## Simulation world (terminology)

### scrubber_degradation

| Abbrev. | English name | Description |
| --- | --- | --- |
| **ECLSS** | Environmental Control and Life Support System | Life-support plant: CO₂ scrubber, air distribution, habitable volume |
| **EPS** | Electrical Power System | Generation, storage, distribution. Supports ECLSS via SARJ/BCDU mocks |
| **Telemetry** | — | CO₂ ppm, scrubber efficiency, power margin, EPS support watts |
| **Recovery command** | — | Temporary operation (fan boost, load shed, EPS boost, bypass) |
| **Design proposal** | — | Permanent change after run (node/edge addition) |

**Health thresholds**: CO₂ safe < 800 / warning < 1200 / critical ≥ 1200 ppm; power margin safe > 0 / warning > −150 / critical ≤ −150 W.

#### Default topology

```
  [cabin] --flow--> [manifold] --flow--> [scrubber] --flow--> [cabin]
                                              ^
                                              | power
                                         [power_bus]
```

Spec: [scenario-scrubber-degradation.md](scenario-scrubber-degradation.md).

### ssos_eclss_loop

| Abbrev. | English name | Description |
| --- | --- | --- |
| **ARS** | Air Revitalisation System | CO₂ storage removal (`air_revitalisation` Action) |
| **OGS** | Oxygen Generation System | O₂ generation (`oxygen_generation`). Sabatier needs CO₂ feedstock |
| **WRS** | Water Recovery System | Water recovery (`water_recovery_systems`) — ros2 bridge implemented |
| **Telemetry** | — | `/co2_storage`, `/o2_storage`, `/wrs/product_water_reserve` (kg / L) |
| **Operational command** | — | ARS / OGS Actions, `request_co2` / `request_o2` Services |
| **Design proposal** | — | `ssos_graph` (`action_profile`, `graph_rewire`, etc.) |

**Health thresholds (storage)**: CO₂ warning ≥ 2.0 kg / critical ≥ 8.0 kg; O₂ warning ≤ 6.0 kg / critical ≤ 1.0 kg. Details: [scenario-ssos-eclss-loop.md](scenario-ssos-eclss-loop.md).

#### SSOS ECLSS subsystems (conceptual)

```
  Metabolic CO₂ ──► /co2_storage ──► ARS (air_revitalisation)
                                    │
  /o2_storage ◄── OGS (oxygen_generation) ◄── request_co2 (Sabatier)
```

Spec: [scenario-ssos-eclss-loop.md](scenario-ssos-eclss-loop.md).

### Agent team (shared pattern)

| Scenario | ID prefix | Default count | Representative action |
| --- | --- | --- | --- |
| scrubber | `engineer` | 4 | `engineer_{(step-1) % N}` |
| ssos actors | `eclss_actor` | 50 | `eclss_actor_{step % N}` (0-based steps) |
| ssos designers | `eclss_designer` | 4 | one representative after the run (`changes`, no count cap) |

Each step: all actors discuss (llm) or rules emit diagnostics (labeled). **Post-run design** on ssos is a separate designer team writing `design_proposals.json`. Design: [post-run design agent](memo/ssos_eclss_loop/post_run_design_agent.md).

---

## This repository vs SSOS / One Piece

```text
[ scrubber_degradation — Mock complete ]
  StationSimulator (MockEclss + EPS mock)
       ↑ SimulatorProtocol
  ScrubberDegradationTeam
       ↓ JSONL + design_proposals.json (scrubber)
  Streamlit dashboard / pytest

[ ssos_eclss_loop — Phase 0–7 complete ]
  Ros2EclssBridge (ros2 inside SSOS Docker)
       ↑ EclssBackend
  SsosEclssLoopTeam (Team ABC)
       ↓ JSONL + design_proposals.json (ssos_graph)
  ea-loop / graph_rewire (client remap) / ssos dashboard views

[ Next / backlog ]
  Phase 8 launch remap     … [backlog BL-003](memo/backlog.md#bl-003)
  design → provenance      … [development-plan.md](development-plan.md)
  One Piece Web UI         … out of scope
```

| Area | Status | Reference |
| --- | --- | --- |
| scrubber mock simulation | **Available** | [architecture.md](architecture.md) |
| ssos_eclss_loop (live ECLSS) | **Available** (Phase 0–7) | [connection plan](memo/ssos_eclss_loop/ssos_eclss_loop_connection_plan.md) |
| One Piece provenance | **Partial** (recovery + operational) | [one-piece-integration.md](one-piece-integration.md) |
| ROS launch remap (Phase 8) | Backlog | [development-plan.md](development-plan.md) |
| One Piece Web / SSOT UI | Not connected | [one-piece-integration.md](one-piece-integration.md) |

Roadmap and research memos: [docs/development-plan.md](development-plan.md).

---

## Documentation { #documentation }

| Document | Audience | Content |
| --- | --- | --- |
| [docs/architecture.md](architecture.md) | Contributors | Layer structure, dual-track execution flow, agent modes, dashboard |
| [docs/scenario-scrubber-degradation.md](scenario-scrubber-degradation.md) | Demo / analysis | Scrubber background, configuration, how to read outputs |
| [docs/scenario-ssos-eclss-loop.md](scenario-ssos-eclss-loop.md) | SSOS integration / demo | ssos background, ARS/OGS operations, Docker runs, outputs |
| [docs/api-contracts.md](api-contracts.md) | Integrators | `SimulatorProtocol` / `EclssBackend`, JSONL, `design_proposals.json` |
| [docs/one-piece-integration.md](one-piece-integration.md) | Design tracking | provenance (recovery / operational), One Piece integration |
| [docs/development-plan.md](development-plan.md) | Developers | Completed milestones, next tasks, roadmap, `docs/en/memo/` index |
| [memo/ssos_eclss_loop/](memo/ssos_eclss_loop/) | SSOS integration | ECLSS Phase 0–7 details, EPS bridge, graph investigation |

---

## Requirements

- **Python 3.11+**
- **Git**
- **Ollama** or lab **vLLM** (only when using `agents.mode: llm`)
- **SSOS Docker** (only for `ssos_eclss_loop` **ros2** mode) — [scenario-ssos-eclss-loop.md](scenario-ssos-eclss-loop.md#how-to-run)

---

## Installation (from scratch)

Python mock scenarios run on the local host. SSOS `ros2` / live smoke connects
to SSOS running in a Linux container, so both macOS and Windows use Docker for
that path.

### 1. Clone the repository

```bash
git clone https://github.com/hirototamura/engineering_agents.git
cd engineering_agents
```

### 2A. macOS / Linux

The validated macOS SSOS live path still runs SSOS itself inside a Docker Linux
container. This step prepares the local Python environment.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"
```

This makes packages under `src/` (`scenario`, `environment`, `core`, etc.) importable.

### 2B. Windows PowerShell + Docker Desktop { #2b-windows-powershell--docker-desktop }

#### 2B-1. Create the Python environment

Run these commands in PowerShell.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[dev]"
python -m pytest -q
```

#### 2B-2. Install Docker Desktop

Install Docker Desktop with the WSL 2 backend. Do not enable Windows
Containers; this project uses Linux containers.

```powershell
wsl --status

curl.exe -L -o C:\tmp\DockerDesktopInstaller.exe `
  "https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe"
Start-Process C:\tmp\DockerDesktopInstaller.exe
```

Recommended installer selections for this project:

| Option | Selection | Why |
| --- | --- | --- |
| All-users installation | Enabled | Good default when administrator approval is available. |
| Use WSL 2 instead of Hyper-V | Enabled | Recommended backend for Linux containers used by SSOS / ROS2. |
| Allow Windows Containers | Disabled | Not needed; this project runs Linux containers. |
| Add shortcut to desktop | Optional | Convenience only. |

After installation, start Docker Desktop and verify it.

```powershell
docker info --format "OSType={{.OSType}} OperatingSystem={{.OperatingSystem}}"
# OSType=linux OperatingSystem=Docker Desktop
docker run --rm hello-world
```

#### 2B-3. Run the SSOS live smoke

Run `scripts/*.sh` via Git Bash. Set `SSOS_CONTAINER` to the running SSOS
container name.

```powershell
$env:SSOS_CONTAINER = "ssos-regression-1807"
& "C:\Program Files\Git\bin\bash.exe" -lc "scripts/run_ssos_regression.sh --skip-pytest --use-existing --steps 3 --artifact-dir artifacts/ssos-regression/windows-wrapper-fixed-cli --keep-container"
```

Expected result: ARS, Phase 1b, Phase 2, graph_rewire smokes pass, followed by
a short `ssos_eclss_loop` run with `backend: ros2`.

Notes:

- If `python` opens the Microsoft Store, disable the Windows Python App
  Execution Alias or call the installed Python by full path.
- If PowerShell blocks `Activate.ps1`, run
  `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, or call
  `.\.venv\Scripts\python.exe` directly.
- If `wsl --status` says WSL is not installed, run `wsl --install` from an
  administrator PowerShell, reboot, then start Docker Desktop.
- Git Bash path conversion, CRLF `bash\r`, and shutdown aborts from the `rclpy`
  reader are handled by the wrappers / `.gitattributes` in this PR.

### 3. Smoke test

```bash
pytest
# scrubber regression
pytest tests/scenario/test_scrubber_baseline.py tests/scenario/test_scrubber_with_agents.py -q
# ssos / graph_rewire
pytest tests/scenario/test_ssos_eclss_loop*.py tests/environment/test_graph_rewire*.py -q
# or
python src/scripts/run_tests.py
```

### 4. LLM backends (for LLM mode)

`agents.mode: llm` needs one of the following. Default is **Ollama**. Switch with `--llm-provider vllm` or `LLM_PROVIDER=vllm`.

#### Ollama (local)

Install Ollama from [https://ollama.com](https://ollama.com) and start the daemon.

```bash
# Example: pull the model specified in agents.yaml
ollama pull gemma4:e4b

# To try another model, change llm.model in agents.yaml
# or override with --llm-model
ollama list
```

Container `ea-loop` defaults to `OLLAMA_BASE_URL=host.docker.internal`.

#### Lab vLLM (GPU server)

The lab box `gpu-sv-008` (`10.10.0.108`) serves OpenAI-compatible APIs. Reachable on the lab LAN or via VPN — not a public address. Do not start another `vllm serve` on that machine. Setup: [hirototamura/vllm_server](https://github.com/hirototamura/vllm_server).

| Use | URL | `model` |
| --- | --- | --- |
| Daily deliberation (default) | `http://10.10.0.108:8000/v1` | `qwen3-8b` |
| Heavier judgment | `http://10.10.0.108:8001/v1` | `qwen3-32b` |

```bash
ea run scrubber_degradation --agents-mode llm --llm-provider vllm
ea run scrubber_degradation --agents-mode llm --llm-provider vllm --llm-model qwen3-32b \
  --set agents.llm.base_url=http://10.10.0.108:8001/v1
```

Env overrides: `VLLM_BASE_URL`, `VLLM_MODEL`, `VLLM_API_KEY`, `VLLM_API_TIMEOUT`, `LLM_PROVIDER`. SSH tunnel example: `VLLM_BASE_URL=http://127.0.0.1:8000/v1`. `agents.llm.api_timeout` applies to Ollama; vLLM keeps a 300s default unless `VLLM_API_TIMEOUT` is set.

Default LLM settings are in each scenario's `agents.yaml` (scrubber: [``scrubber_degradation/agents.yaml``](https://github.com/hirototamura/engineering_agents/blob/main/src/scenario/scrubber_degradation/agents.yaml), ssos: [``ssos_eclss_loop/agents.yaml``](https://github.com/hirototamura/engineering_agents/blob/main/src/scenario/ssos_eclss_loop/agents.yaml)). `llm` mode fails if the selected backend is not reachable.

---

## How to run { #how-to-run }

### scrubber_degradation

#### No agents (baseline)

```bash
python src/scripts/run_mock_eclss.py
```

Or:

```bash
python -c "from scenario.runner import run_scenario; print(run_scenario('scrubber_degradation', overrides={'agents': {'mode': 'none'}}))"
```

#### Rule-based team (scrubber · `labeled_rule_base`)

```bash
python -c "from scenario.runner import run_scenario; print(run_scenario('scrubber_degradation', overrides={'agents': {'mode': 'labeled_rule_base'}}))"
```

Output: `src/experiments/results/scrubber_degradation_labeled_rule_base/`

#### LLM team (scrubber · `llm` · Ollama or vLLM required)

```bash
python -c "from scenario.runner import run_scenario; print(run_scenario('scrubber_degradation', overrides={'agents': {'mode': 'llm'}}))"
```

Output: `src/experiments/results/scrubber_degradation_llm/` (`run_id_llm` in `scenario.yaml`)

To use a different model or run name, change `llm.model` in `agents.yaml` or override `output.run_id_llm` before the run.

### ssos_eclss_loop (SSOS live ECLSS)

#### mock (host, no ROS2)

```bash
python -m scenario.ssos_eclss_loop.scenario_run --backend mock --actor-mode none
python -m scenario.ssos_eclss_loop.scenario_run --backend mock --actor-mode labeled_rule_base
python -m scenario.ssos_eclss_loop.scenario_run --backend mock --actor-mode llm
```

Example output: `src/experiments/results/ssos_eclss_loop_labeled_rule_base/`

PowerShell equivalent:

```powershell
python -m scenario.ssos_eclss_loop.scenario_run --backend mock --actor-mode labeled_rule_base --steps 8
```

#### ros2 (inside SSOS Docker)

```bash
# Terminal 1: after starting SSOS container, ECLSS headless
~/dev/ssos/ssos-run.sh
# Inside container: bash /root/ssos-eclss-headless.sh

# Terminal 2: host repo root
./scripts/run_ssos_eclss_loop.sh --actor-mode labeled_rule_base
./scripts/run_ssos_eclss_loop.sh --actor-mode llm
```

Inside container: `ea-loop --actor-mode labeled_rule_base` (requires synced `src/`).

Apply prior run design proposals:

```bash
python -m scenario.ssos_eclss_loop.scenario_run --backend mock --actor-mode llm \
  --apply-proposals src/experiments/results/ssos_eclss_loop_llm/design_proposals.json
```

graph_rewire E2E: `./scripts/run_graph_rewire_e2e.sh` (requires ECLSS headless)

Details: [scenario-ssos-eclss-loop.md](scenario-ssos-eclss-loop.md).

### Main output files

#### scrubber_degradation

| File | Description |
| --- | --- |
| `telemetry.jsonl` | CO₂, efficiency, power margin, EPS support |
| `messages.jsonl` | Agent messages and reasoning |
| `events.jsonl` | Anomaly injection, recovery commands, design-change events |
| `design_state.jsonl` | Topology at each step start (before agent actions) |
| `design_proposals.json` | Post-run permanent design |
| `summary.json` | Run summary (`agents_mode`, final CO₂, etc.) |

#### ssos_eclss_loop

| File | Description |
| --- | --- |
| `telemetry.jsonl` | CO₂/O₂/water storage (kg / L) |
| `health_metrics.jsonl` | Storage-based safe / warning / critical |
| `messages.jsonl` | `operational_command`, deliberation, reasoning |
| `events.jsonl` | `operational_applied` / `operational_rejected` |
| `design_proposals.json` | Post-run `ssos_graph` (`action_profile`, `graph_rewire`, etc.) |
| `summary.json` | `backend`, `peak_co2_storage_kg`, `operational_command_count`, etc. |
| `provenance.jsonl` | Operational records (`record_type: operational`) |

Schema details: [docs/api-contracts.md](api-contracts.md) · Reading outputs: [scenario-ssos-eclss-loop.md](scenario-ssos-eclss-loop.md#reading-outputs)

---

## Dashboard

```bash
source .venv/bin/activate
python -m streamlit run src/tools/dashboard/app.py
```

Open `http://localhost:8501`. See [Dashboard at a glance](#dashboard-at-a-glance) above.

- **Overview** — single run or two-run comparison (scrubber: CO₂ ppm / EPS; ssos: storage kg)  
- **Step replay** — timeline, messages, reasoning step by step (ssos: operational timeline)  
- Sidebar run selection; `Compare with another run` for LLM vs LLM comparisons  

- Runs with `summary.scenario == "ssos_eclss_loop"` branch to dedicated `ssos_views` UI

Results: `src/experiments/results/<run_id>/`

---

## Repository structure

| Path | Purpose |
| --- | --- |
| `src/core/agents/` | Persona, Team ABC, memory, LLM client |
| `src/environment/` | `SimulatorProtocol` (scrubber), `EclssBackend` / `Ros2EclssBridge` (ssos), EPS mock / `Ros2EpsBridge` |
| `src/scenario/` | `scrubber_degradation`, `ssos_eclss_loop`, teams, `design_proposals` |
| `src/experiments/results/` | Run results (gitignore recommended) |
| `src/tools/dashboard/` | Streamlit UI |
| `src/integrations/one_piece/` | provenance record generation |
| `docs/ja/` | Japanese design, API, and scenario documentation |
| `docs/ja/memo/` | Japanese implementation records and backlog |
| `docs/en/` | English documentation |
| `docs/en/memo/` | English implementation records and backlog ([development-plan.md](development-plan.md)) |

Dependency direction: `tools → scenario → environment → core`

---

## License

[Apache License 2.0](https://github.com/hirototamura/engineering_agents/blob/main/LICENSE.txt) — Copyright 2026 One Piece Engineering
