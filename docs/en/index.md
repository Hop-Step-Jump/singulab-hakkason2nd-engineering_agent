# Quick start

Run your first simulation in a few minutes. Engineering Agents simulates how an **agent team detects ECLSS anomalies, responds during the run, and proposes permanent design changes afterward**.

!!! tip "What you need"
    - **Python 3.11+** and **Git** on every platform
    - **Docker** only for `ssos_eclss_loop` with `--backend ros2` (live SSOS plant)
    - **Ollama** or lab **vLLM** only for `--agents-mode llm`

---

## Install

=== "macOS / Linux"

    ```bash
    git clone https://github.com/hirototamura/engineering_agents.git
    cd engineering_agents

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -U pip
    pip install -e ".[dev]"

    ea doctor
    ```

=== "Windows (PowerShell)"

    #### 1. Python environment

    ```powershell
    git clone https://github.com/hirototamura/engineering_agents.git
    cd engineering_agents

    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install -U pip
    python -m pip install -e ".[dev]"

    python -m tools.cli doctor
    python -m pytest -q
    ```

    #### 2. Docker Desktop (SSOS live runs only)

    Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) with the **WSL 2** backend. Do **not** enable Windows Containers.

    ```powershell
    wsl --status
    docker info --format "OSType={{.OSType}} OperatingSystem={{.OperatingSystem}}"
    docker run --rm hello-world
    ```

    | Installer option | Selection |
    | --- | --- |
    | Use WSL 2 instead of Hyper-V | Enabled |
    | Allow Windows Containers | Disabled |

    If `wsl --status` reports WSL is missing: run `wsl --install` from an administrator PowerShell, reboot, then start Docker Desktop.

    #### 3. Run SSOS scripts

    Use **Git Bash** for `scripts/*.sh` wrappers. Example:

    ```powershell
    & "C:\Program Files\Git\bin\bash.exe" -lc "ea run ssos_eclss_loop --backend mock --agents-mode labeled_rule_base --steps 8"
    ```

    !!! tip "Windows gotchas"
        - If `python` opens the Microsoft Store, disable the Python App Execution Alias or use the full path to your install.
        - If `Activate.ps1` is blocked: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, or call `.\.venv\Scripts\python.exe` directly.
        - Full Windows + Docker walkthrough: [Overview §2B](overview.md#2b-windows-powershell--docker-desktop).

!!! note "Cloud / CI environments"
    The update script may install the package into system Python with `pip install -e ".[dev]"`. In that case use `python3 -m tools.cli` instead of `ea`.

---

## Run a simulation with the CLI

The unified **`ea`** CLI is the recommended entry point.

### Golden path (no Docker, no Ollama)

```bash
ea run scrubber_degradation --agents-mode labeled_rule_base --steps 20
ea results
```

| Command | Purpose |
| --- | --- |
| `ea run [SCENARIO]` | Run one simulation |
| `ea scenarios` | List available scenarios |
| `ea results [RUN_ID]` | Show recent runs or one `summary.json` |
| `ea doctor` | Check Python, dependencies, Docker/SSOS, Ollama, vLLM |

Module form (equivalent):

```bash
python3 -m tools.cli run scrubber_degradation --agents-mode labeled_rule_base --steps 20
```

!!! tip "Design → verification loop"
    Run N issues `design_proposals.json`. Run N+1 with `--apply-proposals` merges config and re-simulates — see [ssos_eclss_loop scenario](scenario-ssos-eclss-loop.md#how-to-run).

### Mock SSOS scenario (no Docker)

```bash
ea run ssos_eclss_loop --backend mock --agents-mode labeled_rule_base --steps 8
ea results
```

### Live SSOS (Docker + ros2)

First-time setup on macOS — run on the **host** only:

```bash
./scripts/ssos/mac/ssos-run-detached.sh
ea run ssos_eclss_loop --agents-mode labeled_rule_base --steps 50
ea results
```

Details: [SSOS Docker setup](ssos/quickstart.md) · Full CLI reference: [CLI guide](cli.md)

---

## Scenarios at a glance

| Scenario | What it simulates | Backend | Typical command |
| --- | --- | --- | --- |
| [scrubber_degradation](scenario-scrubber-degradation.md) | CO₂ scrubber anomaly on a Python mock plant | `StationSimulator` | `ea run scrubber_degradation --agents-mode labeled_rule_base` |
| [ssos_eclss_loop](scenario-ssos-eclss-loop.md) | Agent team operating SSOS ECLSS (ARS/OGS/WRS) | `mock` or `ros2` | `ea run ssos_eclss_loop --backend mock --agents-mode labeled_rule_base` |

Both scenarios share the same agent pattern: **`none`**, **`labeled_rule_base`** (reproducible regression), or **`llm`** (Ollama or lab vLLM).

---

## Where results are saved

Default output root:

```text
src/experiments/results/<run_id>/
```

| File | Description |
| --- | --- |
| `telemetry.jsonl` | Step-by-step plant metrics |
| `messages.jsonl` | Agent messages and reasoning |
| `events.jsonl` | Anomalies, commands, design events |
| `design_proposals.json` | **Post-run** permanent design proposals |
| `summary.json` | Run metadata (`scenario`, `agents_mode`, peaks, etc.) |
| `health_metrics.jsonl` | Safe / warning / critical (ssos_eclss_loop) |

Override with `--run-id`, `--output-dir`, or `EA_RESULTS_ROOT`.

```bash
ea results                          # list recent runs
ea results scrubber_degradation_labeled_rule_base
python3 -m streamlit run src/tools/dashboard/app.py   # optional dashboard
```

---

## Next steps

| Topic | Page |
| --- | --- |
| Project goals and dashboard | [Overview](overview.md) |
| Layer design and agent flow | [Architecture](architecture.md) |
| JSONL and API contracts | [API contracts](api-contracts.md) |
| Coding agent discipline | [Engineering guide](AGENTS.md) |
| SSOS Docker + ROS 2 integration | [SSOS integration](ssos/index.md) |
| Browse docs locally | `pip install -e ".[dev]" && mkdocs serve` → [http://127.0.0.1:8000](http://127.0.0.1:8000) |
