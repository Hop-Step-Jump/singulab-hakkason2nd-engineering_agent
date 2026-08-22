# 乗員サバイバル（`plant_sim`）

実装済みの設計である。タンクが支えられないとき、乗員と運用エージェントは同じ人数に減る。Cursor の 3 プラン（物理下限 → 帯滞在 → CO2 分数減）を `src/scenario/ssos_eclss_loop/` と `src/environment/ssos/eclss/plant_sim/` にまとめた結果である。

サバイバルは **`plant_sim` バックエンドだけ**。`mock` / `ros2` では帯滞在も物理下限も適用しない。チートシート / 感度アプリは `plant_sim.survival.enabled: false` のまま。

人数の正本は `src/scenario/ssos_eclss_loop/scenario.yaml` の `plant_sim.crew.size`。actor ありのときは `agents.yaml` の `actor.team.count` と一致させる。減った乗員は戻らない。**designer は `crew_alive` と一緒に減らない**（全滅後も提案する）。[事後設計エージェント](post_run_design_agent.md)。

## 最初の floor だけでは足りなかった理由

当初の `PlantModel.apply_capacity_drop` は、**次の 20 分インターバルを払える人数**まで全員残した（`floor(タンク / 1人需要)`）。O2 タンクが小さくても人ステップ数は大きいので、大人数はタンクがほぼ空になるまで残り、そのあと一気に落ちた。

帯滞在は **運用ストレスのポリシー**（ARS/OGS/WRS と同じヘルス帯に居続けるコスト）。物理下限は質量収支を無視しないための **ハードキャップ** として残す。

## パイプライン（各ステップの操作のあと）

```text
操作後の在庫
  → ヘルス帯（labeled_rule_base と同じ `thresholds`）
  → SurvivalDwellPolicy.apply_dwell
  → backend.set_crew_alive
  → apply_capacity_drop  （次ステップの O2/水。最終ステップはスキップ）
  → team.set_crew_alive
```

最終ステップには続く `advance_step` がないので look-ahead の floor はスキップする（`physics_floor=step + 1 < steps`）。帯滞在は最終ステップでも走る。

シナリオは `model.state` を直接書かない。

## ヘルス帯（シナリオ既定）

運用トリガーとサバイバル帯は **同じ YAML キー**。いまの `ssos_eclss_loop` 既定（乗員 50）:

| 資源 | SAFE | WARNING | CRITICAL |
| --- | --- | --- | --- |
| Cabin CO2 (kg) | < 2.0 | 2.0 以上 8.0 未満 | ≥ 8.0 |
| O2 (kg) | > 6.0 | 1.0 〜 6.0 | ≤ 1.0 |
| 製品水 (L) | > 50 | 25 〜 50 | ≤ 25 |

`o2_storage_critical_kg` と `product_water_critical_l` は YAML に明示する。省略時のヘルスフォールバックは `low * 0.75` と `low * 0.5`。

既定タンクは O2・水とも **SAFE から開始**する。`initial_o2_storage_kg` は 8.0（LOW 6.0 より上）、`initial_product_water_l` は 80.0（LOW 50 より上）。cabin CO2 は 1.3 kg（HIGH 2.0 未満）。既定の `simulation.steps` は 50。

## 帯滞在（`survival.py`）

YAML は `plant_sim.survival`。CRITICAL 中は同じ資源の WARNING 連続カウンタを増やさない。

### O2 と水（固定人数）

| 帯 | 連続ステップ | 減員 | 減員後 |
| --- | --- | --- | --- |
| O2 WARNING | 2 | 1 人 | カウンタリセット。さらに 2 ステップでまた −1 |
| O2 CRITICAL | 1 | 2 人 | カウンタリセット |
| 水 WARNING | 2 | 1 人 | O2 WARNING と同じ |
| 水 CRITICAL | 1 | 1 人 | カウンタリセット |
| SAFE へ退出 | — | — | その資源のカウンタをリセット |

### CO2（分数、滞在につき一度）

| 帯 | 連続ステップ | 減員 | 再発火 |
| --- | --- | --- | --- |
| WARNING（HIGH） | 2 | `n // 4` | 帯を出て再入場するまで再発火しない |
| CRITICAL | 2 | `n // 2` | 同様。**全滅しない** |

乗員 1 人では `1 // 4` も `1 // 2` も 0 なので、CO2 帯だけでは最後の 1 人は減らない。50 人の例: HIGH に 2 ステップ → 50→38。CRITICAL に 2 ステップ → 38→19。

### 同一ステップの重ね打ち

資源ごとに **要求減員**を独立計算。適用は `lost = min(alive, sum(requests))`。原因のスライスは次の順（高い方が先）:

1. `co2_critical`
2. `co2_warning`
3. `o2_critical`
4. `water_critical`
5. `o2_warning`
6. `water_warning`

イベントの `limiting` は要求した要因をすべて列挙。`crew_lost_by_cause` はスライスした人数であり、合計を全要因にコピーしない。

## 物理下限（`apply_capacity_drop`）

**次の**代謝インターバルを O2 と水で払える人数だけ残す。**cabin CO2 ではここでは減員しない**（残すと CO2 CRITICAL 滞在が見えない）。イベントは `o2_physics` / `water_physics` / `co2_physics`（CO2 wipe オフのあいだ最後は未使用）。O2 と水が同時に下限なら減員人数は O2 に帰属する。

## 成果物

| 場所 | 内容 |
| --- | --- |
| `events.jsonl` | `/eclss/events/crew_lost`（`lost`, `remaining`, `limiting`, `crew_lost_by_cause`, `agent_ids`） |
| `summary.json` | `crew_initial`, `crew_remaining`, `crew_lost`, `crew_lost_by_cause` |
| `telemetry.jsonl` | `raw_topics.plant_sim.crew_alive` / `survival.lost_this_step`（そのステップの帯+物理） |
| ダッシュボード | plant_sim ledgers の乗員数時系列 |

## 試し方（`plant_sim` のみ）

```bash
python3 -m tools.cli run ssos_eclss_loop \
  --backend plant_sim --actor-mode labeled_rule_base --steps 50 \
  --run-id survival-try
```

`--actor-mode none` だと帯に居座りやすく、dwell が見やすい。OGS/ARS/WRS は WARNING から出せる。

## コード

| パス | 役割 |
| --- | --- |
| `src/scenario/ssos_eclss_loop/survival.py` | 滞在表、連続カウンタ、重ね打ち |
| `src/scenario/ssos_eclss_loop/scenario_run.py` `_apply_survival_after_ops` | dwell のあと floor |
| `src/environment/ssos/eclss/plant_sim/model.py` `apply_capacity_drop` | O2/水 floor |
| `src/environment/ssos/eclss/plant_sim/backend.py` `set_crew_alive` | シナリオ → プラント |
| `src/scenario/ssos_eclss_loop/health.py` | 閾値から WARNING/CRITICAL |
| `tests/scenario/test_ssos_eclss_loop_survival.py` | dwell の表テスト |

プラントの質量収支（サバイバル以外）は [plant_sim_backend.md](plant_sim_backend.md)。designer は別チーム: [事後設計エージェント](post_run_design_agent.md)。
