# AGENTS.md — Engineering Agents Guide

This file is the entry point for **human contributors** and **coding agents** (Cursor, etc.).

**Read the full guide in your language:**

| Language | Guide |
| --- | --- |
| **English** | [docs/en/AGENTS.md](docs/en/AGENTS.md) |
| **日本語** | [docs/ja/AGENTS.md](docs/ja/AGENTS.md) |

---

## One-line summary

**The paramount requirement is the mission itself. Design and verification requirements can be revised under One Piece. Design and verification must follow physics and must not violate the mission.**

---

## Quick reference (layers)

```text
tools → scenario → environment → core
integrations/one_piece ← called from scenario
```

Do not import upward across layers. Do not put LLM or Persona logic in `environment/`.

After changes, run `pytest`.

---

## Cursor Cloud specific instructions

Pure Python project (Python 3.12). The update script installs the package editable via `pip install -e ".[dev]"` into the **system** Python (no virtualenv), so `python3 -m pytest`, `python3 -m tools.cli`, etc. work in any fresh shell.

### Minimal scope for “environment works”

Do **not** treat the Streamlit dashboard as the smoke test. Visualization is optional; the mission is the **design→verification loop**:

```text
Run N   → simulation → design_proposals.json issued (post-run permanent design)
Run N+1 → --apply-proposals → config merged → re-simulate → telemetry vs verification requirements
```

**Canonical 2-run smoke** (no Ollama, no ROS2): `ssos_eclss_loop` with `--backend mock` and `labeled_rule_base`. Use **distinct `--run-id` values** — the default `ssos_eclss_loop_labeled_rule_base` is recreated on each run (`EventLog.prepare_run_dir` removes the existing directory), which would delete Run 1 outputs before you can compare them.

```bash
python3 -m tools.cli run ssos_eclss_loop --backend mock --agents-mode labeled_rule_base --steps 20 \
  --run-id cloud-smoke-run1
python3 -m tools.cli run ssos_eclss_loop --backend mock --agents-mode labeled_rule_base --steps 5 \
  --run-id cloud-smoke-run2 \
  --apply-proposals src/experiments/results/cloud-smoke-run1/design_proposals.json
```

Confirm Run 1 wrote `src/experiments/results/cloud-smoke-run1/design_proposals.json` (`design_domain: ssos_graph`, non-empty `changes`). Confirm Run 2 completed with proposals merged. Compare `cloud-smoke-run2/summary.json` and `telemetry.jsonl` against Run 1 — behavior should reflect applied config while Run 1 artifacts remain intact.

`scrubber_degradation` also emits `design_proposals.json` after a run, but **does not yet re-inject proposals into the next simulation** (dashboard Before/After is preview only). Closing that loop for scrubber is backlog; do not use scrubber alone as proof of a closed loop.

### Tooling and CI

- Console scripts (`ea`, etc.) land in `~/.local/bin`, which is not on `PATH`. Prefer `python3 -m tools.cli …` or add `~/.local/bin` to `PATH`. See [docs/en/cli.md](docs/en/cli.md).
- Tests: `python3 -m pytest --ignore=tests/e2e` (matches CI). Full `tests/e2e` needs SSOS Docker + ROS2 (`SSOS_E2E=1`, self-hosted runner) — not required for the minimal loop smoke above.
- `agents.mode: llm` needs Ollama or the lab vLLM server (LAN or VPN); `ssos_eclss_loop` default `ros2` backend needs SSOS Docker. Both are **out of scope** for minimal loop verification — use `labeled_rule_base` + `--backend mock`.
- Dashboard (optional): `python3 -m streamlit run src/tools/dashboard/app.py --server.headless true` reads `src/experiments/results/<run_id>/`.
