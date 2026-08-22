
# Homogeneous Agent Team Redesign Plan

> For implementation tracking. Kept in sync with the Cursor plan.
>
> **ssos_eclss_loop follow-up (shipped):** in-sim actors no longer emit post-run design. That work moved to a separate designer team. See [post_run_design_agent.md](../ssos_eclss_loop/post_run_design_agent.md). This memo still describes the shared homogeneous-team pattern (and scrubber, which keeps a single team).

## Status

| ID | Task | State |
| --- | --- | --- |
| mode-rename | Rename `labeled_llm` → `llm` | **done** |
| team-config | `load_team` / `agents.yaml` new schema, deprecate `main_role` | **done** |
| situation-split | Separate Telemetry / World state, fully remove policy from llm | **done** |
| llm-flow | 1 round + rotating action rep | **done** |
| labeled-rules | Policy-driven rules, `engineer_*` attribution | **done** |
| post-run-rep | Design rep, llm post-run without policy | **done** |
| tests-docs | Tests and documentation follow-through | **done** |

## Background and approach

**Problem**: Fixed four roles (monitor / diagnostician / operator / design_engineer) boxed discussion and action into patterns, encouraging synchronization and hold convergence.

**Implementation**

- Heterogeneous four roles → **N agents with the same persona** (default N=4, `engineer_1` .. `engineer_N`)
- **Deliberation**: **1 round only** (Round2 / react removed)
- **Runtime recovery**: Representative `engineer_{(step-1) % N}` takes action
- **Post-run design**: Representative from the final step proposes
- **`main_role` removed**
- **Mode name**: `labeled_llm` → **`llm`**
- **Full policy separation**: In `llm`, do not read `self.policy` or embed it in prompts

## Agent modes

| `agents.mode` | Meaning | Team composition |
| --- | --- | --- |
| `none` | Physics only | No agents |
| `labeled_rule_base` | Rule-based (`policy`) | Homogeneous N |
| `llm` | LLM (Ollama) | Homogeneous N, N+1 LLM/step |

## Policy separation (fixed rules)

- `build_llm_situation(obs)` / `build_llm_post_run_situation(...)` — no policy argument
- Post-run design policy gate is **labeled_rule_base only**; `llm` always calls LLM with no gate

## Implementation log

### Step 1: mode-rename ✅

- `runner.py`, `scenario_run.py`, `scenario.yaml`: `labeled_llm` → `llm`, `run_id_llm`
- No backward-compat alias

### Step 2: team-config ✅

- `Persona`: `agent_id` + `persona` only (`main_role` removed)
- `load_team` / `TeamConfig` / `build_personas`
- `agents.yaml`: `team` + `policy` schema
- `DeliberationPhase`: `deliberation` | `action` | `post_run_proposal` (REACT removed)

### Step 3: situation-split ✅

- `build_llm_situation`: `### Telemetry` + `### World state`
- `_situation_context` (Rule threshold injection) removed
- `TEAM_CHARTER` updated

### Step 4: llm-flow ✅

- All N deliberate → 1 action rep
- Round2 removed

### Step 5: labeled-rules ✅

- Rule engine centered on `policy.co2_recovery_ppm`
- `from_role`: `engineer_*`, recovery via action rep

### Step 6: post-run-rep ✅

- design rep = `action_rep_id(steps)`
- llm post-run Situation has no policy-derived fields

### Step 7: tests-docs ✅

- 31 tests passing
- README, architecture, api-contracts, scenario-scrubber-degradation updated

## Retrospective

- **Policy separation** fixed at code level by `self.policy = {}` in `llm_mode` branch
- **labeled_rule_base regression** maintained with single `co2_recovery_ppm` threshold (old monitor 900 ppm alert integrated)
- **Tests**: `HealthStatus.value` is lowercase (`warning`) — note for World state notation
