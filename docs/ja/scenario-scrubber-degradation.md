# シナリオ: scrubber_degradation

**ECLSS**（Environmental Control and Life Support System / 環境制御・生命維持システム）レジリエンス・ループ MVP の参照シナリオ。生命維持装置である CO2 スクラバーの性能劣化という単一異常に対し、エージェントチームがどう検知・回復し、事後にどんな恒久設計を提案するかを観察する。

> 実行コマンドは [概要](overview.md#実行方法)。アーキテクチャは [architecture.md](architecture.md)。

---

## 背景と目的

宇宙ステーションの閉鎖環境では、スクラバー（CO2 除去装置）の効率低下が CO2 蓄積につながり、電力系（ファン・EPS 支援）とのトレードオフが発生する。

本シナリオは次の問いに答えるための **最小再現実験** である:

1. 異常注入後、テレメトリはどう悪化するか（ベースライン）
2. ルールベースチームは閾値どおりに回復できるか（再現性の足場）
3. LLM チームは同じ状況で異なるタイミング・発言・提案をするか（比較実験）
4. ラン終了後、どんな恒久設計（バイパス配管、パラメータ変更など）が提案されるか

**ランタイム中はトポロジを変えない**。一時操作（回復コマンド）と恒久提案（`design_proposals.json`）を分離している。

---

## 叙事（時系列）

### エージェントなし（`agents.mode: none`）

| フェーズ | ステップ | 内容 |
| --- | --- | --- |
| 均衡 | 1–19 | CO2 約 800 ppm（ヘルス warning 帯境界）、スクラバー効率 ≈ 0.95 |
| 異常開始 | 20 | `scrubber_degradation` 注入 |
| 悪化 | 20–50 | 効率 −0.02/step、CO2 産生 1.4×、電力マージン −3 W/step |
| ヘルス悪化 | 約 30+ | CO2 が 1200 ppm 超で **critical**（`CO2_WARNING_PPM`） |
| 対応 | — | **なし**（エージェントなし） |

ベースライン run は「異常が放置されるとどうなるか」の参照曲線。

### labeled_rule_base（ルールチーム）

| フェーズ | ステップ（目安） | 内容 |
| --- | --- | --- |
| 均衡 | 1–19 | 同上 |
| 異常 | 20+ | 診断メッセージ、効率低下 |
| ポリシー警戒 | CO2 ≥ 1000 ppm | alert、ファン全開（`co2_recovery_ppm` — **ヘルス閾値とは別**） |
| 電力危機 | 電力マージン ≤ −150 W | 負荷削減、`request_eps_boost`（`power_status: critical`） |
| 追加回復 | CO2 高 + ファン済 | `enable_bypass`（一時） |
| 回復 | 約 40+ | CO2 が warning 帯（1200 ppm）未満へ |
| 事後 | ラン終了後 | bypass **エッジ**の恒久提案（`design_proposals.json`） |

回帰テストでは `final_co2_ppm < CO2_WARNING_PPM`（1200）を期待。

### llm（LLM チーム）

生命維持シミュのフェーズは同じ。回復の**順序・タイミング・発言**はモデル依存。事後提案は LLM が `changes` を生成（例: `set_parameter` でスクラバー効率引き上げ、`add_node` でバイパス弁など）。ダッシュボードで labeled や別モデルと compare する想定。

---

## 設定ファイル

| ファイル | 用途 |
| --- | --- |
| [`scenario.yaml`](https://github.com/hirototamura/engineering_agents/blob/main/src/scenario/scrubber_degradation/scenario.yaml) | ステップ数、初期状態、設計パラメータ、異常、`agents.mode`、run ID |
| [`agents.yaml`](https://github.com/hirototamura/engineering_agents/blob/main/src/scenario/scrubber_degradation/agents.yaml) | チーム、Persona、メモリ、`policy`（labeled のみ）、Ollama / vLLM 設定 |

### scenario.yaml（主要項目）

```yaml
simulation:
  steps: 50
  initial_co2_ppm: 800.0
  initial_power_margin_w: 150.0

anomalies:
  - name: scrubber_degradation
    start_step: 20
    scrubber_efficiency_decay_per_step: 0.02
    power_margin_decay_per_step: 3.0
    co2_production_multiplier: 1.4

agents:
  mode: none  # none | labeled_rule_base | llm

output:
  run_id: scrubber_degradation_baseline
  run_id_labeled_rule_base: scrubber_degradation_labeled_rule_base
  run_id_llm: scrubber_degradation_llm
```

### agents.yaml（主要項目）

```yaml
team:
  count: 4
  id_prefix: engineer
  # 任意: 思考レンズ（round-robin → engineer_1..N）。llm プロンプトのみ影響;
  # labeled は persona 無視。summary.json["archetypes"] には常に記録。
  archetypes: [first_principles, failure_mode, improviser, systems_integrator]
  persona: |
    Closed-habitat ECLSS colleague engineer. ...

policy:          # labeled_rule_base のみ
  co2_recovery_ppm: 1000
  fan_speed: 1.0
  enable_bypass: true
  request_eps_boost_on_power_critical: true
  eps_boost_w: 120.0
  bypass_edge:
    node_a: manifold
    node_b: scrubber
    kind: bypass

llm:
  base_url: http://localhost:11434
  model: gemma4:e4b
  temperature: 0.45
```

実行時オーバーライド:

```python
from scenario.runner import run_scenario

run_scenario(
    "scrubber_degradation",
    overrides={"agents": {"mode": "llm"}},
)
```

別モデルで別 run 名にする例:

```python
run_scenario(
    "scrubber_degradation",
    overrides={
        "agents": {"mode": "llm", "llm": {"model": "qwen2.5:latest"}},
        "output": {"run_id_llm": "scrubber_degradation_llm_qwen2.5_latest"},
    },
)
```

---

## シミュレーション世界

### 用語

| 略称 | 英語名 | 本シナリオでの意味 |
| --- | --- | --- |
| **ECLSS** | Environmental Control and Life Support System | **生命維持装置** — スクラバー・マニホールド・居住空間（cabin）のグラフ |
| **EPS** | Electrical Power System | 発電・蓄電・配電。`request_eps_boost` で ECLSS へ一時支援 |
| **SARJ** | Solar Alpha Rotary Joint | 太陽電池アレイ発電（`MockSarj`） |
| **BCDU** | Battery Charge/Discharge Unit | 蓄電放電。`eps_telemetry.jsonl` の `bcdu_mode` |
| **MBSU** | Main Bus Switching Unit | 実 EPS の主バス（本 MVP モック未個別実装） |
| **DDCU** | Direct Current-to-Direct Current Converter Unit | 実 EPS の DC-DC 変換（本 MVP モック未個別実装） |
| **ノード** | — | `cabin`, `manifold`, `scrubber`, `power_bus` |
| **回復コマンド** | — | ランタイムの一時操作（下表） |
| **設計提案** | — | ラン終了後の恒久変更（`design_proposals.json`） |

### ヘルス閾値（テレメトリ）

`health_metrics.jsonl` — [api-contracts.md](api-contracts.md) と同じ:

| 指標 | safe | warning | critical |
| --- | --- | --- | --- |
| CO2 (ppm) | < 800 | 800 〜 1200 未満 | ≥ 1200 |
| 電力マージン (W) | > 0 | 0 〜 −150 未満 | ≤ −150 |

### 初期トポロジ

```text
  cabin ──flow──► manifold ──flow──► scrubber ──flow──► cabin
                                        ▲
                                        │ power
                                   power_bus
```

| ノード | kind | 役割 |
| --- | --- | --- |
| `cabin` | volume | CO2 産生・居住空間 |
| `manifold` | manifold | 送気分配 |
| `scrubber` | scrubber | CO2 除去（効率は異常で低下） |
| `power_bus` | electrical | スクラバー駆動電源 |

### 回復コマンド（ランタイム）

| kind | 効果（要約） |
| --- | --- |
| `set_fan_speed` | スクラバー送風加速 → 除去レート UP、消費電力 UP |
| `enable_bypass` | 一時バイパス流路 → 流量ボーナス |
| `reduce_load` | 代謝負荷削減 → CO2 産生 DOWN |
| `request_eps_boost` | BCDU 放電 → `eps_support_w` を一定 step 付与 |

いずれも **恒久トポロジは変えない**。`enable_bypass` は運用フラグであり、`design_proposals` の `add_edge`（恒久バイパス配管）とは別。

---

## エージェントチーム設計

### 同種 N 体 + 代表 action（任意 archetype）

| 概念 | 説明 |
| --- | --- |
| `team.count` | エンジニア数（デフォルト 4） |
| `team.archetypes` | 任意の思考レンズリスト。round-robin 割当。省略または `[]` で同種 persona |
| deliberation | llm: 全員 1 ラウンド（archetype ありならレンズ合成）。labeled: ルールが alert/diagnosis を配信 |
| action rep | `engineer_{(step-1) % N}` がその step のコマンド発行者 |
| post-run rep | 最終 step の代表が `design_proposals.json` を書く |

### labeled_rule_base vs llm

| | labeled_rule_base | llm |
| --- | --- | --- |
| 判断 | `policy` 閾値 | Persona + Telemetry + 議論 |
| 再現性 | 高い | モデル依存 |
| 事後提案 | `bypass_edge` 固定 | LLM が `changes` 生成 |
| 研究用途 | 正解比較・回帰 | モデル比較・発言分析 |

LLM が `policy` を読まない理由: ルールの答えをプロンプトに混ぜず、**公平な比較実験**をするため。設計詳細: [memo/agents/homogeneous_agent_team_plan.md](memo/agents/homogeneous_agent_team_plan.md)。

---

## 出力の読み方

### ファイル一覧

| ファイル | いつ読むか |
| --- | --- |
| `telemetry.jsonl` | CO2・効率・電力の時系列 |
| `eps_telemetry.jsonl` | EPS ブースト・BCDU モード |
| `messages.jsonl` | エージェントの発言・reasoning |
| `events.jsonl` | 異常注入、`recovery_applied` |
| `design_state.jsonl` | ラン中のトポロジ（実質不変） |
| `design_proposals.json` | **事後の恒久案**（ダッシュボード After プレビューの元） |
| `summary.json` | 1 枚サマリ（peak CO2、eps_boost step 等） |
| `provenance.jsonl` | One Piece 互換（現状は主に EPS 回復） |

### design_proposals.json（例: labeled_rule_base）

```json
{
  "proposed_by": "engineer_2",
  "decision_source": "rule",
  "message": "Propose permanent bypass plumbing between manifold and scrubber.",
  "reasoning": "Repeated anomaly and high CO2 during the run; ...",
  "changes": [
    {
      "change_kind": "add_edge",
      "payload": {"node_a": "manifold", "node_b": "scrubber", "kind": "bypass"}
    }
  ],
  "baseline_topology": { "nodes": [...], "edges": [...] }
}
```

LLM モードでは `decision_source: "llm"`、`changes` に `add_node`（`bypass_valve`）や `set_parameter` などが含まれることがある。

### summary.json で見る KPI

| フィールド | 意味 |
| --- | --- |
| `peak_co2_ppm` | ラン中最大 CO2 |
| `final_co2_ppm` | 最終 step の CO2 |
| `eps_boost_applied_step` | 初めて EPS ブーストが効いた step |
| `co2_above_threshold_step` | CO2 が `CO2_WARNING_PPM`（1200 ppm）以上になった step |
| `co2_recovered_below_threshold_step` | CO2 が `CO2_WARNING_PPM`（1200 ppm）未満に戻った step（`co2_above_threshold_step` 設定後） |
| `design_proposal_count` | 事後提案の change 数 |
| `provenance_record_count` | provenance 行数（回復中心） |
| `archetypes` | `agent_id` → レンズ名（無効時は `{}`）。構成→成果の比較用 |

---

## ダッシュボードでの見方

1. **Overview** — 2 run を選び、同じ step で CO2・電力・効率を比較
2. **Step replay** — 1 run を追い、step 17 などで「なぜ EPS ブーストしたか」を reasoning から読む
3. **設計提案セクション** — Before / After グラフで恒久変更案を確認（赤破線 = 提案エッジ）

スクリーンショット: [概要](overview.md#一目でわかるダッシュボード)。

---

## テスト

| テスト | モード | 検証 |
| --- | --- | --- |
| `test_scrubber_baseline.py` | `none` | 異常・CO2 上昇、エージェントなし |
| `test_scrubber_with_agents.py` | `labeled_rule_base` | 回復、final CO2 < 1200（warning 未満）、事後 bypass 提案、ランタイムに bypass エッジなし |
| 同上 | `llm`（Fake） | deliberation/action、post-run 提案、rule フォールバックなし |

```bash
pytest tests/scenario/test_scrubber_baseline.py -q
pytest tests/scenario/test_scrubber_with_agents.py -q
```

---

## 関連ドキュメント

- [architecture.md](architecture.md) — レイヤと実行フロー
- [api-contracts.md](api-contracts.md) — JSONL スキーマ
- [one-piece-integration.md](one-piece-integration.md) — provenance
- [development-plan.md](development-plan.md) — 完了状況・次タスク（CLI、Phase 8、provenance 拡張）
- [scenario-ssos-eclss-loop.md](scenario-ssos-eclss-loop.md) — SSOS 実 ECLSS シナリオ（Phase 0–7 完了）
- [memo/ssos_eclss_loop/ssos_eclss_loop_connection_plan.md](memo/ssos_eclss_loop/ssos_eclss_loop_connection_plan.md) — 接合プラン詳細・検証手順
- [memo/backlog.md](memo/backlog.md) — BL-001〜BL-005
