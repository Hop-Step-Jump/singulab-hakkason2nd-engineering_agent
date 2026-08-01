# API 契約 — シミュレータ境界とイベントログ

プロトコルや JSONL 形式を変更したら **本ドキュメントを同時に更新**する。

本リポジトリは **独立した二系統** を持つ。バックエンド・テレメトリ・ランタイムコマンド・事後提案のスキーマは**共有しない**（ファイル名だけ同じ）。

| | `scrubber_degradation` | `ssos_eclss_loop` |
| --- | --- | --- |
| 叙事 | [scenario-scrubber-degradation.md](scenario-scrubber-degradation.md) | [scenario-ssos-eclss-loop.md](scenario-ssos-eclss-loop.md) |
| バックエンド | `SimulatorProtocol` | `EclssBackend` |
| チーム | `ScrubberDegradationTeam` | `SsosEclssLoopTeam` |
| テレメトリ | CO₂ ppm、電力マージン | CO₂/O₂/水ストレージ（kg / L） |
| ランタイム | `RecoveryCommand` | `EclssOperationalCommand` |
| イベント | `recovery_applied` | `operational_applied` |
| 事後提案 | scrubber トポロジ（`add_edge` 等） | `design_domain: ssos_graph` |
| provenance | `record_type: recovery` | `record_type: operational` |

---

## 共通

### 出力ディレクトリ

`src/experiments/results/<run_id>/` — `summary.json` の `scenario` でどちらの系統か判別する。

両系統で出るファイル名:

| ファイル | 役割 |
| --- | --- |
| `telemetry.jsonl` | 毎 step のテレメトリ（**スキーマは系統ごとに異なる**） |
| `health_metrics.jsonl` | 毎 step のヘルス区分（**閾値定義も系統ごとに異なる**） |
| `messages.jsonl` | エージェント発言（`message_type` が系統で異なる） |
| `events.jsonl` | ランタイムイベント（`kind` が系統で異なる） |
| `design_state.jsonl` | 各 step 開始時点の設計スナップショット |
| `design_proposals.json` | ラン終了後の恒久提案（**change_kind が系統で異なる**） |
| `summary.json` | 実行サマリ |
| `provenance.jsonl` | One Piece 互換来歴（[one-piece-integration.md](one-piece-integration.md)） |

### design_proposals.json — 共通フィールド

どちらの系統もラン終了後に 1 ファイル。ランタイム中はシミュレータ／SSOS グラフを**変更しない**。

| フィールド | 説明 |
| --- | --- |
| `proposed_by` | 最終 step の action 代表 ID |
| `decision_source` | `rule` または `llm` |
| `message` / `reasoning` | 提案の説明 |
| `changes` | 恒久変更のリスト（各要素に `change_kind` + `payload`） |
| `parse_notes` | LLM パース時の警告（任意） |

`summary.json` の `design_proposals_path`、`design_proposal_count` と対応。

### messages.jsonl — 共通と系統差

| フィールド | 説明 |
| --- | --- |
| `step` | step 番号 |
| `from_role` / `to_role` | 発言者・宛先 |
| `message` / `reasoning` | 本文・根拠 |
| `decision_source` | `rule` / `llm` / `llm_parse_fail` 等 |
| `deliberation_phase` | `deliberation` / `action` / `post_run_proposal`（llm） |

| `message_type` | scrubber | ssos |
| --- | --- | --- |
| `alert` | ✓ 閾値超過 | — |
| `diagnosis` | ✓ 異常フラグ | — |
| `recovery_command` | ✓ 回復判断 | — |
| `operational_command` | — | ✓ 運用判断 |
| `comment` | ✓ deliberation | ✓ deliberation |
| `skip` | ✓ パース失敗等 | ✓ パース失敗等 |

代表 ID: scrubber は `engineer_*`、ssos は `eclss_operator_*`。Persona 全文や `policy` 値はログに含めない。

### provenance.jsonl — 概要

`src/integrations/one_piece/client.py` が run 終了時に生成。スキーマ: `src/integrations/one_piece/ssot_schema.json`。

| `record_type` | 系統 | ソースイベント |
| --- | --- | --- |
| `recovery` | scrubber | `/eclss/events/recovery_applied`（`request_eps_boost`） |
| `operational` | ssos | `/eclss/events/operational_applied` |

事後 `design_proposals.json` → provenance は**未エクスポート**（両系統共通の開発予定）。

---

## scrubber_degradation

Python モック（`StationSimulator`）上の CO₂ スクラバー異常シナリオ。凍結済み。

### SimulatorProtocol

| クラス | 用途 |
| --- | --- |
| `StationSimulator` | **デフォルト** — ECLSS + EPS |
| `MockEclssSimulator` | プラントのみ（単体テスト） |

| メソッド | 戻り値 | 説明 |
| --- | --- | --- |
| `step()` | `TelemetrySnapshot` | プラントを 1 ティック進める |
| `apply_command(cmd)` | `CommandResult` | 一時的な回復アクション |
| `get_topology()` | `TopologyGraph` | ノード/エッジ |
| `get_design_parameters()` | `dict[str, float]` | 可変パラメータ |
| `get_design_state()` | `DesignState` | トポロジ + パラメータ |
| `inject_anomaly(spec)` | `None` | 異常スケジュール |

### TelemetrySnapshot — `telemetry.jsonl`

```json
{
  "step": 20,
  "co2_ppm": 1240.5,
  "scrubber_efficiency": 0.72,
  "power_margin_w": 45.0,
  "fan_speed": 0.7,
  "bypass_enabled": false,
  "load_reduced": false,
  "eps_support_w": 120.0,
  "eps_support_steps_remaining": 4,
  "anomaly_flags": ["scrubber_degradation"]
}
```

| フィールド | 説明 |
| --- | --- |
| `co2_ppm` | 居住空間 CO₂ 濃度 |
| `scrubber_efficiency` | 有効除去効率 |
| `power_margin_w` | ECLSS ネット電力マージン |
| `eps_support_w` | EPS 一時支援ワット |
| `anomaly_flags` | 有効な異常名 |

運用コマンドがあった step では、`"post_ops": true` 付きの 2 行目が追記されうる（L5、`ssos_eclss_loop` と同規約）。ダッシュボード等の読取側は `post_ops`／同 step の最終行を優先し、`summary.json` と揃える。

### RecoveryCommand — ランタイム

`apply_command()` で適用される一時操作。

```json
{
  "kind": "set_fan_speed",
  "value": 1.0,
  "issued_by": "engineer_2"
}
```

| `kind` | `value` 型 | 説明 |
| --- | --- | --- |
| `set_fan_speed` | float 0–1 | ファン速度 |
| `enable_bypass` | bool | 一時バイパス |
| `reduce_load` | bool | 代謝負荷削減 |
| `request_eps_boost` | float W (0, 500] | EPS 放電支援 |

### ヘルス — `health_metrics.jsonl`

`compute_health_metrics()` — `src/environment/scrubber/eclss_ops/telemetry.py`

```json
{"step": 5, "co2_status": "safe", "power_status": "safe", "overall": "safe"}
```

ops 後に health を更新する場合、scrubber `telemetry.jsonl` と同様に `"post_ops": true` の重複行がありうる。

| 指標 | safe | warning | critical |
| --- | --- | --- | --- |
| CO₂ (ppm) | < 800 | 800 〜 1200 未満 | ≥ 1200 |
| 電力マージン (W) | > 0 | 0 〜 −150 未満 | ≤ −150 |

`policy.co2_recovery_ppm`（デフォルト 1000）等は**回復トリガー**であり、上表のヘルス区分とは別。

### design_proposals.json — scrubber ドメイン

| `change_kind` | 用途 |
| --- | --- |
| `add_edge` | 新規エッジ（flow / bypass / power） |
| `add_node` | 新規ノード |
| `set_parameter` | 設計パラメータ |

```json
{
  "proposed_by": "engineer_2",
  "decision_source": "rule",
  "message": "Propose permanent bypass plumbing between manifold and scrubber.",
  "changes": [
    {
      "change_kind": "add_edge",
      "payload": {"node_a": "manifold", "node_b": "scrubber", "kind": "bypass"}
    }
  ],
  "baseline_topology": {
    "nodes": [{"id": "cabin", "name": "Cabin", "kind": "volume"}],
    "edges": [{"source": "manifold", "target": "scrubber", "kind": "flow"}]
  }
}
```

### エージェントモード

| `agents.mode` | チーム | ランタイム | 事後提案 |
| --- | --- | --- | --- |
| `none` | — | シミュのみ | — |
| `labeled_rule_base` | `ScrubberDegradationTeam` | `policy` 駆動回復 | rule |
| `llm` | 同上 | LLM `commands` | llm |

#### messages.jsonl 例

```json
{
  "step": 33,
  "from_role": "engineer_2",
  "to_role": "team",
  "message": "CO2 at 1016 ppm exceeds recovery band 1000 ppm.",
  "message_type": "alert",
  "decision_source": "rule"
}
```

```json
{
  "step": 17,
  "from_role": "engineer_1",
  "message": "EPS boost critical for CO2 reduction.",
  "message_type": "recovery_command",
  "decision_source": "llm",
  "deliberation_phase": "action"
}
```

### events.jsonl

```json
{"step": 20, "kind": "/eclss/events/anomaly", "flags": ["scrubber_degradation"]}
{"step": 33, "kind": "/eclss/events/recovery_applied", "command": {"kind": "set_fan_speed", "value": 1.0, "issued_by": "engineer_2"}, "message": "fan_speed set to 1.0"}
```

`/eclss/events/design_change` はランタイムに発生しない（事後提案は `design_proposals.json`）。

### design_state.jsonl

毎 step、エージェント行動**前**。ランタイム中トポロジは不変。

```json
{
  "step": 36,
  "topology": {
    "nodes": [{"id": "cabin", "name": "Cabin", "kind": "volume"}],
    "edges": [{"source": "manifold", "target": "scrubber", "kind": "flow"}]
  },
  "parameters": {"scrubber_base_efficiency": 0.95}
}
```

### eps_telemetry.jsonl

`StationSimulator` 実行時のみ。

```json
{
  "step": 22,
  "solar_voltage_v": 113.14,
  "bcdu_mode": "discharging",
  "support_w": 120.0,
  "support_steps_remaining": 3
}
```

同一 step で回復コマンド後に EPS を更新する場合、`"post_ops": true` 付き行が追記されうる。

### summary.json

```json
{
  "scenario": "scrubber_degradation",
  "simulator": "mock_station",
  "agents_mode": "labeled_rule_base",
  "steps": 50,
  "peak_co2_ppm": 1016.34,
  "final_co2_ppm": 967.2,
  "final_power_margin_w": -42.5,
  "eps_boost_applied_step": 28,
  "final_health": {"co2_status": "safe", "power_status": "warning", "overall": "warning"},
  "design_proposal_count": 1,
  "provenance_record_count": 2,
  "archetypes": {
    "engineer_1": "first_principles",
    "engineer_2": "failure_mode",
    "engineer_3": "improviser",
    "engineer_4": "systems_integrator"
  }
}
```

| フィールド | 説明 |
| --- | --- |
| `archetypes` | `agents.yaml` の `team.archetypes` から割り当てた `agent_id` → レンズ名。省略または `[]` のとき `{}`。scrubber で記録（`labeled_rule_base` でも）。ssos はデフォルト未使用 |

### ROS2 風トピック（Mock 契約）

`environment/ssos/topics.py` — `StationSimulator` / モックアダプタ用。**ssos 実 ECLSS とは別名前空間**。

| トピック | 方向 | ペイロード |
| --- | --- | --- |
| `/eclss/telemetry/co2_ppm` | pub | float |
| `/eclss/command/set_fan_speed` | sub | float 0–1 |
| `/eclss/command/request_eps_boost` | sub | float W |
| `/eclss/events/recovery_applied` | event | コマンド適用結果 |
| `/eclss/events/anomaly` | event | 異常フラグ |

### EPS トピック（scrubber 電力）

`environment/ssos/eps_topics.py` — `MockSarj` / `MockBcdu` および `Ros2EpsBridge`（Phase 3）。

| トピック | 方向 | ペイロード |
| --- | --- | --- |
| `/solar/voltage` | pub | float V |
| `/bcdu/operation` | sub | `{support_w, duration_steps}` |
| `/bcdu/status` | pub | `BcduStatus` |

### provenance — 回復レコード

```json
{
  "record_type": "recovery",
  "scenario": "scrubber_degradation",
  "change_kind": "request_eps_boost",
  "actor": "engineer_3",
  "payload": {"support_w": 120.0, "eps": {"bcdu_mode": "discharging"}},
  "trace": {"event_kind": "/eclss/events/recovery_applied", "decision_source": "rule"}
}
```

### 実行例

```bash
python src/scripts/run_mock_eclss.py
python -c "from scenario.runner import run_scenario; run_scenario('scrubber_degradation', overrides={'agents': {'mode': 'labeled_rule_base'}})"
python -c "from scenario.runner import run_scenario; run_scenario('scrubber_degradation', overrides={'agents': {'mode': 'llm'}})"
```

---

## ssos_eclss_loop

SSOS Docker 内の実 ROS2 ECLSS（または `LoopMockEclssBackend`）を操作するシナリオ。`SimulatorProtocol` は使わない。

### EclssBackend

`build_eclss_backend()` — `src/scenario/ssos_eclss_loop/scenario_run.py`

| クラス | 用途 |
| --- | --- |
| `LoopMockEclssBackend` | ホスト dev / pytest（簡易ストレージ動態） |
| `Ros2EclssBridge` | SSOS Docker 内 `ros2` CLI ブリッジ |

backend 選択: `scenario.yaml` の `backend.kind`、環境変数 `SSOS_ECLSS_BACKEND`、CLI `--backend mock|ros2`（または `ea run … --backend mock`）。

| メソッド | 説明 |
| --- | --- |
| `poll_telemetry()` | `/co2_storage` 等を読み取り |
| `send_air_revitalisation_goal(goal)` | ARS Action |
| `send_oxygen_generation_goal(goal)` | OGS Action |
| `send_water_recovery_goal(goal)` | WRS Action |
| `request_co2(amount)` / `request_o2(amount)` | Service |
| `request_product_water(liters)` | Service |
| `set_subsystem_failure(name, enabled)` | 故障注入 |

実装: `environment/ssos/eclss/backend.py`、`eclss/ros2/bridge.py`、`eclss/ros2/graph_rewire.py`（client remap）。

### EclssTelemetrySnapshot — `telemetry.jsonl`

```json
{
  "step": 3,
  "co2_storage_kg": 1680.0,
  "o2_storage_kg": 465.0,
  "product_water_reserve_l": 100.0,
  "ars_failure_enabled": false
}
```

| フィールド | ROS2 トピック |
| --- | --- |
| `co2_storage_kg` | `/co2_storage` |
| `o2_storage_kg` | `/o2_storage` |
| `product_water_reserve_l` | `/wrs/product_water_reserve` |

運用コマンドがあった step では、`"post_ops": true` 付きの 2 行目が追記されうる（L5）。ダッシュボード等の読取側は `post_ops`／同 step の最終行を優先し、`summary.json` と揃える。

### EclssOperationalCommand — ランタイム

`SsosEclssLoopTeam.apply_outcome()` → `EclssBackend`

```json
{
  "kind": "air_revitalisation",
  "payload": {"initial_co2_mass": 1800.0, "initial_moisture_content": 25.0},
  "issued_by": "eclss_operator_1"
}
```

| `kind` | バックエンド |
| --- | --- |
| `air_revitalisation` | `send_air_revitalisation_goal()` |
| `oxygen_generation` | `send_oxygen_generation_goal()` |
| `water_recovery_systems` | `send_water_recovery_goal()` |
| `request_co2` | `request_co2(amount)` |
| `request_o2` | `request_o2(amount)` |

### ヘルス — `health_metrics.jsonl`

`compute_eclss_storage_health()` — `src/scenario/ssos_eclss_loop/health.py`  
閾値は `scenario.yaml` の `thresholds`。

```json
{"step": 3, "co2_status": "warning", "o2_status": "safe", "water_status": "safe", "overall": "warning"}
```

ops 後に health を更新する場合、`telemetry.jsonl` と同様に `"post_ops": true` の重複行がありうる。

| 指標 | safe | warning | critical |
| --- | --- | --- | --- |
| CO₂ ストレージ (kg) | < 1500（high） | 1500 〜 2200 未満 | ≥ 2200 |
| O₂ ストレージ (kg) | > 450（low） | 337.5 〜 450 | ≤ 337.5 |
| 製品水 (L) | > 50（low） | 25 〜 50 | ≤ 25 |

`thresholds.co2_storage_high_kg` 等は**運用トリガー**。ヘルス区分とは別概念。

### design_proposals.json — `design_domain: ssos_graph`

| `change_kind` | 用途 |
| --- | --- |
| `action_profile` | Action goal フィールド（ARS / OGS / WRS） |
| `service_config` | Service 呼び出し量・順序 |
| `set_parameter` | 閾値・policy パラメータ |
| `graph_rewire` | 次 run の client `topic_remap`（Phase 7）。launch remap は [BL-003](memo/backlog.md#bl-003) |

`--apply-proposals` で `scenario.yaml` / `ssos_graph.rewires` にマージ。実装: `scenario/ssos_eclss_loop/design_proposals.py`。

```json
{
  "design_domain": "ssos_graph",
  "proposed_by": "eclss_operator_2",
  "decision_source": "rule",
  "changes": [
    {
      "change_kind": "action_profile",
      "payload": {
        "action": "air_revitalisation",
        "fields": {"initial_co2_mass": 2000.0}
      }
    }
  ],
  "baseline_graph": {"rewires": []}
}
```

### エージェントモード

| `agents.mode` | チーム | ランタイム | 事後提案 |
| --- | --- | --- | --- |
| `none` | — | `poll_telemetry` のみ | — |
| `labeled_rule_base` | `SsosEclssLoopTeam` | ストレージ閾値 → ARS/OGS | `ssos_graph`（rule） |
| `llm` | 同上 | deliberation + operational | `ssos_graph`（llm） |

#### messages.jsonl 例

```json
{
  "step": 2,
  "from_role": "eclss_operator_1",
  "message": "Starting ARS air_revitalisation to vent CO2 from storage.",
  "message_type": "operational_command",
  "decision_source": "rule"
}
```

### events.jsonl

```json
{
  "step": 2,
  "kind": "/eclss/events/operational_applied",
  "command": {"kind": "air_revitalisation", "issued_by": "eclss_operator_1", "payload": {"initial_co2_mass": 1800.0}},
  "result": {"success": true},
  "message": "ARS goal dispatched"
}
```

失敗時は `/eclss/events/operational_rejected`。

### design_state.jsonl

毎 step、エージェント行動**前**。`ssos_graph`（`rewires` 含む）のスナップショット。

```json
{
  "step": 1,
  "ssos_graph": {
    "rewires": [{"public": "/co2_storage", "backend": "/co2_storage"}]
  }
}
```

### summary.json

```json
{
  "scenario": "ssos_eclss_loop",
  "backend": "ros2",
  "agents_mode": "labeled_rule_base",
  "steps": 8,
  "peak_co2_storage_kg": 1680.0,
  "final_co2_storage_kg": 1330.0,
  "final_o2_storage_kg": 465.0,
  "operational_command_count": 3,
  "ogs_invoked_step": 2,
  "final_health": {"co2_status": "safe", "o2_status": "warning", "overall": "warning"},
  "agent_ids": ["eclss_operator_1", "eclss_operator_2", "eclss_operator_3"],
  "provenance_record_count": 3
}
```

**scrubber に無いフィールド**: `backend`、`peak_co2_storage_kg`、`operational_command_count` 等。  
**ssos に無いフィールド**: `co2_ppm`、`eps_boost_applied_step`、`eps_telemetry.jsonl` 全体。

### ROS2 トピック（SSOS 実 ECLSS）

`environment/ssos/eclss_topics.py` — `Ros2EclssBridge` が使用。**scrubber の `/eclss/telemetry/co2_ppm` とは別**。

| 種別 | 名前 |
| --- | --- |
| Action | `air_revitalisation`, `oxygen_generation`, `water_recovery_systems` |
| Service | `/ars/request_co2`, `/ogs/request_o2`, `/wrs/product_water_request` |
| Topic | `/co2_storage`, `/o2_storage`, `/wrs/product_water_reserve` |

`Ros2EclssBridge(topic_remap=...)` — `graph_rewire` 提案を client 側でトピック名置換（Phase 7）。

### provenance — 運用レコード

```json
{
  "record_type": "operational",
  "scenario": "ssos_eclss_loop",
  "change_kind": "air_revitalisation",
  "actor": "eclss_operator_1",
  "payload": {"initial_co2_mass": 1800.0},
  "trace": {"event_kind": "/eclss/events/operational_applied", "result_success": true}
}
```

### 実行例

```bash
# mock（ホスト）
python -m scenario.ssos_eclss_loop.scenario_run --backend mock --agents-mode labeled_rule_base

# ros2（SSOS Docker）
./scripts/run_ssos_eclss_loop.sh --agents-mode labeled_rule_base

# graph_rewire E2E
./scripts/run_graph_rewire_e2e.sh
```

---

## 関連ドキュメント

- [architecture.md](architecture.md) — レイヤと実行フロー
- [one-piece-integration.md](one-piece-integration.md) — provenance 詳細
- [development-plan.md](development-plan.md) — 未完了項目
