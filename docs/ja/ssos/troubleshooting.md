# トラブルシューティング

SSOS ECLSS + EPS 接合でよく遭遇する問題と対処法です。

---

## Action 型不一致 — goal が永久待ち

### 症状

```
Waiting for an action server...
```

`ros2 action list` には `air_revitalisation` が見えるが、`send_goal` が返らない。

### 原因

Action **名前**は一致していても **型**が異なる。旧ドキュメントの `space_station_eclss/action/...` は現行 Jazzy イメージでは無効。

### 確認

```bash
ros2 node info /air_revitalisation | grep -A1 'Action Servers'
# 期待: space_station_interfaces/action/AirRevitalisation
```

### 対処

正しい型で手動送信（質量フィールドは SSOS ワイヤ上 **グラム** — `1800.0` ≈ 1.8 kg）:

```bash
ros2 action send_goal /air_revitalisation \
  space_station_interfaces/action/AirRevitalisation \
  "{initial_co2_mass: 1800.0, initial_moisture_content: 25.0, initial_contaminants: 5.0}"
```

コード側は `src/environment/ssos/eclss/ros2/topics.py` の `ACTION_TYPE_*` 定数を使用（`Ros2EclssBridge` はこれに従う）。

---

## Power granted vs goal — Action 結果の解釈

### 症状

Action が `SUCCEEDED` だが、期待する CO₂/O₂ 変化が telemetry に現れない。または feedback に "Power granted" のみ。

### 原因

SSOS ECLSS サブシステムは EPS 電力状態に依存する場合がある。ECLSS ヘッドレスのみ起動で EPS 未起動のとき、Action は受理されても物理効果が限定的。

### 対処

1. フルステーション起動を検討: `ros2 launch space_station space_station.launch.py`
2. `poll_telemetry()` を action **前後**で比較（smoke レポートの `telemetry_before` / `telemetry_after`）
3. Phase 1b では Sabatier **信号**（`sabatier_signal: true`）を合格条件に — 絶対値より相関を重視

---

## ros2 CLI not found（ホスト Mac）

### 症状

```
ros2 CLI not found on host and docker is unavailable.
```

またはホストで `PYTHONPATH=src python3 -m scripts.ssos_eclss_ars_smoke` を実行して失敗。

### 原因

**想定どおり**。Mac ホストに ROS 2 Jazzy はインストールされていません。

### 対処

ラッパースクリプトを使用:

```bash
./scripts/run_ssos_eclss_smoke.sh
./scripts/run_ssos_eclss_1b_smoke.sh
./scripts/run_ssos_eclss_2_smoke.sh
./scripts/run_ssos_eps_smoke.sh
```

---

## PYTHONPATH が ROS workspace を上書き

### 症状

コンテナ内で `PYTHONPATH=src python3 ...` 実行後、`ros2` コマンド自体が壊れる / import エラー。

### 原因

`PYTHONPATH=src` が **代入**（prepend ではない）され、ROS workspace のパスが消える。

### 対処

**prepend** する:

```bash
PYTHONPATH=/tmp/engineering_agents/src:${PYTHONPATH} python3 -m scripts.ssos_eclss_ars_smoke
```

smoke ラッパーは自動で `PYTHONPATH='$CONTAINER_REPO/src:'${PYTHONPATH}` と設定します。

---

## ros2 graph が空

### 症状

```
WARNING: ros2 graph is empty — ECLSS may not be running yet.
```

### 原因

Terminal 1 で ECLSS / ステーションが未起動、または起動直後で discovery 未完了。

### 対処

1. Terminal 1: `bash /root/ssos-eclss-headless.sh` が動作中か確認
2. コンテナ内: `ros2 topic list` / `ros2 action list` でグラフ確認
3. smoke の `--wait-timeout` を延長（スクリプト引数を確認）
4. `ROS_DOMAIN_ID` が SSOS 起動側と一致しているか確認（EPS 特に）

---

## Service call パース失敗（Jazzy）

### 症状

`request_co2` / `request_o2` が常に `success=False` だが、手動 `ros2 service call` は成功。

### 原因

Jazzy の `ros2 service call` 出力が YAML ではなく Python repr 形式。

### 対処

`Ros2EclssBridge` は両形式をパース（Phase 1b 修正済）。最新 `feat/ssos-eclss-loop` を使用。

手動確認:

```bash
ros2 service call /ars/request_co2 space_station_interfaces/srv/Co2Request "{amount: 25.0}"
```

---

## SSOS コンテナが見つからない

### 症状

```
SSOS container 'ssos' is not running.
```

### 対処

```bash
docker ps -a | grep ssos
docker start ssos && docker exec -it ssos bash

# 別名の場合
SSOS_CONTAINER=my_ssos ./scripts/run_ssos_eclss_smoke.sh
```

---

## EPS: discharge が arm されない / support_w が 0

### 症状

`request_discharge(100, 3)` は success だが `consume_scheduled_support()` が 0 を返す。

### 原因（Phase 3a interim）

- BCDU がまだ `discharging` モードに入っていない（SSU 電圧閾値未達）
- `ROS_DOMAIN_ID` 不一致で `/bcdu/status` が読めない
- EPS launch 未起動

### 対処

```bash
export ROS_DOMAIN_ID=23   # SSOS 側と一致
ros2 topic echo /bcdu/status space_station_interfaces/msg/BCDUStatus --once
ros2 topic echo /solar_controller/ssu_voltage_v std_msgs/msg/Float64 --once
```

bridge は BCDU `discharging` 時に `current_draw × bus_voltage` を live `support_w` として使用。未 discharge 時は armed 値にフォールバック。

---

## Daemon / zombie プロセス

### 症状

過去の `ros2 daemon` や headless launch が残り、ポート競合・古いグラフ参照。

### 対処（コンテナ内）

```bash
# 起動中 launch を Ctrl+C
ros2 daemon stop
ros2 daemon start
# 必要ならコンテナ再起動
docker restart ssos
```

---

## pytest 失敗

```bash
pip install -e ".[dev]"
pytest --ignore=tests/e2e   # 205 passed / 4 skipped 前後を期待
pytest tests/environment/ -v
```

Docker 不要のテストが大半。skip される ROS 統合テストは 2–4 件あり得ます。

---

## SSOS コンテナ回帰テストの失敗

### 症状

- `ERROR: Tier 2 requires docker.`
- `ERROR: smoke scripts.ssos_eclss_ars_smoke failed`
- Tier 2 中の `ros2 graph is empty`
- CI の `ssos-e2e` ジョブが self-hosted ランナーで失敗

### Tier 1 と Tier 2 の切り分け

| 症状 | 想定 tier | 対処 |
| --- | --- | --- |
| ローカルで `Tier 2 skipped` | `SSOS_E2E=1` 未設定（正常） | 実機連鎖には `SSOS_E2E=1` を設定 |
| Docker 無しで pytest 失敗 | Tier 1 | 単体/シナリオテストを先に修正 |
| smoke タイムアウト / 空グラフ | Tier 2 | SSOS イメージの pull を確認。個別 smoke の `--wait-timeout` を延長 |

### ローカル Tier 2 チェックリスト

```bash
# 1. Docker 利用可能か
docker ps

# 2. フル回帰（管理コンテナを自動作成）
SSOS_E2E=1 ./scripts/run_ssos_regression.sh

# 3. 既存コンテナ ssos を再利用
SSOS_E2E=1 SSOS_CONTAINER=ssos ./scripts/run_ssos_regression.sh --use-existing

# 4. 成果物の確認
ls artifacts/ssos-regression/*/
```

管理コンテナはデフォルトで `SSOS_CONTAINER_REPO=/ea`、`ROS_DOMAIN_ID=23`（`scripts/lib/ssos_docker.sh`）。新規 `ghcr.io` イメージでヘッドレス起動が失敗する場合は `/root/ssos-eclss-headless.sh` の有無を確認するか、`SSOS_HEADLESS_SCRIPT` を設定してください。

### CI について

- PR では **pytest のみ**（`tests/e2e/test_ssos_regression.py::test_regression_tier1_pytest_only` を含む）。
- 実機 Tier 2 は **workflow_dispatch** または週次 cron で実行（全 PR ではない。self-hosted `ssos` ランナー + Docker + SSOS イメージが必要）。
- Tier 2 実行時、レポートは `ssos-regression-reports` アーティファクトにアップロードされます。

---

## それでも解決しない場合

1. smoke レポート JSON（`--json-out`）の `errors` 配列を確認
2. コンテナ内で該当 Phase の手動コマンドを実行（[ECLSS 統合](eclss-integration.md)、[EPS 統合](eps-integration.md)）
3. 開発メモ: [SSOS ECLSS 接合プラン](../memo/ssos_eclss_loop/ssos_eclss_loop_connection_plan.md)
