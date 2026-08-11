# クイックスタート

SSOS 接合 smoke テストと `ssos_eclss_loop` の **ros2** バックエンド向け手順です。**Mac ホストには ROS 2 がない**ため、実機プラントは Docker 内で動き、シミュレーションの起動は **ホスト** から `ea run` します。

!!! info "初回はこちらから"
    Docker 不要の mock だけ試す場合は [クイックスタート](../index.md)（`ea run ssos_eclss_loop --backend mock`）を参照してください。

シナリオ仕様: [ssos_eclss_loop シナリオ](../scenario-ssos-eclss-loop.md)

---

## ssos_eclss_loop — コマンド一式（Mac） { #ssos_eclss_loop--コマンド一式mac }

### 初回：環境設定からシミュレーションまで

マシンごとに一度。すべて **ホスト** のターミナルで実行してください。

```bash
cd /path/to/engineering_agents

# Python CLI
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# SSOS コンテナ（ヘルパーを /root/ にマウント）
./scripts/ssos/mac/ssos-run-detached.sh

# 任意：確認
docker ps --filter name=ssos
docker exec ssos test -f /root/ssos-eclss-headless.sh && echo "headless helper OK"

# シミュレーション
ea run ssos_eclss_loop --agents-mode labeled_rule_base --steps 50

# 結果
ea results
```

出力例: `src/experiments/results/ssos_eclss_loop_labeled_rule_base/`（`telemetry.jsonl`, `summary.json` 等）

詳細: [CLI ガイド — SSOS Docker](../cli.md#ssos-docker-ssos_eclss_loop--ros2)

### 2 回目以降：シミュレーションのみ

**コンテナが Up**（`docker ps --filter name=ssos`）:

```bash
cd /path/to/engineering_agents
source .venv/bin/activate
ea run ssos_eclss_loop --agents-mode labeled_rule_base --steps 50
ea results
```

**コンテナが停止**（`docker ps -a` で `Exited`）:

```bash
docker start ssos
cd /path/to/engineering_agents
source .venv/bin/activate
ea run ssos_eclss_loop --agents-mode labeled_rule_base --steps 50
ea results
```

!!! tip "覚えておくこと"
    - `ea run` は **ホスト専用**（コンテナ内では `ea` は使わない）
    - **毎 run 前に headless を再起動**し、プラント状態を初期化（手動の第 2 ターミナル不要）
    - LLM 利用時はホストで Ollama を起動し `--agents-mode llm` を指定

---

## 前提条件（詳細）

### 1. SSOS Docker コンテナ

| 項目 | 典型値 |
| --- | --- |
| コンテナ名 | `ssos`（`SSOS_CONTAINER` / `SSOS_CONTAINER_NAME` で上書き可） |
| イメージ | `ghcr.io/space-station-os/space_station_os:latest` |
| ROS ディストリ | **Jazzy**（`/opt/ros/jazzy/setup.bash`） |
| ワークスペース | `~/ssos_ws/install/setup.bash` |

作成手順は冒頭の [コマンド一式](#ssos_eclss_loop--コマンド一式mac) を参照。`scripts/ssos/` 内のヘルパーが `/root/` にマウントされます。

!!! note "smoke テスト用の旧手順"
    下記の **2 ターミナルワークフロー**（手動 headless + `docker cp`）は Phase 1a smoke 向けです。`ssos_eclss_loop` の通常運用は上記 `ea run` を使ってください。

### 2. engineering_agents 開発環境

```bash
cd /path/to/engineering_agents
pip install -e ".[dev]"
pytest --ignore=tests/e2e   # 回帰確認（205 passed / 4 skipped 前後を期待）
```

### 3. 環境変数（任意）

| 変数 | デフォルト | 用途 |
| --- | --- | --- |
| `SSOS_CONTAINER` | `ssos` | smoke ラッパーの対象コンテナ |
| `SSOS_CONTAINER_REPO` | `/ea` | コンテナ内 sync 先 |
| `ROS_DOMAIN_ID` | ECLSS: 未設定 / EPS: `23` | DDS ドメイン（EPS smoke ラッパーが 23 を export） |
| `SSOS_ECLSS_BACKEND` | — | `ssos_eclss_loop` の backend 上書き（`mock` \| `plant_sim` \| `ros2`） |

!!! warning "Mac Docker と DDS"
    Mac Docker Desktop では `--network=host` が使えません。ホスト Mac から SSOS ROS グラフへ直接 DDS 接続するのは **非推奨** です。smoke ラッパーは `docker cp` + `docker exec` でコンテナ内実行します。

---

## 2 ターミナルワークフロー（ECLSS smoke）

```mermaid
sequenceDiagram
  participant T1 as Terminal 1<br/>コンテナ内
  participant SSOS as SSOS ECLSS<br/>ROS 2 graph
  participant T2 as Terminal 2<br/>ホスト Mac
  participant Wrap as run_ssos_eclss_*.sh

  T1->>SSOS: bash /root/ssos-eclss-headless.sh
  Note over SSOS: eclss.launch.py<br/>crew GUI なし
  T2->>Wrap: ./scripts/run_ssos_eclss_smoke.sh
  Wrap->>Wrap: docker cp src/ → コンテナ
  Wrap->>SSOS: python3 -m scripts.ssos_eclss_ars_smoke
  SSOS-->>Wrap: JSON レポート / exit 0
```

### Terminal 1 — ECLSS ヘッドレス起動

```bash
docker exec -it ssos bash
bash /root/ssos-eclss-headless.sh
# Ctrl+C で停止。smoke 実行中は起動したままにする。
```

内部相当コマンド:

```bash
ros2 launch space_station eclss.launch.py
```

### Terminal 2 — Phase 1a ARS smoke（ホスト repo ルート）

```bash
cd /path/to/engineering_agents
chmod +x scripts/run_ssos_eclss_smoke.sh   # 初回のみ
./scripts/run_ssos_eclss_smoke.sh
# JSON 保存: ./scripts/run_ssos_eclss_smoke.sh --json-out /tmp/eclss_smoke.json
```

**合格条件**: exit code 0、`/co2_storage` と `/ars/diagnostics` が存在、`air_revitalisation` goal が SUCCEEDED。

### Phase 1b / 2 smoke（同じ Terminal 1 前提）

```bash
./scripts/run_ssos_eclss_1b_smoke.sh    # ARS + OGS + Sabatier 信号
./scripts/run_ssos_eclss_2_smoke.sh     # + WRS + 飲料水トレードオフ
```

---

## EPS smoke（Phase 3）

EPS は **フルステーションまたは EPS launch** が必要です。ECLSS ヘッドレスだけでは solar/BCDU トピックが無い場合があります。

```bash
# Terminal 1（例: フルステーション — コンテナ内）
ros2 launch space_station space_station.launch.py
# または EPS のみ: ros2 launch space_station eps.launch.py

# Terminal 2（ホスト）
./scripts/run_ssos_eps_smoke.sh
./scripts/run_ssos_eps_smoke.sh --arm-discharge-w 100 --arm-duration-steps 3
```

---

## ssos_eclss_loop シナリオ（ホスト — ROS 不要）

### mock（最速）

```bash
cd /path/to/engineering_agents
PYTHONPATH=src python3 -m scenario.ssos_eclss_loop.scenario_run --backend mock
PYTHONPATH=src python3 -m scenario.ssos_eclss_loop.scenario_run \
  --backend mock --agents-mode labeled_rule_base --steps 8
```

### plant_sim（物質収支プラント）

```bash
PYTHONPATH=src python3 -m scenario.ssos_eclss_loop.scenario_run \
  --backend plant_sim --agents-mode labeled_rule_base --steps 72
```

[Plant Sim backend 解説](../memo/ssos_eclss_loop/plant_sim_backend.md) を参照。

出力: `src/experiments/results/<run_id>/`（`telemetry.jsonl`, `health_metrics.jsonl`, `summary.json`）

---

## ssos_eclss_loop（ROS2 — 推奨: ホストから `ea run`）

上記 [コマンド一式](#ssos_eclss_loop--コマンド一式mac) を参照。レガシー経路のみ以下。

### レガシー: コンテナ内で直接実行

手動 headless + `docker cp` 経路（デバッグ用）:

```bash
source /opt/ros/jazzy/setup.bash
source ~/ssos_ws/install/setup.bash
cd /ea   # デフォルト sync 先（SSOS_CONTAINER_REPO で上書き可）
PYTHONPATH=/ea/src SSOS_ECLSS_BACKEND=ros2 EA_RESULTS_ROOT=/ea/results \
  python3 -m scenario.ssos_eclss_loop.scenario_run --backend ros2
```

---

## コンテナ E2E 回帰（ワンコマンド） { #container-e2e-regression-one-command }

`scripts/run_ssos_regression.sh` は **Tier 1**（ホスト `pytest`）と任意の **Tier 2**（SSOS Docker 実機 smoke + `ea-loop`）を連鎖します。共通ヘルパは `scripts/lib/ssos_docker.sh` です。

### Tier 1 — デフォルト（Docker 不要）

```bash
./scripts/run_ssos_regression.sh
# pytest を実行（tests/e2e 除外）。"Tier 2 skipped" と表示
```

### Tier 2 — フル SSOS コンテナ連鎖

Docker と SSOS イメージ（`ghcr.io/space-station-os/space_station_os:latest`）が必要です。管理コンテナ（`ssos-regression-<pid>`）を作成し、ヘッドレス ECLSS を起動、`src/` を sync して以下を実行します:

1. ARS smoke → 1b smoke → WRS smoke → graph rewire smoke
2. `labeled_rule_base` で `ssos_eclss_loop`（デフォルト 5 ステップ）

```bash
SSOS_E2E=1 ./scripts/run_ssos_regression.sh
# 成果物: artifacts/ssos-regression/<timestamp>/
```

| フラグ / 環境変数 | 効果 |
| --- | --- |
| `--skip-pytest` | Tier 2 のみ（`SSOS_E2E=1` と同等） |
| `--with-eps` | `ssos-headless.sh` を使い EPS smoke を追加 |
| `--with-llm` | `llm` モードの `ea-loop` も実行（ホストに Ollama が必要） |
| `--use-existing` | 起動中の `SSOS_CONTAINER` を再利用。作成/削除しない |
| `--keep-container` | 終了時に管理コンテナを削除しない |
| `--steps N` | `ea-loop` のシミュレーションステップ数（デフォルト: 5） |
| `SSOS_IMAGE` | 事前ビルドイメージの上書き |
| `SSOS_ROS_DOMAIN_ID` | コンテナ内 DDS ドメイン（デフォルト: `23`） |

pytest フック（Tier 2）:

```bash
SSOS_E2E=1 pytest tests/e2e/test_ssos_regression.py -m ssos_e2e
```

### CI（`.github/workflows/ssos-e2e.yml`）

| ジョブ | タイミング | 内容 |
| --- | --- | --- |
| `pytest` | 全 PR | 全 pytest + `test_regression_tier1_pytest_only` |
| `ssos-e2e` | `workflow_dispatch` または週次 cron（月 03:00 UTC） | self-hosted `ssos` ランナーで Tier 2 |

GitHub Actions から手動 Tier 2: **Actions → SSOS E2E Regression → Run workflow**（`with_eps` / `with_llm` / `use_existing` 任意）。

---

## ドキュメントのブラウザ表示

MkDocs Material でローカルプレビュー:

```bash
pip install -e ".[dev]"
mkdocs serve
# → http://127.0.0.1:8000/ssos/  （SSOS 接合セクション）
```

静的ビルド:

```bash
mkdocs build
# 出力: site/ — 任意の静的ホストや GitHub Pages に配置可
```

GitHub 上では `docs/ssos/index.md` をそのまま閲覧できます（Mermaid は GitHub ネイティブレンダリング対応）。

---

## 次のステップ

- [ECLSS 統合](eclss-integration.md) — Action 型・Service 詳細
- [EPS 統合](eps-integration.md) — `request_eps_boost` の写像
- [トラブルシューティング](troubleshooting.md) — よくある失敗パターン
