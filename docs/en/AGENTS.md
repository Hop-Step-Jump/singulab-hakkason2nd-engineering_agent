# AGENTS.md — Guide for Engineering Agents

This file defines the north star and implementation discipline of the repository for **human contributors** and **coding agents (Cursor, etc.)** alike.

---

## Mission

Reproduce in software an engineering team that runs a **design–verification loop** for **autonomous development** of complex hardware.

The target is hardware in general that traditionally requires systems engineering — **satellites, spacecraft, rockets, aircraft, automobiles, humanoid robots**, and similar. **Reproducible design→verification loops** take priority over high-fidelity 3D or real-hardware connection.

**The primary scope of this repository is design and verification.** Supervision (setting design requirements and verification requirements, and validating those requirements themselves) is handled by a separate repository, **[One Piece](https://github.com/hirototamura/one-piece)**. Eventually, requirements must be pulled from One Piece, but **that is not implemented yet**. This repository stubs requirements in `scenario.yaml` and focuses on implementing the design–verification loop.

---

## Paradigm shift

The table below expresses vision; it is not a forecast of timing or ratios.


| Stage | Supervision | Design | Verification |
| -------- | ------- | --- | ------------------------------ |
| **Present** | Human | Human | Virtual world: physics simulation + human Physical world: human |
| **10 years out** | Human + AI | AI | Virtual world: physics simulation + AI Physical world: robot |
| **This demo** | Human + AI | AI | Virtual world: physics simulation + AI Physical world: N/A |


From **Present** to **This demo**, the main actors for design and virtual verification shift from human to AI. From **This demo** to **10 years out**, AI joins supervision, and physical-world verification shifts from human to robot.

### Supervision, design, verification — three roles linked by requirements

Supervision (human + AI) provides both **design requirements** and **verification requirements**. Supervision must supply a framework that satisfies these two kinds of requirements.

### Top requirement — the mission must not be violated

Above all requirements sits the **top requirement**. This is **the mission itself** (why the system exists) — a separate axis from reality and physical law. **It must never be violated**. Design and verification requirements can be revised iteratively, but abandoning or substituting the mission is not allowed.


| Kind | Revision | Example |
| ------------- | -------- | -------------------------- |
| **Top requirement** | Not allowed | The mission itself |
| **Design / verification requirements** | Supervision may revise iteratively | Thresholds, topology assumptions, acceptance scenarios (initial drafts may be wrong) |


To achieve the mission, follow this **top requirement** first. **Reality (physical law)** is a constraint design and verification must respect; verification questions it as perception of the physical world. When supervision’s design or verification requirements conflict with physics, propose **requirement revision to supervision** rather than bending design — and such proposals must not harm the mission (top requirement).


| Role | Essence | What must be satisfied |
| ------ | -------- | ---------------------------------------------------------------------------- |
| **Supervision** | Setting requirements | Provide requirements for design and requirements for verification |
| **Design** | Conception aligned with requirements | Meet supervision’s **design requirements** and output design proposals aligned with **physical principles**. If requirements are wrong, **propose requirement changes to supervision** |
| **Verification** | Perception of the physical world | Run simulation (virtual) or observation (physical) from design proposals and confirm whether supervision’s **verification requirements** are met. Propose requirement changes to supervision when needed |


Verification is simulation under physical law or observation by robots — **perception of the physical world**. In addition, deterministic confirmation against supervision’s verification requirements (thresholds, scenarios, acceptance criteria) is essential. In the virtual world, design proposals are fed into physics simulation and pass/fail is decided against verification requirements.

Supervision’s design and verification requirements may be **wrong in early stages**. Design need not be bent only to fit them. **Revising design and verification requirements themselves** is sometimes more important. Design and verification may propose changes to supervision (One Piece); the three roles iterate on requirements — only **without harming the mission (top requirement)**.

```text
Top requirement (the mission itself — do not violate)
 ↓
Supervision ⇄ design requirements + verification requirements (iterative revision; canonical source is One Piece)
 ↓
Design: design proposals meeting design requirements (aligned with physical principles)
        or requirement-change proposals to supervision (without harming the mission)
 ↓
Verification: design proposals → perception of physical world (simulation / observation)
              → meet verification requirements? (deterministic check)
              or requirement-change proposals to supervision (without harming the mission)
```

The loop exit is not only “change design to match requirements.” **Revising design and verification requirements to match reality (physics)** is also a legitimate outcome. Design that violates physics, or verification that hides it, is forbidden. Likewise, design or verification that **abandons the mission (top requirement)** is forbidden under any name of requirement revision.

Physical-world verification is **N/A** in this demo (as in the table). This repository implements **only the virtual world** — feeding design into **physics simulation mocking Space Station OS (SSOS)** and running through **AI (verification bridge)** to deterministic checks. Connection to real ROS2 / on-orbit systems is out of scope (`SsosAdapter` is a stub).

---

## Top principle: no self-dealing

In **10 years out** and **This demo**, both design and virtual-world verification are AI-driven. One misstep here becomes **AI self-dealing (hiding hallucination)**.


| | This demo / 10 years out | Conditions that avoid self-dealing |
| ------------ | ------------------ | ----------------------------------------------------------- |
| **Supervision** | Human + AI | Provide both **design requirements** and **verification requirements**. AI stays at situational judgment and discussion; humans retain final authority on requirements |
| **Design** | AI | Output design proposals. When requirements conflict with physical principles, **propose requirement changes to supervision** (no pass/fail judgment or unilateral requirement changes) |
| **Verification (virtual world)** | Physics simulation + AI | Confirm verification requirements from simulation results. When telemetry questions requirement validity, **propose requirement changes to supervision** |
| **Verification (physical world)** | N/A in this demo / robot in 10 years | Robot perception of physical world + verification requirement checks. Do not treat virtual pass as substitute for physical pass |


For a trustworthy enterprise product, separate **creativity (design AI)** from **cold physical law (simulation + deterministic checks)** so virtual pass/fail is independent of LLM subjectivity. Both **abandoning the mission (top requirement)** and **design or verification that violates physics** are forbidden.

### What supervision (human + AI) does

> **Scope note:** Supervision is implemented in the **One Piece** repository. This repository only stubs requirements in `scenario.yaml`. Pulling requirements from One Piece is future work.

- **Set design requirements** — performance, constraints, topology assumptions to satisfy (what to build)
- **Set verification requirements** — acceptance criteria, thresholds, scenarios (what counts as pass)
- **Human**: final judgment on defining and revising the above (whether to accept requirement-change proposals from design and verification)
- **AI**: discussion within the team, situational judgment, assistance interpreting requirements (humans retain authority over requirements themselves)

### What design (AI) does

- **Propose** topology, parameters, and permanent changes that meet supervision’s **design requirements** (`design_proposals.json`, etc.)
- Output design proposals aligned with **physical principles** (solver-ready form)
- When requirements are unrealistic or contradictory, **propose design and verification requirement changes to supervision** (fix requirements rather than bend design)
- Generate recovery-command proposals during runtime

### What verification does — virtual world (physics simulation + AI)

1. **Perception of the physical world** — Run simulation with a deterministic physics solver (SSOS math engine) using design proposals as input. No interpretation, rounding, or “probably fine.”
2. **Verification requirement checks** — Deterministic programs decide whether raw simulation data (telemetry JSON) meets supervision’s **verification requirements** (hard constraints, thresholds, scenarios). Do not ask an LLM for pass/fail.
3. **Requirement-change proposals** — When simulation shows requirements are wrong, propose verification requirement revision (and design requirements if needed) to supervision. Pass/fail rationale is telemetry; supervision decides requirement revision.
4. **Physical world is a separate track** — N/A in this demo. In 10 years, robots are expected to handle physical perception and verification checks, but virtual pass is not sufficient for physical pass.

---

## Concretization in this repository

This demo implements **design** and **verification (virtual world)** from the **This demo** row. ECLSS/EPS are only the reference scenario; the paradigm is domain-agnostic.

The **Supervision** column is One Piece’s responsibility. In the current MVP, thresholds and scenarios in `scenario.yaml` stub verification requirements; design-requirement stubs live near that file. Pulling requirements from One Piece is future work and is not touched now ([one-piece-integration.md](one-piece-integration.md) covers provenance export only).

### Current MVP (`scrubber_degradation`) — mapping to the table


| Table column | Actor in this demo | Output / implementation | Notes |
| --------------- | -------------------------------------- | ----------------------------------------- | ------------------------------------------- |
| **Supervision (human + AI)** | One Piece (future) / currently stubbed in `scenario.yaml` | `scenario.yaml`, `messages.jsonl` | Out of primary scope for this repo. Canonical requirements will move to One Piece |
| **Design (AI)** | Lead engineer (LLM or rules) | `design_proposals.json` | Fit to design requirements + physically sound design conditions. Not applied to simulator during runtime |
| **Verification · virtual world** | Physics simulation + verification bridge | `telemetry.jsonl`, `health_metrics.jsonl` | Simulation from design proposals → deterministic verification requirement checks |
| **Verification · physical world** | N/A | — | Out of scope for this repository |


The dashboard **After (if proposals applied)** is a preview of proposals, **not a virtual-world verified result**. Re-injecting design into the simulator to close the loop is the next step to complete the **This demo** row.

### Target end state (This demo row → foundation for 10 years out)

```text
[Top requirement] The mission itself (do not violate; defined by One Piece)
 ↓
[Supervision] One Piece (future) — set and revise design + verification requirements
 ⇄ requirement-change proposals from design and verification (without harming the mission)
 Currently: stubbed in scenario.yaml (this repo not yet integrated)
 ↓
[Design] AI (LLM) — primary scope of this repository
 → design proposals (`design_proposals.json` — scrubber uses `add_edge` etc. / ssos_eclss_loop uses `design_domain: ssos_graph`)
 → requirement-change proposals to supervision when needed
 ↓
[Verification · virtual world] Physics simulation + AI (verification bridge)
 → perception of physical world (simulation) from design proposals
 → telemetry.jsonl (raw data)
 → verification requirement checker (pure Python, threshold comparison)
 → pass / fail (deterministic)
 → requirement-change proposals to supervision when needed
 ↓
[Verification · physical world] This demo: N/A / 10 years out: robot perception + verification checks
```

Do not put LLM pass/fail judgment in the verification bridge. An LLM may write explanatory text, but **pass/fail rationale must be simulation output vs verification requirements**.

---

## Discipline for coding agents

### Layers and dependency direction (strict)

```text
tools → scenario → environment → core
integrations/one_piece ← called from scenario
```

Do not import upper layers from lower layers. Do not put LLM or Persona in `environment`.


| Path | Responsibility |
| ------------------- | --------------------------------------------- |
| `src/core/` | Persona, Team, memory, LLM client, event log |
| `src/environment/` | `SimulatorProtocol`, ECLSS/EPS physics mocks, SSOS topics |
| `src/scenario/` | Scenario YAML, runner, team implementations |
| `src/tools/` | Streamlit dashboard |
| `src/integrations/` | One Piece provenance |


### Do

- Focus on **design** and **virtual verification** from the **This demo** row. Stub supervision requirements in `scenario.yaml`; do not start One Piece integration yet.
- Make **design requirements** and **verification requirements** explicit in `scenario.yaml` and version-control them (temporary stub until One Piece integration).
- Design paths for design and verification to **propose requirement changes** to supervision (judge against current requirements until supervision revises).
- When requirements are unrealistic, consider **revising design and verification requirements** rather than bending design only (**top requirement** must not be violated).
- Run simulation from design proposals and **deterministically confirm current verification requirements**.
- Maintain **separation** of design proposals and runtime operations (current: only recovery commands at runtime; permanent changes are post-run proposals).
- Maintain **isolation** of `labeled_rule_base` `policy` and `llm` mode (do not mix policy thresholds into LLM prompts).
- Add virtual-world pass/fail to **`health_metrics` / scenario YAML / pure function checkers**.
- Follow **JSONL schema** for simulator output ([api-contracts.md](api-contracts.md)).
- Run `pytest` after changes.

### Do not

- Design or verify in ways that **abandon or substitute the mission (top requirement)**.
- Propose **physically impossible** design or hide it in verification.
- Run the design–verification loop without design and verification requirements (self-dealing without supervision).
- Let design or verification **unilaterally rewrite requirements** (proposals go to supervision; canonical source is One Piece / `scenario.yaml`).
- Declare verification requirements met without physical perception (simulation).
- Implement virtual-world “physics simulation + AI” with **LLM subjective pass/fail** (self-dealing).
- Let the verification bridge bypass the simulator and infer “as expected” from design content.
- In this demo where physical world is N/A, describe virtual pass as **physically verified**.
- Change permanent topology at runtime, breaking design–verification separation (`apply_design_change` removed in Phase 0).
- Put agent logic or Ollama dependencies in `environment`.
- Round telemetry or thresholds loosely to force pass.

### Agent modes (`agents.mode`)


| Mode | Use |
| ------------------- | ------------------ |
| `none` | Baseline (no agents) |
| `labeled_rule_base` | Highly reproducible ground-truth comparison and regression |
| `llm` | Experiments in situational judgment, discussion, and diversity of design proposals |


`labeled_rule_base` is **scaffolding** for the verification pipeline (comparison for supervision and design). `llm` is the AI-side experiment for design and supervision. In both cases, virtual-world physics verification is the simulator’s job.

### Test and run

```bash
pip install -e ".[dev]"
pytest
python -c "from scenario.runner import run_scenario; print(run_scenario('scrubber_degradation', overrides={'agents': {'mode': 'labeled_rule_base'}}))"
```

LLM mode requires Ollama. Prefer Fake LLM / `labeled_rule_base` for CI and regression.

---

## Contributing — filing issues

For feature, design, or integration proposals, use the **First-principles proposal** GitHub issue template (`.github/ISSUE_TEMPLATE/first_principles.md`). It structures four sections — current problem (A), why it matters (B), scope in/out (C), and expected outcome (D). **If you cannot fill them in concretely, the work is not ready to file.**

**Repository definition of first-principles thinking** (issue template §0):

> An approach that questions existing conventions and precedents, decomposes problems down to their fundamental elements, and builds new solutions by stacking only facts that can be reliably proven.

This is **not** the same as the `first_principles` **thinking-style archetype** lens in `team.archetypes` (agent deliberation prompts in `src/core/agents/persona.py`). The issue template governs **whether work is justified**; archetypes govern **how agents reason** during simulation.

---

## Related documentation


| Document | Content |
| ------------------------------------------------------------------------------ | ------------------------------------------ |
| [overview.md](overview.md) | Overview, run instructions, dashboard |
| [architecture.md](architecture.md) | Layers, execution flow, agent design |
| [api-contracts.md](api-contracts.md) | `SimulatorProtocol`, JSONL, design proposal schema |
| [development-plan.md](development-plan.md) | Incomplete features, roadmap |
| [one-piece-integration.md](one-piece-integration.md) | One Piece integration (provenance only for now; requirement pull is future) |
| [scenario-scrubber-degradation.md](scenario-scrubber-degradation.md) | Reference scenario specification |
| [docs/scenario-ssos-eclss-loop.md](scenario-ssos-eclss-loop.md) | SSOS live ECLSS scenario (Phase 0–7) |

---

## One-line summary (for agents)

**The top requirement is the mission itself. Design and verification requirements can be revised iteratively under One Piece. Design and verification follow physics and must not violate the mission.**
