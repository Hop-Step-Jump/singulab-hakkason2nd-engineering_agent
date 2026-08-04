# シナリオ: ssos_eclss_loop

**SSOS**（Space Station OS）Docker 内の実 ROS2 **ECLSS**（Environmental Control and Life Support System）を、エージェントチームが Crew Simulation の代わりに操作する参照シナリオ。CO₂ / O₂ / 製品水の**ストレージ kg** を監視し、閾値超過時に ARS / OGS 等の運用コマンドを打ち、ラン終了後に `ssos_graph` ドメインの恒久設計を提案する。

> 実行コマンドは [概要](overview.md#実行方法) および本ドキュメント [実行方法](#実行方法)。アーキテクチャは [architecture.md](architecture.md)。scrubber との対比は [scenario-scrubber-degradation.md](scenario-scrubber-degradation.md)。

---

## scrubber_degradation との違い

| 観点 | scrubber_degradation | ssos_eclss_loop |
| --- | --- | --- |
| バックエンド | `StationSimulator`（Python モック） | `EclssBackend`（`LoopMockEclssBackend` / `Ros2EclssBridge`） |
| テレメトリ | CO₂ ppm、スクラバー効率、電力マージン | `/co2_storage`、`/o2_storage`、`/wrs/product_water_reserve`（kg / L） |
| ランタイム操作 | 回復コマンド（ファン、EPS ブースト等） | 運用コマンド（ARS Action、OGS Action、CO₂ Service 等） |
| 事後提案 | scrubber トポロジ（`add_edge` 等） | `design_domain: ssos_graph`（`action_profile`、`graph_rewire` 等） |
| 実行環境 | ホスト Python のみ | mock はホスト可。**ros2** は SSOS Docker + ECLSS headless |
| 状態 | Mock 凍結 | Phase 0–7 完了（launch remap は Phase 8 バックログ） |

---

## 背景と目的

SSOS の ECLSS は、閉鎖環境の **CO₂ 除去（ARS）**、**O₂ 生成（OGS / Sabatier）**、**水回収（WRS）** を ROS2 Action / Service で操作する。従来は Crew Simulation がこれらを起動していたが、本シナリオでは **同種エンジニア N 体のエージェントチーム** が同じインターフェースを `EclssBackend` 経由で呼び出す。

本シナリオが答える問い:

1. ストレージ閾値を超えたとき、ルールベースチームは ARS / OGS を正しい順序で起動できるか
2. LLM チームは Sabatier 用 CO₂ 要求や OGS タイミングをどう判断するか
3. 運用ログ（`operational_applied`）と provenance が One Piece モデルと整合するか
4. ラン終了後、`action_profile` / `graph_rewire` 等の恒久提案を次 run に `--apply-proposals` で反映できるか

**ランタイム中は SSOS グラフを変えない**。運用コマンドと事後 `design_proposals.json` を分離している（scrubber と同じ設計原則）。

---

## SSOS ECLSS サブシステム

```text
  [居住・代謝] ──CO₂──► /co2_storage ──► ARS (air_revitalisation)
                                              │
  /o2_storage ◄── OGS (oxygen_generation) ◄──┘  Sabatier（CO₂ feedstock）
       │
       └── request_o2 / request_co2 (Service)

  /wrs/product_water_reserve ◄── WRS (water_recovery_systems)  ※ ros2 ブリッジ実装済み
```

| 略称 | フルネーム | 本シナリオでの役割 |
| --- | --- | --- |
| **ARS** | Air Revitalisation System | CO₂ ストレージからの除去（`air_revitalisation` Action） |
| **OGS** | Oxygen Generation System | O₂ 生成（`oxygen_generation` Action）。Sabatier には CO₂ feedstock が必要 |
| **WRS** | Water Recovery System | 水回収（`water_recovery_systems` Action）— チーム運用はバックログ（BL-004） |

### ROS2 インターフェース（主要）

| 種別 | 名前 | 用途 |
| --- | --- | --- |
| Action | `air_revitalisation` | ARS サイクル起動 |
| Action | `oxygen_generation` | OGS サイクル起動 |
| Action | `water_recovery_systems` | WRS サイクル起動 |
| Service | `/ars/request_co2` | Sabatier 用 CO₂ 供給 |
| Service | `/ogs/request_o2` | O₂ 引き出し |
| Topic | `/co2_storage` | CO₂ 貯蔵量（kg） |
| Topic | `/o2_storage` | O₂ 貯蔵量（kg） |
| Topic | `/wrs/product_water_reserve` | 製品水（L） |

型定数: `src/environment/ssos/eclss/ros2/topics.py`。ブリッジ: `src/environment/ssos/eclss/ros2/bridge.py`。

---

## 叙事（時系列）

### エージェントなし（`agents.mode: none`）

| フェーズ | 内容 |
| --- | --- |
| 各 step | `poll_telemetry()` のみ。運用コマンドなし |
| mock | 毎 step CO₂ が `co2_growth_kg_per_step` だけ増加（デフォルト +0.06 kg/step） |
| ros2 | SSOS 実プラントの自然動態（Crew Simulation なしで放置） |
| 事後 | `design_proposals.json` なし |

ベースライン run は「エージェントが介入しないとストレージがどう推移するか」の参照。

### labeled_rule_base

`scenario.yaml` の `thresholds` が**ストレージ閾値**、`agents.yaml` の `policy` が**運用プロファイル**（goal フィールド、CO₂ 先行要求の有無）。

| 条件（目安） | 運用コマンド |
| --- | --- |
| CO₂ ≥ `co2_storage_high_kg`（デフォルト 1.5 kg） | `air_revitalisation`（ARS） |
| O₂ ≤ `o2_storage_low_kg`（デフォルト 0.45 kg） | `oxygen_generation`（OGS）。`request_co2_before_ogs: true` のときだけ先に `request_co2`（既定は **false**） |

**`request_co2_before_ogs`:** 既定 OFF。実 SSOS では OGS が Sabatier 用に `/ars/request_co2` を内部呼び出しするため。`true` にすると（設計提案含む）、同一 step で明示 `request_co2` と LoopMock の OGS Sabatier 減算が両方走り、**バッファなしの簡略 mock では CO₂ が二重減算されうる**。

**re-arm**: ARS / OGS を打った後もストレージが改善しなければ、次 step で再試行可能（`co2_at_ars_dispatch` / `o2_at_ogs_dispatch` 境界）。

代表オペレータ `eclss_operator_{(step-1) % N}` がその step のコマンドを発行。事後は代表が `design_proposals.json`（`ssos_graph`）を出力。

### llm

各 step: 全 N 体 deliberation → 代表が `operational_command`（JSON `commands`）→ 事後 1 回で `changes` 提案。`policy` 閾値はプロンプトに含めない（scrubber と同様）。

---

## 設定ファイル

| ファイル | 用途 |
| --- | --- |
| [`scenario.yaml`](https://github.com/hirototamura/engineering_agents/blob/main/src/scenario/ssos_eclss_loop/scenario.yaml) | step 数、初期ストレージ、backend 種別、閾値、`agents.mode`、run ID |
| [`agents.yaml`](https://github.com/hirototamura/engineering_agents/blob/main/src/scenario/ssos_eclss_loop/agents.yaml) | チーム（`eclss_operator_*`）、Persona、`policy`（labeled のみ）、Ollama |

### scenario.yaml（主要項目）

```yaml
simulation:
  steps: 8
  initial_co2_storage_kg: 1.5
  initial_o2_storage_kg: 0.48
  initial_product_water_l: 100.0

backend:
  kind: mock  # mock | ros2 — SSOS_ECLSS_BACKEND 環境変数でも上書き可

mock_dynamics:
  co2_growth_kg_per_step: 0.06
  ars_co2_reduction_kg: 0.35
  ogs_o2_gain_kg: 0.1

thresholds:
  co2_storage_high_kg: 1.5
  co2_storage_critical_kg: 2.2
  o2_storage_low_kg: 0.45
  product_water_low_l: 50.0

agents:
  mode: none  # none | labeled_rule_base | llm

output:
  run_id: ssos_eclss_loop_baseline
  run_id_labeled_rule_base: ssos_eclss_loop_labeled_rule_base
  run_id_llm: ssos_eclss_loop_llm
```

`ssos_graph.rewires`（任意）— 前 run の `graph_rewire` 提案を `--apply-proposals` でマージすると、次 run の `Ros2EclssBridge` に client remap が渡る。

### agents.yaml（主要項目）

```yaml
team:
  count: 3
  id_prefix: eclss_operator

policy:   # labeled_rule_base のみ。閾値は scenario.yaml から実行時マージ
  request_co2_before_ogs: false
  request_co2_amount: 0.025
  ars_goal:
    initial_co2_mass: 1.8
  ogs_goal:
    input_water_mass: 0.015

llm:
  base_url: http://localhost:11434   # Docker: host.docker.internal（ea-loop が設定）
  model: gemma4:e4b
```

---

## シミュレーション世界

### ヘルス閾値（ストレージ）

`health_metrics.jsonl` — `compute_eclss_storage_health()`（`src/scenario/ssos_eclss_loop/health.py`）:

| 指標 | safe | warning | critical |
| --- | --- | --- | --- |
| CO₂ ストレージ (kg) | < high（1.5） | high 〜 critical 未満 | ≥ critical（2.2） |
| O₂ ストレージ (kg) | > low（0.45） | low×0.75 〜 low | ≤ low×0.75（0.3375） |
| 製品水 (L) | > low（50） | low×0.5 〜 low | ≤ low×0.5（25） |
| `overall` | 全 safe | より悪い方 | より悪い方 |

エージェントの運用トリガー（`co2_storage_high_kg` 等）は `scenario.yaml` の `thresholds`。ヘルス区分はテレメトリから独立に記録される。

### 運用コマンド（ランタイム）

| `kind` | バックエンド呼び出し | 効果（要約） |
| --- | --- | --- |
| `air_revitalisation` | `send_air_revitalisation_goal()` | ARS サイクル — CO₂ 除去 |
| `oxygen_generation` | `send_oxygen_generation_goal()` | OGS サイクル — O₂ 生成 |
| `water_recovery_systems` | `send_water_recovery_goal()` | WRS サイクル（ros2 のみ；mock は未実装） |
| `request_co2` | `request_co2(amount)` | Sabatier feedstock 供給 |
| `request_o2` | `request_o2(amount)` | O₂ 引き出し |

いずれも **恒久グラフ変更ではない**。`events.jsonl` では `/eclss/events/operational_applied` として記録。

### graph_rewire（client remap — Phase 7）

`design_proposals.json` の `graph_rewire` または `scenario.yaml` の `ssos_graph.rewires` は、**次 run** の `Ros2EclssBridge` が `ros2 topic echo` 等で使うトピック名をクライアント側で置換する（`environment/ssos/eclss/ros2/graph_rewire.py`）。

ROS launch ファイル側の remap（Phase 8）は [backlog BL-003](memo/backlog.md#bl-003)。

---

## エージェントチーム設計

### 同種 N 体 + 代表 action

| 概念 | ssos_eclss_loop |
| --- | --- |
| ID | `eclss_operator_1` … `eclss_operator_N`（デフォルト 3） |
| deliberation | llm: 全員 1 ラウンド。labeled: 運用判断メッセージ |
| action rep | `eclss_operator_{(step-1) % N}` |
| post-run rep | 最終 step の代表が `design_proposals.json`（`changes` 非空のときのみ） |

`SsosEclssLoopTeam` は `Team` ABC を継承。`run_step(backend, obs)` / `apply_outcome(backend, outcome)` シグネチャ。

### labeled_rule_base vs llm

| | labeled_rule_base | llm |
| --- | --- | --- |
| 判断 | `thresholds` + `policy` プロファイル | Persona + ストレージテレメトリ + 議論 |
| 再現性 | 高い | モデル依存 |
| 事後提案 | ルールベース `ssos_graph`（書くときは非空。L8 で goal/閾値フォールバック） | LLM が `changes` 生成（空ならファイルなし） |
| provenance | `operational_applied` → `record_type: operational` | 同上 |

---

## 実行方法 { #実行方法 }

### mock（ホスト、ROS2 不要）

```bash
python -m scenario.ssos_eclss_loop.scenario_run --backend mock --agents-mode labeled_rule_base
python -m scenario.ssos_eclss_loop.scenario_run --backend mock --agents-mode llm
```

### ros2（SSOS Docker）

```bash
# Terminal 1: SSOS コンテナで ECLSS headless
~/dev/ssos/ssos-run.sh
# コンテナ内: bash /root/ssos-eclss-headless.sh

# Terminal 2: ホスト repo ルート
./scripts/run_ssos_eclss_loop.sh --agents-mode labeled_rule_base
./scripts/run_ssos_eclss_loop.sh --agents-mode llm
```

コンテナ内直接: `ea-loop --agents-mode labeled_rule_base`（`OLLAMA_BASE_URL=host.docker.internal` 既定）。

### 前 run の設計提案を次 run に適用

```bash
python -m scenario.ssos_eclss_loop.scenario_run --backend mock --agents-mode llm \
  --apply-proposals src/experiments/results/ssos_eclss_loop_llm/design_proposals.json
```

### graph_rewire E2E スモーク

```bash
./scripts/run_graph_rewire_e2e.sh   # ECLSS headless 前提
```

---

## 出力の読み方 { #出力の読み方 }

### ファイル一覧

| ファイル | いつ読むか |
| --- | --- |
| `telemetry.jsonl` | CO₂/O₂/水ストレージの時系列（kg / L） |
| `health_metrics.jsonl` | ストレージベースの safe / warning / critical |
| `messages.jsonl` | `operational_command`、deliberation、reasoning |
| `events.jsonl` | `operational_applied` / `operational_rejected` |
| `design_state.jsonl` | 各 step の `ssos_graph` スナップショット（rewires 含む） |
| `design_proposals.json` | 事後の `ssos_graph` 恒久案（`changes` 非空のときのみ書込） |
| `summary.json` | peak CO₂、operational 回数、backend 種別など |
| `provenance.jsonl` | 運用レコード（`record_type: operational`） |

**scrubber 専用で ssos には出ないもの**: `eps_telemetry.jsonl`、ppm ベースの回復イベント。

### telemetry.jsonl（例）

```json
{
  "step": 3,
  "co2_storage_kg": 1.68,
  "o2_storage_kg": 0.465,
  "product_water_reserve_l": 100.0
}
```

### design_proposals.json（ssos_graph）

```json
{
  "design_domain": "ssos_graph",
  "proposed_by": "eclss_operator_2",
  "decision_source": "rule",
  "message": "Raise ARS initial_co2_mass for faster vent cycles.",
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

| `change_kind` | 用途 |
| --- | --- |
| `action_profile` | Action goal フィールドの恒久調整 |
| `service_config` | Service 呼び出し量・順序 |
| `set_parameter` | 閾値・policy パラメータ |
| `graph_rewire` | 次 run の client topic remap マニフェスト |

### summary.json で見る KPI

| フィールド | 意味 |
| --- | --- |
| `backend` | `mock` または `ros2` |
| `peak_co2_storage_kg` | ラン中最大 CO₂ ストレージ |
| `final_co2_storage_kg` / `final_o2_storage_kg` | 最終 step のストレージ |
| `operational_command_count` | 発行した運用コマンド数 |
| `ogs_invoked_step` / `co2_requested_step` | 初回 OGS / request_co2 の step |
| `design_proposal_count` | 事後 change 数 |
| `provenance_record_count` | 運用 provenance 行数 |
| `telemetry_topics_read` | ros2 で読めたトピック名 |

---

## ダッシュボードでの見方 { #ダッシュボードでの見方 }

`summary.scenario == "ssos_eclss_loop"` の run は `src/tools/dashboard/ssos_views.py` に分岐。

1. **Overview** — CO₂ / O₂ / 水ストレージ kg のプロット、ヘルスカード、2 run 比較
2. **Step replay** — `operational_applied` タイムライン、発言・reasoning、ストレージプロット
3. **設計提案** — `ssos_graph` の `action_profile` / `graph_rewire` プレビュー

scrubber 向けスクリーンショット: [概要](overview.md#一目でわかるダッシュボード)。

---

## テスト

| テスト | 内容 |
| --- | --- |
| `test_ssos_eclss_loop_team.py` | `SsosEclssLoopTeam`、labeled / llm、Team 継承 |
| `test_ssos_eclss_loop_scenario.py` | mock シナリオ end-to-end |
| `test_graph_rewire.py` | client remap 単体 |
| `test_graph_rewire_integration.py` | `Ros2EclssBridge` 統合（ROS なしは skip） |

```bash
pytest tests/scenario/test_ssos_eclss_loop*.py -q
pytest tests/environment/test_graph_rewire*.py -q
```

コンテナ E2E 記録: `memo/ssos_eclss_loop/e2e_records/` (repo only)。

---

## 関連ドキュメント

- [architecture.md](architecture.md) — レイヤと ssos 実行フロー
- [api-contracts.md](api-contracts.md) — `EclssBackend`、JSONL、運用コマンド
- [one-piece-integration.md](one-piece-integration.md) — 運用 provenance
- [development-plan.md](development-plan.md) — Phase 0–7 完了、次タスク
- [memo/ssos_eclss_loop/ssos_eclss_loop_connection_plan.md](memo/ssos_eclss_loop/ssos_eclss_loop_connection_plan.md) — 接合プラン詳細・検証手順
- [memo/backlog.md](memo/backlog.md) — BL-003（Phase 8）、BL-004（ECLSS フォローアップ）
