# CLI Guide

The unified CLI is the recommended way to run simulations.

## Prerequisites

- **Python 3.11+** on the Mac host (enforced by `pyproject.toml` and `ea doctor`)
- pyenv users: install any **3.11+** (e.g. `pyenv install 3.11`); optional `.python-version` pins the minor series

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
ea doctor
ea run
```

## Golden path

`ea run` with no arguments runs:

- scenario: `scrubber_degradation`
- agents: `labeled_rule_base` (no Ollama / vLLM required)
- steps: from `scenario.yaml` (default 50)

To match the physics-only baseline in `scenario.yaml`, pass `--agents-mode none`.

## Commands

| Command | Purpose |
| --- | --- |
| `ea run [SCENARIO]` | Run one simulation |
| `ea scenarios` | List available scenarios |
| `ea results [RUN_ID]` | List recent runs or show one `summary.json` |
| `ea doctor` | Check Python 3.11+, dependencies, Docker/SSOS mounts, Ollama, and vLLM |
| `ea job run SPEC.json` | Execute a serialized `RunSpec` (cluster-worker compatible) |
| `ea --version` | Show CLI version |

Equivalent module form:

```bash
python3 -m tools.cli run scrubber_degradation --agents-mode none
```

## Common flags

```bash
ea run scrubber_degradation --agents-mode labeled_rule_base --steps 30
ea run ssos_eclss_loop --backend mock --agents-mode none --steps 4
ea run scrubber_degradation --agents-mode llm --llm-provider vllm
ea run scrubber_degradation --set simulation.steps=10 --set agents.mode=none
ea run scrubber_degradation --override-file my_patch.yaml
ea run scrubber_degradation --output-dir /tmp/my-run
ea run scrubber_degradation --run-id sweep-001
ea run --dry-run --write-spec /tmp/job.json
ea job run /tmp/job.json
```

| Flag | Description |
| --- | --- |
| `--agents-mode` | `none`, `labeled_rule_base`, or `llm` |
| `--llm-provider` | `ollama` (local) or `vllm` (lab GPU server). Only used with `--agents-mode llm` |
| `--llm-model` | Override `agents.llm.model` (Ollama tag or vLLM served-model id) |
| `--steps` | Override `simulation.steps` |
| `--run-id` | Override output run id when using the default results root |
| `--output-dir` | Write directly to a directory path |
| `--results-root` | Override `src/experiments/results` (also `EA_RESULTS_ROOT`) |
| `--set KEY=VALUE` | Dot-notation deep override |
| `--override-file` | YAML/JSON patch merged into scenario config |
| `--backend` | `mock`, `plant_sim`, or `ros2` (`ssos_eclss_loop` only) |
| `--inject-failures` / `--no-inject-failures` | Apply the `ssos_eclss_loop` `subsystem_failures` schedule (default: off) |
| `--apply-proposals` | Apply prior `design_proposals.json` (`ssos_eclss_loop`) |
| `--seed` | Record a seed in `summary.json` for future sweeps |
| `--no-recreate` | Keep an existing output directory |
| `--dry-run` | Resolve the plan without executing |
| `--write-spec` | Write the resolved `RunSpec` JSON |
| `--json` | Machine-readable result on stdout |
| `--quiet` | Print only the output path |

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Simulation execution failed |
| 2 | Invalid arguments or unknown scenario |
| 3 | Environment error (for example Ollama or vLLM unreachable in `llm` mode) |

## Viewing results

```bash
ea results
python3 -m streamlit run src/tools/dashboard/app.py
```

## SSOS Docker (`ssos_eclss_loop` + ros2) { #ssos-docker-ssos_eclss_loop--ros2 }

Run simulations from the **Mac host** with `ea run`. Do **not** run `ea` inside the SSOS container (`ea` is installed in the host `.venv` only).

**Plant reset between runs**: every `ea run ssos_eclss_loop` (ros2) **stops and restarts** headless (solar + EPS + ECLSS) inside the container before the simulation. This prevents CO₂ storage, EPS state, and other plant variables from carrying over from the previous run. You do not need to keep headless running manually.

Design: [CLI guide](cli.md) · Helper scripts: [`scripts/ssos/README.md`](https://github.com/hirototamura/engineering_agents/blob/main/scripts/ssos/README.md)

### First time: setup through simulation (full command list)

**Once per machine.** Run everything on the **host** terminal (do not enter the container for `ea run`).

```bash
cd /path/to/engineering_agents

# 1. Python 3.11+ virtualenv and CLI
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
ea doctor

# 2. Create SSOS container (mounts scripts/ssos/* to /root/)
#    Starts Colima / Docker if needed (Apple Silicon: linux/amd64 + Rosetta)
./scripts/ssos/mac/ssos-run-detached.sh

# 3. Optional: verify mounts
docker ps --filter name=ssos
docker exec ssos test -f /root/ssos-eclss-headless.sh && echo "headless helper OK"
docker exec ssos test -d /ea/src/scenario/ssos_eclss_loop && echo "src mount OK"

# 4. Simulation
ea run ssos_eclss_loop --agents-mode labeled_rule_base --steps 50

# 5. Results
ea results
```

| Mount | Purpose |
| --- | --- |
| `scripts/ssos/*` → `/root/` | Headless scripts (`ssos-eclss-headless.sh`, launch files) |
| `src` → `/ea/src` | Code |
| `experiments/results` → `/ea/results` | Run outputs on the host |

For LLM agents, start Ollama on the host **or** reach the lab vLLM server (LAN/VPN) and use `--agents-mode llm`. Example: `--llm-provider vllm`. No second terminal for headless.

### After setup: simulation only (full command list)

No venv or container setup needed if the container already exists.

**Container is Up** (`docker ps --filter name=ssos` shows `Up`):

```bash
cd /path/to/engineering_agents
source .venv/bin/activate
ea run ssos_eclss_loop --agents-mode labeled_rule_base --steps 50
ea results
```

**Container is stopped** (`Exited` — for example after `exit` from an interactive shell):

```bash
docker start ssos
cd /path/to/engineering_agents
source .venv/bin/activate
ea run ssos_eclss_loop --agents-mode labeled_rule_base --steps 50
ea results
```

Volume mounts are fixed at container **create** time. If helper scripts are missing, recreate with `./scripts/ssos/mac/ssos-run-detached.sh` (first-time block above).

**Interactive debugging** (optional): `./scripts/ssos/mac/ssos-run.sh` → inside container: `bash /root/ssos-eclss-headless.sh`

**Windows / Linux**: no bundled runner yet — see manual mount steps in `scripts/ssos/README.md`.

### Mock / plant_sim backends (no Docker)

```bash
ea run ssos_eclss_loop --backend mock --agents-mode labeled_rule_base --steps 8
ea run ssos_eclss_loop --backend plant_sim --agents-mode labeled_rule_base --steps 72
ea run ssos_eclss_loop --backend mock --agents-mode llm --set agents.max_actions_per_step=8
```

`plant_sim` adds crew metabolism, WRS water-loop closure, and mass-balance ledgers — see [Plant Sim backend](memo/ssos_eclss_loop/plant_sim_backend.md).

### Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `SSOS_CONTAINER` | `ssos` | Docker container name |
| `EA_MOUNT_SRC` | `/ea/src` | Mounted source path inside container |
| `EA_MOUNT_RESULTS` | `/ea/results` | Mounted results path inside container |
| `EA_HEADLESS_POLL_TIMEOUT_S` | `120` | Wait for ros2 graph after headless restart |

`LLM_PROVIDER`, `VLLM_BASE_URL`, `VLLM_MODEL`, `VLLM_API_KEY`, and `VLLM_API_TIMEOUT` are forwarded into the container so ros2 llm jobs match host preflight.

### Exit code 3 (environment)

If you see `SSOS environment not ready`:

1. `docker ps --filter name=ssos` — is the container **Up**? If not: `docker start ssos`
2. `docker exec ssos test -f /root/ssos-eclss-headless.sh` — if missing, recreate with `./scripts/ssos/mac/ssos-run-detached.sh`
3. `docker exec ssos test -d /ea/src/scenario/ssos_eclss_loop` — if missing, recreate the container (src mount)
4. Run `ea run` from the **host**, not inside the container

See also: [ssos/quickstart.md](ssos/quickstart.md).

## Parallel runs (future)

Each simulation is described by a `RunSpec` JSON file. A future batch runner can fan out many specs to workers that all call:

```bash
ea job run /worker/jobs/job-0042.json
```

Draft batch manifest (not implemented):

```yaml
batch_id: sweep_2026_06_27
jobs:
  - scenario: scrubber_degradation
    overrides:
      agents:
        mode: labeled_rule_base
      simulation:
        steps: 50
    run_id: sweep_0001
```

## Legacy entry points

These still work and delegate to the same execution path:

- `python3 src/scripts/run_mock_eclss.py`
- `python3 -m scenario.ssos_eclss_loop.scenario_run`
- `from scenario.runner import run_scenario`
