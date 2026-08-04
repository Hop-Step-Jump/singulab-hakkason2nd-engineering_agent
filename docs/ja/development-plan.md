# 開発プラン（進行中・未着手）

本ドキュメントは **まだ完了していない機能** と **研究バックログ** を集約します。利用可能な機能の説明は [概要](overview.md) および次のシナリオドキュメントを参照してください。


| ドキュメント                                                               | 内容                                |
| -------------------------------------------------------------------- | --------------------------------- |
| [scenario-scrubber-degradation.md](scenario-scrubber-degradation.md) | Mock scrubber シナリオの叙事・設定・出力       |
| [scenario-ssos-eclss-loop.md](scenario-ssos-eclss-loop.md)           | SSOS 実 ECLSS シナリオの叙事・運用・Docker 実行 |
| [architecture.md](architecture.md)                                   | レイヤ構成・二系統実行フロー                    |
| [api-contracts.md](api-contracts.md)                                 | プロトコル・JSONL スキーマ                  |


**SSOS 接合の Phase 0–7 完了状況**: [memo/ssos_eclss_loop/ssos_eclss_loop_connection_plan.md](memo/ssos_eclss_loop/ssos_eclss_loop_connection_plan.md)

---



## マイルストーン一覧



### scrubber_degradation（Mock ECLSS + EPS）— 完了


| 領域         | 内容                                                                        |
| ---------- | ------------------------------------------------------------------------- |
| シミュレータ     | `StationSimulator`（`MockEclssSimulator` + `EpsBackend` mock / `ssos_eps`） |
| シナリオ       | `scrubber_degradation` — 50 step、step 20 から異常注入                           |
| エージェント     | `none` / `labeled_rule_base` / `llm`、同種エンジニア N 体                          |
| 回復         | ファン加速、負荷削減、EPS ブースト、一時バイパス                                                |
| 事後設計       | `design_proposals.json`（scrubber 凍結。ランタイムトポロジ変更なし）                        |
| provenance | ランタイム **回復**（`request_eps_boost`）                                         |
| ダッシュボード    | CO₂ ppm / EPS / トポロジ / 2 run 比較                                           |




### ssos_eclss_loop（SSOS 実 ECLSS）— Phase 0–7 完了


| Phase | 内容                                                         | 状態                                                                                  |
| ----- | ---------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| 0     | ランタイム `DesignChange` 削除                                    | ✅                                                                                   |
| 1a–1b | ARS/OGS smoke、`EclssBackend`、`Ros2EclssBridge`             | ✅                                                                                   |
| 2     | WRS ブリッジ                                                   | ✅                                                                                   |
| 3     | EPS 接合（scrubber 経路、`Ros2EpsBridge`）                        | ✅                                                                                   |
| 4     | `ssos_eclss_loop` + `SsosEclssLoopTeam`                    | ✅                                                                                   |
| 5     | `design_proposals.json`（`ssos_graph`）+ `--apply-proposals` | ✅                                                                                   |
| 6     | LLM エージェント + Docker `ea-loop`（ros2 / Ollama デフォルト）         | ✅                                                                                   |
| 7     | クライアント `graph_rewire`、`Team` ABC、ダッシュボード ssos ビュー          | ✅                                                                                   |
| 8     | ROS launch remap + ゲートウェイ                                  | 📋 [backlog BL-003](memo/backlog.md#bl-003) |


**テスト**: `pytest --ignore=tests/e2e` — **205 passed**, 4 skipped（ROS2 live / コンテナ外は skip）。

**コンテナ回帰**: `./scripts/run_ssos_regression.sh`（Tier 1 pytest。Tier 2 は `SSOS_E2E=1`）。CI: `.github/workflows/ssos-e2e.yml`。

**時間モデル（現状）**: `mock` は 1 EA step = 1 物理 tick。`ros2` は SSOS 実時間のスナップショット駆動（step 同期なし）。run 間リセットは headless 再起動。step 同期の方針検討は [BL-007](memo/backlog.md#bl-007)。

**コンテナ実行（目標）**: `scripts/ssos/mac/ssos-run-detached.sh`（src + results + ヘルパーマウント）→ ホスト `ea run ssos_eclss_loop` のみ。headless 再起動は CLI 内部 bash が担当。

---



## 進行中


| 項目                           | 説明                                                                                          | 参照                                                           |
| ---------------------------- | ------------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| **CLI v3 — SSOS ホスト 1 コマンド** | ボリュームマウント + `ea run ssos_eclss_loop`（内部 bash）、`duration_wall_s`、rclpy shutdown、`ea results` | [cli.md](cli.md), [memo/cli_v3_plan.md](memo/cli_v3_plan.md) |
| LLM 比較実験                     | モデル・温度・run_id を変えた軌道比較（ダッシュボード compare）                                                     | [architecture.md](architecture.md)                           |
| ドキュメント整備                     | `docs/ja/` / `docs/en/` をコード・memo と同期                                                          | [MAINTENANCE.md](MAINTENANCE.md)                                                          |


**CLI v3 スコープ外**（バックログ）: CO2=500kg 初期値・ros2 プラント検証、Streamlit SSOS リッチ表示 → [BL-006](memo/backlog.md#bl-006)

**接合の次段階（検討）**: EA step と SSOS 物理時間の同期 — Mock 拡充 vs upstream sim clock → [BL-007](memo/backlog.md#bl-007)（CLI v3 / Phase 8 とは別トラック）

---



## 次の実装（優先順）

1. **provenance 拡張** — scrubber / ssos の `design_proposals.json` を One Piece レコードへエクスポート
2. **provenance インデックス** — 複数 run 横断の `provenance_index.json`
3. **Phase 8 — ROS launch remap** — `graph_rewire` の launch 適用（BL-003）
4. **ECLSS + EPS 単一 ros2 シナリオ** — 電力危機と SSOS ECLSS を同一 run（BL-004）
5. **EPS 3b/3c** — BCDU discharge 直接呼び出し、`/bcdu/operation` Action（BL-005）

---



## その後（スコープ外に近い）


| 項目                         | 状態                       | 参照                                                        |
| -------------------------- | ------------------------ | --------------------------------------------------------- |
| One Piece Web / SSOT UI    | 未接続（JSON provenance のみ）  | [one-piece-integration.md](one-piece-integration.md)      |
| `agents.mode: base`        | 未実装（創発ロール）               | [backlog.md](memo/backlog.md) BL-001                      |
| 進化ペルソナ研究                   | バックログ                    | BL-002                                                    |
| WRS in `SsosEclssLoopTeam` | バックログ                    | BL-004                                                    |
| upstream CO₂ スクラバ          | SSOS 拡張待ち                | BL-004                                                    |
| MkDocs CI deploy           | `docs/ssos-mkdocs`       | BL-004                                                    |
| SSOS ↔ EA step 同期          | 検討中（Mock 拡充 vs upstream） | [BL-007](memo/backlog.md#bl-007) |


---



## ロードマップ（時系列）

```text
[完了 — scrubber MVP]
  Day 1–6   レイヤ分離、scrubber_degradation、ダッシュボード
  EPS-1–4   SARJ/BCDU モック、StationSimulator、eps_telemetry
  同種 N 体 LLM チーム

[完了 — SSOS 接合 Phase 0–7]
  1a–2     EclssBackend、ARS/OGS/WRS、Ros2EclssBridge
  3        Ros2EpsBridge（scrubber 電力）
  4–6      ssos_eclss_loop、design_proposals、LLM、ea-loop
  7        client graph_rewire、Team ABC、ssos ダッシュボード
  Day 8    CLI（`ea run`、RunSpec、クラスタ向け job runner）

[次]
  Day 9    provenance インデックス、design エクスポート
  Phase 8  launch remap + ゲートウェイ（BL-003）
  BL-004/5 ECLSS+EPS 統合、EPS 3b/3c、WRS team

[検討 — SSOS 接合の次段階]
  BL-007   EA step ↔ SSOS 物理時間（Mock 拡充 A / upstream B / 緩和 C）

[研究]
  BL-001   base モード（創発ロール）
  BL-002   進化ペルソナ
```

詳細: [memo/scrubber_degradation/mvp_plan.md](memo/scrubber_degradation/mvp_plan.md)、[memo/ssos_eclss_loop/](memo/ssos_eclss_loop/)、[memo/backlog.md](memo/backlog.md)。

---



## 研究メモ（`docs/ja/memo/`）


| メモ                                                                                                                      | 内容                                                            |
| ----------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| [mvp_plan.md](memo/scrubber_degradation/mvp_plan.md)                                                                                         | Week ロードマップ、Day 1–10                                          |
| [ssos_eclss_loop/ssos_eclss_loop_connection_plan.md](memo/ssos_eclss_loop/ssos_eclss_loop_connection_plan.md)           | SSOS ECLSS Phase 0–7 詳細・検証手順                                  |
| [ssos_eclss_loop/ssos_eps_ros2_connection_plan.md](memo/ssos_eclss_loop/ssos_eps_ros2_connection_plan.md)               | EPS ROS2 ブリッジ（Phase 3）                                        |
| [ssos_eclss_loop/ssos_ros2_graph_design_investigation.md](memo/ssos_eclss_loop/ssos_ros2_graph_design_investigation.md) | ゲートウェイ・remap 調査                                               |
| [backlog.md](memo/backlog.md)                                                                                           | BL-001〜BL-007（創発ロール、Phase 8、ECLSS/EPS、CLI v3 スコープ外、step 同期検討） |
| [cli_v3_plan.md](memo/cli_v3_plan.md)                                                                                   | **CLI v3 最終** — SSOS マウント + `ea run` 1 コマンド                   |
| [homogeneous_agent_team_plan.md](memo/agents/homogeneous_agent_team_plan.md)                                                   | 同種 N 体チーム設計                                                   |
| [eps_implementation_plan.md](memo/scrubber_degradation/eps_implementation_plan.md)                                      | EPS-1〜4、CLI Day 区切り                                           |


---



## SSOS / One Piece 接合（現状）

```text
[ scrubber_degradation — Mock 凍結 ]
  StationSimulator → ScrubberDegradationTeam
       ↓ JSONL + design_proposals.json（scrubber ドメイン）
  Dashboard（ppm / EPS / トポロジ）

[ ssos_eclss_loop — Phase 0–7 完了 ]
  EclssBackend (mock | ros2) → SsosEclssLoopTeam(Team)
       ↓ JSONL + design_proposals.json（ssos_graph）
  Dashboard（storage kg / operational timeline）
  ea-loop（Docker）+ graph_rewire（クライアント remap）

[ 未接続・バックログ ]
  ROS launch remap（Phase 8）     … BL-003
  design_proposals → provenance  … Day 9
  EA step ↔ SSOS 物理同期        … BL-007（検討）
  One Piece Web UI               … スコープ外
```

One Piece 連携: [one-piece-integration.md](one-piece-integration.md)。

---



## コントリビュータ向けチェックリスト

新機能を足すとき:

1. `SimulatorProtocol` / `EclssBackend` / JSONL スキーマを変えたら [api-contracts.md](api-contracts.md) を更新
2. エージェント・シナリオを増やしたら [architecture.md](architecture.md) を更新
3. 回帰: `pytest`（全体）、scrubber は `test_scrubber_baseline.py` / `test_scrubber_with_agents.py`、ssos は `test_ssos_eclss_loop*.py`
4. SSOS コンテナ検証: `./scripts/run_ssos_eclss_loop.sh`、`run_graph_rewire_e2e.sh`（ECLSS headless 前提）
5. 完了した項目は本ファイルの「完了」へ移し、バックログは [backlog.md](memo/backlog.md) で管理

