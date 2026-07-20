
# Backlog — Research & Design Topics

Topics outside MVP scope that are worth tracking. Implementation priority follows the roadmap in [mvp_plan.md](scrubber_degradation/mvp_plan.md). SSOS integration follow-ups after Phase 0–7 completion are tracked in [ssos_eclss_loop/ssos_eclss_loop_connection_plan.md](ssos_eclss_loop/ssos_eclss_loop_connection_plan.md).

---

## BL-001: Labeled Roles vs Emergent Roles (Base Role) { #bl-001 }

**Status**: Under consideration (Week-1 onward)  
**Related**: Day 4 agent team design, lunar_agents structured communication experiments

### Background

Operational-phase agent teams (Monitor / Diagnostician / Operator / DesignEngineer, etc.) may be nothing more than **human convenience labels for division of labor**. In the MVP we assign **scenario-specific roles** tailored to `scrubber_degradation` to drive anomaly response, but this is a pragmatic choice for demo viability.

### Research questions

| Condition | Hypothesis |
| --- | --- |
| **Labeled** — Explicit assignment of four scenario-specific roles | Faster anomaly response and higher reproducibility. Easier prompt/rule design. |
| **Unlabeled** — Base Role agents (no role name or role instructions) | Role division suited to the situation may **emerge** from telemetry and communication history alone. |
| **Comparison** | Quality of emergence (response speed, design-change validity, communication redundancy) can be quantitatively compared. |

### Value

- Extends lunar_agents’ “structured communication · individuality → emergence” into an **ECLSS resilience loop** context
- Provides evidence for the design choice of assigning roles vs not
- Can connect to One Piece provenance for “who proposed the design change”

### Experiment plan (not scheduled)

1. Same `scrubber_degradation` scenario, same Mock ECLSS
2. **Run A**: `agents.mode: labeled_rule_base` (four roles dedicated to scrubber_degradation)
3. **Run B**: `agents.mode: base` (N Base Role agents, no role YAML)
4. Comparison metrics (draft):
   - Steps to recovery (CO2 < 1000)
   - `messages.jsonl` message_type diversity / self-described role equivalents
   - Number of design changes and final health
   - With LLM: reasoning individuality (reuse lunar_agents metrics)

### Relation to MVP

- **Week-1**: Labeled + rule_based only (no generic role framework)
- **BL-001**: Week-2 onward or post-hackathon. Add `agents.mode: base` when Base Role is implemented
- Together with **BL-002**, forms the foundation for a three-way comparison: fixed heterogeneous / homogeneous N / emergent unlabeled

---

## BL-002: Evolutionary Persona Formation (Homogeneous vs Heterogeneous Teams) { #bl-002 }

**Status**: Under consideration (after homogeneous N-agent team introduction)  
**Related**: Homogeneous agent team redesign plan, BL-001 (emergent roles), Day 8 persona workshop, hardware development organization theory

### Background

When personas are fixed per role by hand, thinking and behavior tend to converge into rigid patterns (e.g. hold synchronization in the old `labeled_llm` / fixed four-role setup). The MVP avoids this by moving to **homogeneous N agents** (single persona · variable headcount · representative action / post-run design), but **AI-driven evolution and generation of personas** is not yet started.

As a substitute for human teams that develop hardware, the central question is **how to organize which AI (or AI team)** — i.e. **organization theory and team design**.

### Research questions

| Axis | Question |
| --- | --- |
| **Homogeneous vs heterogeneous** | Which improves emergence, recovery, and design proposal quality: all identical personas (homogeneous N) or differentiated personas (heterogeneous N)? Three-way comparison with fixed heterogeneous (current four roles). |
| **Unit of evolution** | Which acts as the “gene”: individual persona / team charter / role-division pattern? |
| **Selection pressure** | How to map simulation KPIs (CO2 recovery, power, post-run design validity) to fitness? |
| **Human-team substitute** | In closed-loop ECLSS and hardware development, which human-team functions (specialization, review, representative decision) should an AI organization reproduce? |

### Value

- Goes beyond hand-written persona rigidity; update team characteristics per run or per generation
- As a middle layer between homogeneous teams (near-term MVP) and heterogeneous/emergent (BL-001), clarifies the design space of **who decides the persona**
- Future connection to One Piece / provenance for “which generation · which individual proposed the design”

### Experiment plan (not scheduled)

1. **Baseline**: Homogeneous N + hand-written single persona (near-term implementation)
2. **Variant A**: Heterogeneous N + evolution-generated personas (random initial population, crossover · mutation)
3. **Variant B**: Homogeneous but only charter / policy evolve (persona body fixed)
4. Compare: recovery steps, design proposal adoption rate (human evaluation), discussion diversity, rigidity metrics (utterance n-gram overlap, etc.)

### Relation to MVP

- **Near term**: Homogeneous N + hand-written persona (no evolution). **Out of implementation scope** for this item
- **BL-002**: After homogeneous team stabilizes. Start from evolution loop, evaluation function, organization design docs

---

## BL-003: ROS launch remap (Phase 8 — graph_rewire A) { #bl-003 }

**Status**: Not started (after Phase 7 client remap complete)  
**Related**: [ssos_eclss_loop_connection_plan.md](ssos_eclss_loop/ssos_eclss_loop_connection_plan.md) Phase 7a, [ssos_ros2_graph_design_investigation.md](ssos_eclss_loop/ssos_ros2_graph_design_investigation.md)

### Background

Phase 7a covers **client-side remap in `Ros2EclssBridge` only**. Without `--ros-args -r` / launch `remappings` (A) at SSOS node startup, **internal wiring such as OGS↔WRS does not change**. The hackathon demo path (ea-loop / labeled / LLM) works without A, but scrubber-style `add_edge` material-flow changes require A + (if needed) an rclpy gateway.

`ssos_graph.rewires` can be reused in Phase 8 (branch from the same JSON for bridge vs launch).

### Tier plan

| Tier | Effort | Change locations | Deliverables |
|------|--------|------------------|--------------|
| **8a PoC** | 1–2 days | Hand-written `remappings` in `~/dev/ssos/ssos-headless.launch.py` | Launch remap verification for one topic/service |
| **8b proposals→launch** | 3–5 days | engineering_agents + `~/dev/ssos/` per table below | `--apply-proposals` → remap on next headless start (**ECLSS restart required**) |
| **8c Gateway** | 1–2 weeks | `environment/ssos/gateways/` (e.g. grey_water_router), launch Node add, collision detection, container E2E | Flow changes close to scrubber-style `add_edge` |

### Files to touch in 8b (draft)

**engineering_agents**

| File | Changes |
|------|---------|
| `scenario/ssos_eclss_loop/design_proposals.py` | `graph_rewire` adds `target_node` / `remap_rules[]` (`public`/`backend` kept for bridge) |
| `environment/ssos/launch_remap.py` (new) | `ssos_graph.rewires` → launch `remappings` generation |
| `scenario/ssos_eclss_loop/scenario_run.py` | manifest export |
| `scripts/ssos_container_run.sh` | warn headless restart when manifest present |

**~/dev/ssos/**

| File | Changes |
|------|---------|
| `ssos-headless.launch.py` | dynamic `remappings` or overlay launch |
| `ssos-eclss-headless.sh` | pass manifest / `SSOS_LAUNCH_REMAPS` to launch |

---

## BL-004: SSOS ECLSS loop — follow-ups { #bl-004 }

**Status**: Not started  
**Related**: [ssos_eclss_loop_connection_plan.md](ssos_eclss_loop/ssos_eclss_loop_connection_plan.md) (Phase 0–7 complete)

| Priority | Item | Description |
|----------|------|-------------|
| P1 | **ros2 E2E pytest (optional)** | SSOS container CI or live skip integration test |
| P1 | **LLM connection preflight** | Early fail with `OllamaClient.check_connection()` at llm mode start |
| P2 | **WRS in scenario team** | `SsosEclssLoopTeam` operates WRS goals / water services in labeled and LLM modes |
| P2 | **Single ros2 scenario: ECLSS + EPS** | Power crisis and ECLSS in one run (`eclss.backend=ros2` + `eps.backend=ssos_eps`) |
| P2 | **rclpy native ECLSS client** | Migrate from CLI bridge (latency, CI stability) |
| P3 | **MkDocs CI deploy** | `docs/ssos-mkdocs` branch |
| P3 | **upstream CO₂ scrubber** | SSOS ECLSS extension → new Mock scenario |

### Edge cases (low priority — noted in 7d, not implemented)

| Item | Note |
|------|------|
| `co2_critical` unused (labeled) | health evaluates critical but labeled rules only use `co2_high` |
| One Piece provenance heuristic | operational events depend on message parsing |
| labeled ignores command failure | not reflected in next-step rule branching |
| `set_parameter` arbitrary path | allowlist recommended for production SSOS |

---

## BL-005: SSOS EPS ROS2 bridge — follow-ups { #bl-005 }

**Status**: Phase 3a complete (PR-1–4), remainder not started  
**Related**: [ssos_eps_ros2_connection_plan.md](ssos_eclss_loop/ssos_eps_ros2_connection_plan.md)

### Complete (reference)

- `EpsBackend` / `Ros2EpsBridge` / `topic_map.py` / `build_eps_backend()`
- `request_eps_boost` **interim 3a** — when BCDU `discharging`, `current_draw * bus_voltage` + bridge timer
- `scripts/run_ssos_eps_smoke.sh`

### Not started

| Priority | Item | Description |
|----------|------|-------------|
| P2 | **PR-5 operations docs** | `docs/ssos-eps-integration.md` (separate PR) |
| P2 | **Phase 3b — direct BCDU discharge** | Call `/battery/battery_bms_*/discharge` services from bridge |
| P3 | **Phase 3c — `/bcdu/operation` Action** | SSOS upstream PR. Currently README only, not implemented |
| P3 | **Mac host↔container DDS** | CycloneDDS Peers, etc. Container-only execution for now |
| P2 | **Ongoing topic contract alignment** | Keep `eps_topics.py` in sync with SSOS real names (`/solar_controller/ssu_voltage_v`, etc.) |
| P2 | **EPS BCDU action (scrubber 3b)** | Discharge/boost Action path in `Ros2EpsBridge` (currently topic + command only) |

### Known limitations (3a interim)

- `/bcdu/operation` not implemented — discharge depends on SSOS auto thresholds + bridge timer
- `support_w` not in SSOS messages — bridge estimates watts
- ECLSS remains `MockEclssSimulator` on scrubber path (ECLSS+EPS single scenario is BL-004)

---

## BL-006: SSOS run reproducibility and dashboard enrichment (out of CLI v3 scope) { #bl-006 }

**Status**: Not started (after CLI v3 mounts + `ea run`)  
**Related**: [CLI guide](../cli.md), [scenario-ssos-eclss-loop.md](../scenario-ssos-eclss-loop.md)

CLI v3 focuses on **host one-command runs and results mounts**. The items below belong to the simulation/visualization layer.

### P1 — Plant initial state (CO2=500kg)

| Item | Description |
| --- | --- |
| `scenario.yaml` | `simulation.initial_co2_storage_kg: 500` (mock; currently 1500) |
| ros2 step 0 | Record `/co2_storage` after headless restart as `summary.plant_initial_co2_storage_kg` |
| Validation | Fail fast if outside tolerance vs target 500 (point to SSOS launch params) |
| SSOS side | Investigate launch params if headless default ≠ 500kg |

**Intent**: Run-to-run reset is handled by CLI (headless restart). Target CO2 level and validation are scenario/plant contract.

### P2 — Streamlit dashboard (rich SSOS views)

Target: `src/tools/dashboard/ssos_views.py`, `app.py` — duration, threshold lines, ops/messages, compare, deep link (see Japanese BL-006 for detail).

---

## BL-007: SSOS ↔ EA time and step synchronization (next integration phase) { #bl-007 }

**Status**: Under consideration (separate from CLI v3 / Phase 8)  
**Related**: [scenario-ssos-eclss-loop.md](../scenario-ssos-eclss-loop.md), [ssos_eclss_physical_phenomena_overview.md](ssos_eclss_loop/ssos_eclss_physical_phenomena_overview.md), BL-004 (WRS mock), BL-006 (run-boundary reproducibility)

### Background

- **EA `steps`** are decision cycles (observe → deliberate → act). The **SSOS ros2 plant** advances continuously on wall clock.
- Only `LoopMockEclssBackend` guarantees **1 EA step = 1 physics tick** via `advance_step()`.
- `ea run` headless restart resets state **between runs**, not **between steps** inside a run.
- Current SSOS headless has **no global time_scale / sim clock** ([space_station_os](https://github.com/space-station-os/space_station_os)).

**Conclusion (for now)**: Strict 1:1 mapping between EA steps and SSOS physics time is **likely too hard**. Capture options in backlog for the next integration phase (**not in cli_v3_plan**).

### Current coupling model (keep)

| backend | Meaning of step | Use |
| --- | --- | --- |
| `mock` | Explicit tick (`mock_dynamics`) | Agents, thresholds, LLM comparison, pytest |
| `ros2` | Instant snapshot + wait for Action completion | SSOS smoke, E2E, demos (few steps) |

### Option A — Expand SSOS mock inside engineering_agents (preferred first candidate)

Build an **integrated SSOS-equivalent mock** in this repo: topic semantics, WRS/OGS/ARS dynamics, EPS coupling under EA-controlled ticks.

| Item | Contents |
| --- | --- |
| Scope | Extend `LoopMockEclssBackend` or add `SsosPlantMock`; align with `eclss_topics.py` |
| WRS / OGS | Step-synced Action/Service effects on mock (links to BL-004 WRS team) |
| EPS | Drive with existing `MockEpsBackend` / `EpsStack` on same tick |
| Pros | No upstream dependency; fast pytest; **step = physics tick** by design |
| Cons | Drift from real SSOS; need contract tests for topics and Action types |

### Option B — Upstream SSOS sim clock / tick sync

Fork/clone [space_station_os](https://github.com/space-station-os/space_station_os) and add **upstream changes**: `use_sim_time` + `/clock`, or pause physics until EA ticks.

| Item | Contents |
| --- | --- |
| Scope | Headless launch, node timers, Crew/metabolism drivers |
| Pros | Closer to real plant with possible step sync |
| Cons | High cost; maintenance burden; **may be overkill** for Mac Docker + real-time ops |

### Option C — Mitigation only (short term; overlaps BL-006)

No strict sync; strengthen **observation contract**:

- Timestamps on telemetry; optional `step_dwell_s` after Actions
- Step-0 plant validation (BL-006)
- Dashboard: wall time vs step

### Open questions (unscheduled)

1. Primary axis for next integration phase: A, B, C, or hybrid (**logic on A, ros2 smoke on few steps**)
2. Option A boundary: same `EclssBackend` Protocol as `Ros2EclssBridge`?
3. Minimal upstream API if pursuing B (`tick(Δt)`, pause, sim clock)
4. Explicit `simulation.ssos_time_model: mock_tick | ros2_snapshot` in `scenario.yaml`?

### Relation to other backlog items

| BL | Relation |
| --- | --- |
| BL-004 | WRS team, ECLSS+EPS unified scenario — overlaps Option A |
| BL-006 | Run-boundary reproducibility, step-0 check — Option C; not step sync |
| BL-003 | Launch remap — independent |

### Relation to development plan

- **Not** in the next implementation priority list (provenance, Phase 8, etc.)
- Tracked under **“SSOS integration — next phase”** in [development-plan.md](../development-plan.md)
