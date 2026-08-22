# One Piece 連携

設計変更と運用回復の **provenance（来歴）** を、One Piece のデータモデルと互換な JSON で記録する。完全な [One Piece](https://github.com/hirototamura/one-piece) Web UI は現 MVP のスコープ外。

> JSONL スキーマ: [api-contracts.md](api-contracts.md)。未完了項目: [development-plan.md](development-plan.md)。

---

## 目的

自律ハードウェア開発の前段として、次を追跡可能にする:

1. **ランタイム回復**（scrubber）— 誰が、いつ、どの EPS ブーストを要求したか
2. **ランタイム運用**（ssos）— 誰が、いつ、どの ARS/OGS/WRS コマンドを打ったか
3. **事後設計提案** — 誰が、なぜ、どの変更を推奨したか（`design_proposals.json`）
4. （将来）One Piece SSOT への取り込みと横断インデックス

シミュレーションループは provenance 生成でブロックしない。失敗時は warning ログのみ。

---

## レイアウト

```text
src/integrations/one_piece/
├── __init__.py        # export_run_provenance
├── client.py          # events/messages からレコード構築
└── ssot_schema.json   # MVP サブセット（elements, parameters, traces）
```

---

## トリガーとフロー

### scrubber_degradation

`ScrubberDegradationScenario.run()` の末尾:

```text
1. team.propose_post_run_design()  → design_proposals.json
2. log.write_summary(summary)
3. export_run_provenance(run_dir)  → provenance.jsonl
4. summary に provenance_path / provenance_record_count を追記
```

### ssos_eclss_loop

`SsosEclssLoopScenario.run()` も同様。`agents.actor.mode` が `labeled_rule_base` または `llm` のとき運用 provenance をエクスポート。運用イベント（`/eclss/events/operational_applied`）が `record_type: operational` になる。事後の `design_proposals.json` は `PostRunDesignAgent` が書く（`team.propose_post_run_design` ではない）。

```text
events.jsonl ──┐
messages.jsonl ├──► build_provenance_records() ──► provenance.jsonl
design_state.jsonl ┘
summary.json
```

---

## 現状エクスポートされるレコード

| 種別 | ソース | scrubber_degradation | ssos_eclss_loop |
| --- | --- | --- | --- |
| `design_change` | ランタイム `/eclss/events/design_change` | **0 件** | **0 件** |
| `recovery` | `request_eps_boost` の `recovery_applied` | **1 件以上** | — |
| `operational` | `/eclss/events/operational_applied` | — | **0 件以上** |

### 回復レコード（scrubber・実装済み）

```json
{
  "record_id": "scrubber_degradation_labeled_rule_base:recovery:1",
  "record_type": "recovery",
  "run_id": "scrubber_degradation_labeled_rule_base",
  "scenario": "scrubber_degradation",
  "step": 28,
  "actor": "engineer_3",
  "actor_kind": "ai_agent",
  "change_kind": "request_eps_boost",
  "payload": {
    "support_w": 120.0,
    "eps": {"bcdu_mode": "discharging"}
  },
  "trace": {
    "event_kind": "/eclss/events/recovery_applied",
    "decision_source": "rule",
    "message": "Requesting EPS support boost of 120 W.",
    "reasoning": "Power margin critical; requesting temporary EPS assist."
  }
}
```

`actor` は `issued_by`（`engineer_*`）。`trace` は同一 step の `recovery_command` メッセージ（`from_role == actor`）から解決する。

### 運用レコード（ssos_eclss_loop・実装済み）

```json
{
  "record_id": "ssos_eclss_loop_labeled_rule_base:operational:1",
  "record_type": "operational",
  "run_id": "ssos_eclss_loop_labeled_rule_base",
  "scenario": "ssos_eclss_loop",
  "step": 12,
  "actor": "engineer_1",
  "actor_kind": "ai_agent",
  "change_kind": "air_revitalisation",
  "payload": {"target_co2_kg": 0.5},
  "trace": {
    "event_kind": "/eclss/events/operational_applied",
    "decision_source": "rule",
    "message": "CO2 storage high; dispatching ARS.",
    "result_success": true
  }
}
```

`trace` は同一 step の `operational_command` メッセージから解決する（ARS/OGS 等はメッセージ文で照合）。

### 設計変更レコード（プロトコル対応済み・データなし）

ランタイム設計変更は Phase 0 で削除済み。scrubber の事後 `design_proposals.json` は One Piece 未エクスポート。

---

## design_proposals.json との関係

| 成果物 | タイミング | provenance 連携 |
| --- | --- | --- |
| `design_proposals.json` | ラン終了後 | **未エクスポート**（開発予定） |
| `provenance.jsonl` | ラン終了後 | ランタイムイベント（回復 / 運用） |

scrubber の事後提案（バイパス弁、非常電源等）および ssos の `ssos_graph` 提案（`action_profile`、`service_config`、`graph_rewire` 等）は `design_proposals.json` にあり、ダッシュボードがプレビューを描画する。One Piece へは **まだ自動連携しない**。

ssos の `design_domain: ssos_graph` の読み方: [scenario-ssos-eclss-loop.md](scenario-ssos-eclss-loop.md#design_proposalsjsonssos_graph)。

### 想定される次ステップ（Day 9）

1. `design_proposals.json` を読み、`record_type: design_proposal` レコードを追加
2. `before_topology` = `baseline_topology`、`after_topology` = 提案適用後の仮想グラフ
3. `trace.decision_source` = `rule` / `llm`、`trace.reasoning` = 提案理由

---

## データモデル（MVP サブセット）

One Piece `SsotProvenanceRecord` 概念に準拠。必須フィールド:

| フィールド | 説明 |
| --- | --- |
| `record_id` | `{run_id}:{種別}:{連番}` |
| `run_id` | 実行ディレクトリ名 |
| `scenario` | `scrubber_degradation` 等 |
| `step` | イベント step |
| `actor` | 代表エンジニア ID（`engineer_*`） |
| `actor_kind` | `ai_agent` / `logic_automation` |
| `change_kind` | `request_eps_boost`、`add_edge` 等 |
| `payload` | コマンド/変更の詳細 |
| `trace` | message、reasoning、decision_source、parse_status |

任意: `record_type`（`recovery`）、`before_topology` / `after_topology`（設計変更時）。

契約: `src/integrations/one_piece/ssot_schema.json`。

---

## summary.json とのリンク

```json
{
  "provenance_path": "src/experiments/results/scrubber_degradation_labeled_rule_base/provenance.jsonl",
  "provenance_record_count": 2,
  "design_proposals_path": ".../design_proposals.json",
  "design_proposal_count": 1
}
```

ベースライン（`agents.mode: none`）も **0 件の `provenance.jsonl`** を出力し、ファイル存在契約を安定化。

---

## SSOS トポロジ取り込み

| 経路 | 状態 |
| --- | --- |
| Mock ECLSS デフォルトトポロジ | scrubber — `environment/scrubber/eclss_ops/design_state.py` |
| SSOS 実 ECLSS 運用 | ssos — `Ros2EclssBridge` + `EclssBackend`（Phase 0–7 完了） |
| One Piece コネクタ [`ssos.py`](https://github.com/hirototamura/one-piece/blob/main/packages/connectors/one_piece_connectors/ssos.py) | 任意 — 実 SSOS から初期 `SystemElement` + ICD グラフをシード |

Phase 8（ROS launch remap + ゲートウェイ）: [backlog BL-003](memo/backlog.md#bl-003)。

---

## 依存戦略

- **JSON ファイル + 将来コネクタ** — provenance 形式が安定するまで One Piece パッケージへのハード依存を避ける
- 取り込み必要時: git submodule または `pip install -e ../one-piece/packages/connectors`
- 方針詳細: [memo/scrubber_degradation/mvp_plan.md](memo/scrubber_degradation/mvp_plan.md)

---

## ステータスまとめ

| 項目 | 状態 |
| --- | --- |
| `export_run_provenance()` | 完了 |
| scrubber EPS 回復 provenance | 完了 |
| ssos 運用 provenance | 完了 |
| ランタイム design_change provenance | プロトコルあり・現シナリオでは 0 件 |
| post-run `design_proposals` → provenance | **未実装** |
| `provenance_index.json`（横断） | **未実装** |
| One Piece Web UI | スコープ外 |

---

## 関連ドキュメント

- [api-contracts.md](api-contracts.md) — 全 JSONL スキーマ
- [scenario-scrubber-degradation.md](scenario-scrubber-degradation.md) — scrubber 出力の読み方
- [scenario-ssos-eclss-loop.md](scenario-ssos-eclss-loop.md) — ssos 運用・出力の読み方
- [architecture.md](architecture.md) — 実行フロー
- [development-plan.md](development-plan.md) — Day 9–10 計画
