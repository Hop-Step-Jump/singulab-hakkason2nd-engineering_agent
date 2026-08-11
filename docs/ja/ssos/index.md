# SSOS ECLSS + EPS 接合 — 概要

本ドキュメントは、Space Station OS（SSOS）の **ECLSS**（生命維持）と **EPS**（電力）を `engineering_agents` から操作するための接合レイヤを説明します。Crew Simulation GUI の代わりに、エージェントが `EclssBackend` / `EpsBackend` 経由で ARS・OGS・WRS および BCDU を制御します。

シナリオ仕様（エージェント・出力・ダッシュボード）は [ssos_eclss_loop シナリオ](../scenario-ssos-eclss-loop.md) を参照してください。ここでは **Docker / ROS 2 接合の運用** に焦点を当てます。

!!! note "スコープ"
    - **仮想検証**が主目的です。物理世界（軌道上実機）への接続は本デモのスコープ外です。
    - 参照シナリオ `scrubber_degradation` は **Mock 凍結**のままです。SSOS 接合は新シナリオ `ssos_eclss_loop` で検証します。
    - ランタイム中の恒久トポロジ変更（旧 `DesignChange`）は **Phase 0 で削除済み**です。

---

## なぜ接合するか

| 従来（Crew Simulation） | 接合後（engineering_agents） |
| --- | --- |
| 人間オペレータが GUI で ARS/OGS を操作 | AI エージェントが `EclssBackend` API で同操作を再現 |
| 合否が主観的になりうる | テレメトリ JSONL + 決定論的 `health_metrics` で検証 |
| 設計と運用が混在しやすい | ランタイムは **運用コマンドのみ**、恒久変更は事後 `design_proposals.json`（Phase 5） |

エージェントは「物理シミュレータの代わりに LLM が合格を宣言する」**自作自演**になってはなりません。SSOS Docker 上の ROS 2 グラフから取得した生テレメトリを入力に、シナリオ YAML の閾値で pass/fail を決めます（[AGENTS.md](../AGENTS.md) 参照）。

---

## Tier Model

接合は段階的に深くなります。各 Tier は独立して smoke テスト可能です。

| Tier | Phase | 内容 | バックエンド | 検証 |
| --- | --- | --- | --- | --- |
| **T0** | 0 | `DesignChange` 削除、`scrubber_degradation` 凍結 | Mock のみ | `pytest` |
| **T1a** | 1a | ARS Action smoke | `ros2` CLI → SSOS | `run_ssos_eclss_smoke.sh` |
| **T1b** | 1b | ARS + OGS + Service | `Ros2EclssBridge` | `run_ssos_eclss_1b_smoke.sh` |
| **T2** | 2 | + WRS（飲料水 vs 電解水） | `Ros2EclssBridge` | `run_ssos_eclss_2_smoke.sh` |
| **T3** | 3 | EPS 読取 + `request_eps_boost` interim | `Ros2EpsBridge` | `run_ssos_eps_smoke.sh` |
| **T4** | 4 | `ssos_eclss_loop` シナリオ + エージェント | mock \| plant_sim \| ros2 | `scenario_run.py` |
| **T5** | 5 | `design_proposals.json` + `--apply-proposals` | — | `scenario_run.py` |
| **Regression** | — | コンテナ E2E オーケストレータ（pytest + smoke 連鎖 + ea-loop） | `run_ssos_regression.sh` | `.github/workflows/ssos-e2e.yml` |

---

## コンテナ回帰テスト

`scripts/run_ssos_regression.sh` は SSOS 接合回帰の単一エントリポイントです。

| Tier | 範囲 | Docker 要否 |
| --- | --- | --- |
| **Tier 1** | 全 `pytest`（デフォルト。`tests/e2e` 除外） | 不要 |
| **Tier 2** | 管理コンテナ → ヘッドレス ECLSS → ARS/1b/WRS/graph-rewire smoke → `ea-loop` | 要（`SSOS_E2E=1`） |

成果物は `artifacts/ssos-regression/<timestamp>/` に出力されます（smoke JSON、`ea-loop` 出力）。手順は [クイックスタート — コンテナ E2E 回帰](quickstart.md#container-e2e-regression-one-command) を参照。

---

## アーキテクチャ

```mermaid
flowchart TB
  subgraph agents [scenario/ — エージェント層]
    Team[SsosEclssLoopTeam]
    Runner[SsosEclssLoopScenario]
  end

  subgraph backends [environment/ssos/ — バックエンド層]
    EclssProto[EclssBackend Protocol]
    EpsProto[EpsBackend Protocol]
    MockEclss[LoopMockEclssBackend / MockEclssBackend]
    PlantSim[PlantSimEclssBackend]
    Ros2Eclss[Ros2EclssBridge]
    MockEps[MockEpsBackend]
    Ros2Eps[Ros2EpsBridge]
  end

  subgraph ssos [SSOS Docker — ROS 2 Jazzy]
    ARS[air_revitalisation]
    OGS[oxygen_generation]
    WRS[water_recovery_systems]
    BCDU[/bcdu/status]
    Solar[/solar_controller/ssu_voltage_v]
  end

  Team --> Runner
  Runner --> EclssProto
  EclssProto --> MockEclss
  EclssProto --> PlantSim
  EclssProto --> Ros2Eclss
  Ros2Eclss -->|ros2 CLI| ARS
  Ros2Eclss --> OGS
  Ros2Eclss --> WRS

  subgraph scrubber [scrubber_degradation — 凍結]
    Station[StationSimulator]
    Station --> EpsProto
    EpsProto --> MockEps
    EpsProto --> Ros2Eps
    Ros2Eps -->|ros2 CLI| BCDU
    Ros2Eps --> Solar
  end
```

### 実行パスの違い

| シナリオ | シミュレータ | ECLSS | EPS |
| --- | --- | --- | --- |
| `scrubber_degradation` | `StationSimulator` | `MockEclssSimulator` | `mock` \| `ssos_eps` |
| `ssos_eclss_loop` | なし（`EclssBackend` 直接） | `mock` \| `plant_sim` \| `ros2` | 未使用（Phase 4） |

---

## 主要ファイル一覧

| パス | 役割 |
| --- | --- |
| `src/environment/ssos/eclss/backend.py` | `EclssBackend` Protocol |
| `src/environment/ssos/eclss/types.py` | Goal / Report データ型 |
| `src/environment/ssos/eclss/mock/backend.py` | 契約テスト用 Mock |
| `src/environment/ssos/eclss/plant_sim/` | 物質収支プラント backend |
| `src/environment/ssos/eclss/ros2/bridge.py` | SSOS ECLSS ブリッジ（CLI） |
| `src/environment/ssos/eclss/ros2/topics.py` | Action / Service / Topic 定数 |
| `src/environment/ssos/eclss/ros2/graph_rewire.py` | クライアント側グラフ remap |
| `src/environment/ssos/ros2/cli.py` | 共有 `ros2` サブプロセスヘルパ |
| `src/environment/scrubber/eps/backend.py` | `EpsBackend` Protocol（scrubber） |
| `src/environment/scrubber/eps/mock/backend.py` | SARJ/BCDU Mock ラッパ |
| `src/environment/ssos/eps/ros2/bridge.py` | SSOS EPS ブリッジ（CLI） |
| `src/environment/ssos/eps/ros2/topic_map.py` | SSOS 実トピック ↔ 契約名 |
| `src/environment/ssos/eps/ros2/adapters.py` | ROS メッセージ ↔ dataclass |
| `src/scenario/ssos_eclss_loop/` | 新シナリオ（YAML + runner + health） |
| `src/scenario/agents/ssos_eclss_loop_team.py` | Crew 代替エージェント |
| `scripts/run_ssos_eclss_*.sh` | ホスト → Docker smoke ラッパ |
| `scripts/run_ssos_eps_smoke.sh` | EPS smoke ラッパ |
| `scripts/run_ssos_regression.sh` | Tier 1 pytest + 任意 Tier 2 コンテナ E2E |
| `scripts/lib/ssos_docker.sh` | Docker sync・ヘッドレス起動・グラフ待機の共通ヘルパ |
| `.github/workflows/ssos-e2e.yml` | CI: PR pytest + 定期/手動 Tier 2 |

---

## 関連リンク

- [Docker セットアップ](quickstart.md) — `ea run` と smoke テスト
- [ECLSS 統合](eclss-integration.md) — トピック・アクション詳細
- [EPS 統合](eps-integration.md) — 電力ブースト interim 方式
- [ssos_eclss_loop シナリオ](../scenario-ssos-eclss-loop.md) — シナリオ仕様・出力の読み方
- [トラブルシューティング](troubleshooting.md)
- [API リファレンス](api-reference.md)
- 開発メモ: [SSOS ECLSS 接合プラン](../memo/ssos_eclss_loop/ssos_eclss_loop_connection_plan.md), [SSOS EPS ROS2 接合プラン](../memo/ssos_eclss_loop/ssos_eps_ros2_connection_plan.md)
