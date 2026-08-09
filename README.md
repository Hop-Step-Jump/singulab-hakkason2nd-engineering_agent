# Engineering Agents — ECLSS Resilience Loop

Research repository that simulates **agent teams** detecting, responding to, and proposing design changes after **ECLSS** (Environmental Control and Life Support System) anomalies on a mock **Space Station OS (SSOS)** simulator.

---

## Quick start

Run your first simulation in a few minutes. The **`ea`** CLI is the recommended entry point.

**What you need**

- **Python 3.11+** and **Git** on every platform
- **Docker** only for `ssos_eclss_loop` with `--backend ros2` (live SSOS plant)
- **Ollama** only for `--agents-mode llm`

### Install (macOS / Linux)

```bash
git clone https://github.com/hirototamura/engineering_agents.git
cd engineering_agents

python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"

ea doctor
```

### Install (Windows PowerShell)

```powershell
git clone https://github.com/hirototamura/engineering_agents.git
cd engineering_agents

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[dev]"

python -m tools.cli doctor
```

For SSOS live runs, install [Docker Desktop](https://www.docker.com/products/docker-desktop/) with the **WSL 2** backend and run `scripts/*.sh` via **Git Bash**. Full Windows walkthrough: [docs/en/overview.md §2B](docs/en/overview.md#2b-windows-powershell--docker-desktop).

If `ea` is not on `PATH`, use `python3 -m tools.cli` instead.

### Run a simulation (no Docker, no Ollama)

```bash
ea run scrubber_degradation --agents-mode labeled_rule_base --steps 20
ea results
```

| Command | Purpose |
| --- | --- |
| `ea run [SCENARIO]` | Run one simulation |
| `ea scenarios` | List available scenarios |
| `ea results [RUN_ID]` | Show recent runs or one `summary.json` |
| `ea doctor` | Check Python, dependencies, Docker/SSOS, Ollama |

Mock SSOS scenario:

```bash
ea run ssos_eclss_loop --backend mock --agents-mode labeled_rule_base --steps 8
ea results
```

### Scenarios at a glance

| Scenario | What it simulates | Typical command |
| --- | --- | --- |
| `scrubber_degradation` | CO₂ scrubber anomaly on a Python mock plant | `ea run scrubber_degradation --agents-mode labeled_rule_base` |
| `ssos_eclss_loop` | Agent team operating SSOS ECLSS (ARS/OGS/WRS) | `ea run ssos_eclss_loop --backend mock --agents-mode labeled_rule_base` |

Agent modes: **`none`**, **`labeled_rule_base`** (reproducible regression), or **`llm`** (Ollama).

### Where results are saved

```text
src/experiments/results/<run_id>/
```

| File | Description |
| --- | --- |
| `telemetry.jsonl` | Step-by-step plant metrics |
| `messages.jsonl` | Agent messages and reasoning |
| `design_proposals.json` | Post-run permanent design proposals |
| `summary.json` | Run metadata (`scenario`, `agents_mode`, etc.) |

```bash
ea results
python3 -m streamlit run src/tools/dashboard/app.py   # optional dashboard
```

### Dashboard demo

Overview and Step replay walkthrough for run `plant-sim-labeled-rule-base` (`ssos_eclss_loop` + `--backend plant_sim` + `--agents-mode labeled_rule_base`).

<video src="https://github.com/user-attachments/assets/f2c778af-bd48-4188-98ca-00ce106a7b38" controls muted playsinline width="100%">
  <a href="https://github.com/user-attachments/assets/f2c778af-bd48-4188-98ca-00ce106a7b38">Download MP4</a>
</video>

```bash
ea run ssos_eclss_loop --backend plant_sim --agents-mode labeled_rule_base --steps 40 \
  --run-id plant-sim-labeled-rule-base
python3 -m streamlit run src/tools/dashboard/app.py
```

**Next:** [Overview](docs/en/overview.md) · [Architecture](docs/en/architecture.md) · [CLI guide](docs/en/cli.md) · [SSOS integration](docs/en/ssos/index.md) · Japanese quick start: [docs/ja/index.md](docs/ja/index.md)

---

## Documentation / ドキュメント

| Language | Quick start | Overview | Engineering guide (AGENTS) |
| --- | --- | --- | --- |
| **English** | [docs/en/index.md](docs/en/index.md) | [docs/en/overview.md](docs/en/overview.md) | [docs/en/AGENTS.md](docs/en/AGENTS.md) |
| **日本語** | [docs/ja/index.md](docs/ja/index.md) | [docs/ja/overview.md](docs/ja/overview.md) | [docs/ja/AGENTS.md](docs/ja/AGENTS.md) |

### Design docs / 設計ドキュメント

| | English | 日本語 |
| --- | --- | --- |
| Architecture | [docs/en/architecture.md](docs/en/architecture.md) | [docs/ja/architecture.md](docs/ja/architecture.md) |
| API contracts | [docs/en/api-contracts.md](docs/en/api-contracts.md) | [docs/ja/api-contracts.md](docs/ja/api-contracts.md) |
| Development plan | [docs/en/development-plan.md](docs/en/development-plan.md) | [docs/ja/development-plan.md](docs/ja/development-plan.md) |
| Scenario: scrubber_degradation | [docs/en/scenario-scrubber-degradation.md](docs/en/scenario-scrubber-degradation.md) | [docs/ja/scenario-scrubber-degradation.md](docs/ja/scenario-scrubber-degradation.md) |
| Scenario: ssos_eclss_loop | [docs/en/scenario-ssos-eclss-loop.md](docs/en/scenario-ssos-eclss-loop.md) | [docs/ja/scenario-ssos-eclss-loop.md](docs/ja/scenario-ssos-eclss-loop.md) |
| SSOS integration | [docs/en/ssos/index.md](docs/en/ssos/index.md) | [docs/ja/ssos/index.md](docs/ja/ssos/index.md) |

MkDocs preview: `pip install -e ".[dev]" && mkdocs serve` → [http://127.0.0.1:8000/](http://127.0.0.1:8000/) · [http://127.0.0.1:8000/ja/](http://127.0.0.1:8000/ja/)

---

## License

[Apache License 2.0](LICENSE.txt) — Copyright 2026 One Piece Engineering
