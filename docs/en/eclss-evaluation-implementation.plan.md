---
name: eclss-evaluation-implementation
overview: Implement the A3 scorecard as a deterministic evaluator that scores plant_sim run artifacts. Physics integrity is an unscored gate; `evaluation.json` is canonical and `summary.json` is an index.
todos:
  - id: define-evaluation-contract
    content: Implement evaluation config, JSON contract, and deterministic scoring pure functions
    status: completed
  - id: expose-physics-ledger
    content: Expose plant_sim ledgers in telemetry and implement the physics gate
    status: completed
  - id: integrate-run-output
    content: Wire evaluation.json generation and summary index into run finalization
    status: completed
  - id: add-tests-docs
    content: Add unit/integration tests and sync JA/EN API docs and A3 scorecard
    status: completed
  - id: verify-regression
    content: Regression-check with non-E2E pytest and 2-run smoke
    status: completed
isProject: false
---

# ECLSS evaluator implementation

## Evaluation contract
- Full scoring applies only to `ssos_eclss_loop` with `backend=plant_sim` and `survival.enabled=true`. For all other runs, still emit `evaluation.json` with `not_applicable` and a reason.
- Run the unscored physics gate first: check missing required values, non-finite values, negative inventories, ledger residuals, processing while failed, and physical sign consistency of operation results. On FAIL, do not compute axis or total scores; mark `invalid`.
- When actors are enabled, maximum score is 100 (50 + 10×5). With `actor.mode=none`, exclude D/E for a maximum of 80. Do not treat inapplicable axes as zero or redistribute their points.

## Deterministic scoring formulas
- Actor survival: `50 × crew_remaining / crew_initial`. Per-cause loss is reported separately as physical floor vs band dwell.
- A/TCL: use `simulation_time_s` at the first `/eclss/events/crew_lost` observed in the run; score `10 × min(TCL / T_ref, 1)`. No loss with observation time ≥ `T_ref`: 10 points. Run ends before `T_ref` with no loss: right-censored → `incomplete`. No future extrapolation or automatic extension.
- B/Environment: equal weight on CO₂, O₂, and water; score 10 from time integral of severity normalized 0–1 from safe to critical boundaries. Do not double-count pre/post rows in the same step.
- C/Resource margin and recovery: equal weight on three resources. Record initial, pre-operation at first fault event, worst, terminal, and deltas; combine terminal safety margin and recovery from post-fault worst at configured ratios.
- D/Actor decision: combine response latency to danger episodes and command validity against observed state, failure state, and payload bounds at configured ratios. Device outcomes are not used for decision scoring.
- E/Device response: only operations judged valid in D; combine success, processed amount vs requested amount, and expected physical sign. For multiple operations, use individual result details as canonical; do not mis-attribute step-level deltas to individual operations.

## Implementation locations
- Add [`src/scenario/ssos_eclss_loop/evaluation.py`](/Users/naoya/develop/Singulab/hakkason2nd/engineering_agents/src/scenario/ssos_eclss_loop/evaluation.py): JSONL read, canonical row selection, physics gate, per-axis pure functions, and `evaluation.json` write.
- Add an `evaluation` section to [`src/scenario/ssos_eclss_loop/scenario.yaml`](/Users/naoya/develop/Singulab/hakkason2nd/engineering_agents/src/scenario/ssos_eclss_loop/scenario.yaml): explicitly set `T_ref`, equal resource weights, B/C normalization, D latency/payload bounds, D/E internal weights, and physics gate tolerances.
- Extend `raw_topics.plant_sim` in [`src/environment/ssos/eclss/plant_sim/backend.py`](/Users/naoya/develop/Singulab/hakkason2nd/engineering_agents/src/environment/ssos/eclss/plant_sim/backend.py) with existing cumulative ledgers so mass balance can be recomputed from artifacts per run. Do not put the physics model or scoring thresholds in the environment layer.
- Call the evaluator after run completion in [`src/scenario/ssos_eclss_loop/scenario_run.py`](/Users/naoya/develop/Singulab/hakkason2nd/engineering_agents/src/scenario/ssos_eclss_loop/scenario_run.py) to produce `evaluation.json`. Add only `evaluation_path/status/score/max_score/physics_gate_passed` to `summary.json`; keep canonical detail separate.
- Update [`docs/ja/api-contracts.md`](/Users/naoya/develop/Singulab/hakkason2nd/engineering_agents/docs/ja/api-contracts.md) and [`docs/en/api-contracts.md`](/Users/naoya/develop/Singulab/hakkason2nd/engineering_agents/docs/en/api-contracts.md) with new artifacts, applicability, censoring, and canonical row rules; sync [`docs/ja/evaluation-scorecard-a3.html`](/Users/naoya/develop/Singulab/hakkason2nd/engineering_agents/docs/ja/evaluation-scorecard-a3.html) and [`docs/en/evaluation-scorecard-a3.html`](/Users/naoya/develop/Singulab/hakkason2nd/engineering_agents/docs/en/evaluation-scorecard-a3.html) to implementation field names and formulas.

## Verification
- Add [`tests/scenario/test_ssos_eclss_loop_evaluation.py`](/Users/naoya/develop/Singulab/hakkason2nd/engineering_agents/tests/scenario/test_ssos_eclss_loop_evaluation.py): unit-test each formula, post_ops deduplication, TCL observed/right-censored, actor none 80-point max, physics gate failure, at-fault values, and D/E target selection.
- In plant_sim integration tests, confirm `evaluation.json` / `summary.json` index alignment, ledger output, and evaluation references after provenance export.
- Run `python3 -m pytest --ignore=tests/e2e`; when possible, run the AGENTS.md mock 2-run smoke to regression-check the design→verification loop.
