# 同種エージェントチーム再設計プラン

> 実装トラッキング用。Cursor plan と同期する。
>
> **ssos_eclss_loop の後続（実装済み）:** シミュレーション内 actor は事後設計を出さない。別チームの designer が担当する。[post_run_design_agent.md](../ssos_eclss_loop/post_run_design_agent.md)。このメモは共通の同種チームパターン（および単一チームのままの scrubber）を記述する。

## ステータス

| ID | タスク | 状態 |
| --- | --- | --- |
| mode-rename | `labeled_llm` → `llm` 改名 | **done** |
| team-config | `load_team` / `agents.yaml` 新スキーマ、`main_role` 廃止 | **done** |
| situation-split | Telemetry / World state 分離、policy は llm から完全排除 | **done** |
| llm-flow | 1ラウンド + rotating action rep | **done** |
| labeled-rules | policy 駆動ルール、`engineer_*` attribution | **done** |
| post-run-rep | design rep、llm 事後 policy 非含有 | **done** |
| tests-docs | テスト・ドキュメント追随 | **done** |

## 背景と方針

**問題**: 固定4ロール（monitor / diagnostician / operator / design_engineer）が議論と行動を型にはめ込み、同調・hold 収束を助長。

**実装内容**

- 異種4ロール → **同一ペルソナの N 体**（デフォルト N=4、`engineer_1` .. `engineer_N`）
- **議論**: **1ラウンドのみ**（Round2 / react 廃止）
- **ランタイム recovery**: 代表 `engineer_{(step-1) % N}` が action
- **事後 Design**: 最終 step の代表が提案
- **main_role 廃止**
- **モード名**: `labeled_llm` → **`llm`**
- **policy 完全分離**: `llm` では `self.policy` を読まない・プロンプトに埋め込まない

## エージェントモード

| `agents.mode` | 意味 | チーム構成 |
| --- | --- | --- |
| `none` | 物理のみ | エージェントなし |
| `labeled_rule_base` | ルールベース（`policy`） | 同種 N 体 |
| `llm` | LLM（Ollama） | 同種 N 体、N+1 LLM/step |

## policy 分離（固定ルール）

- `build_llm_situation(obs)` / `build_llm_post_run_situation(...)` — policy 引数なし
- 事後 design の policy ゲートは **labeled_rule_base 専用**；`llm` はゲートなしで常に LLM 呼び出し

## 実装ログ

### Step 1: mode-rename ✅

- `runner.py`, `scenario_run.py`, `scenario.yaml`: `labeled_llm` → `llm`, `run_id_llm`
- 後方互換エイリアスなし

### Step 2: team-config ✅

- `Persona`: `agent_id` + `persona` のみ（`main_role` 削除）
- `load_team` / `TeamConfig` / `build_personas`
- `agents.yaml`: `team` + `policy` スキーマ
- `DeliberationPhase`: `deliberation` | `action` | `post_run_proposal`（REACT 廃止）

### Step 3: situation-split ✅

- `build_llm_situation`: `### Telemetry` + `### World state`
- `_situation_context`（Rule thresholds 注入）廃止
- `TEAM_CHARTER` 更新

### Step 4: llm-flow ✅

- 全 N 体 deliberation → action rep 1 体
- Round2 削除

### Step 5: labeled-rules ✅

- `policy.co2_recovery_ppm` 中心のルールエンジン
- `from_role`: `engineer_*`、recovery は action rep

### Step 6: post-run-rep ✅

- design rep = `action_rep_id(steps)`
- llm 事後 Situation に policy 由来フィールドなし

### Step 7: tests-docs ✅

- 31 tests passing
- README, architecture, api-contracts, scenario-scrubber-degradation 更新

## 振り返り

- **policy 分離**を `llm_mode` 分岐で `self.policy = {}` とすることでコードレベルでも固定できた
- **labeled_rule_base 回帰**は `co2_recovery_ppm` 単一閾値で維持（旧 monitor 900ppm アラートは統合）
- **テスト**: `HealthStatus.value` は小文字（`warning`）— World state 表記に注意
