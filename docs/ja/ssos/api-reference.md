# API リファレンス

`EclssBackend` と `EpsBackend` Protocol の主要メソッドです。実装詳細はソース docstring を正とします。

---

## EclssBackend

**定義**: `src/environment/ssos/eclss/backend.py`

Crew Simulation 代替の ECLSS 操作インターフェース。Phase 1b で ARS+OGS、Phase 2 で WRS をカバー。

### poll_telemetry() → EclssTelemetrySnapshot

ROS 2 トピックから最新スナップショットを取得。`Ros2EclssBridge` は SSOS トピックの **グラム** をスナップショットの **kg** に変換する（[ECLSS 統合 — Units and conversions](eclss-integration.md#units-and-conversions)）。

| フィールド | ソース topic | 単位（スナップショット） |
| --- | --- | --- |
| `co2_storage_kg` | `/co2_storage` | kg |
| `o2_storage_kg` | `/o2_storage` | kg |
| `product_water_reserve_l` | `/wrs/product_water_reserve` | L |
| `ars_diagnostics` | `/ars/diagnostics` | str / dict |
| `ogs_diagnostics` | `/ogs/diagnostics` | str / dict |
| `wrs_diagnostics` | `/wrs/diagnostics` | str / dict |

**Mock**: 内部状態から合成。**Ros2**: `ros2 topic echo --once`

---

### send_air_revitalisation_goal(goal: ArsGoal) → ActionResult

| 項目 | 値 |
| --- | --- |
| Action 名 | `air_revitalisation` |
| 型 | `space_station_interfaces/action/AirRevitalisation` |
| Goal フィールド | `initial_co2_mass`, `initial_moisture_content`, `initial_contaminants` |

---

### send_oxygen_generation_goal(goal: OgsGoal) → ActionResult

| 項目 | 値 |
| --- | --- |
| Action 名 | `oxygen_generation` |
| 型 | `space_station_interfaces/action/OxygenGeneration` |
| Goal フィールド | `input_water_mass`, `iodine_concentration` |

---

### send_water_recovery_goal(goal: WrsGoal) → ActionResult

| 項目 | 値 |
| --- | --- |
| Action 名 | `water_recovery_systems` |
| 型 | `space_station_interfaces/action/WaterRecovery` |
| Goal フィールド | `urine_volume` |

Phase 2 以降。Mock / Ros2 両方実装。

---

### request_o2(amount: float) → ServiceResult

| 項目 | 値 |
| --- | --- |
| Service | `/ogs/request_o2` |
| 型 | `space_station_interfaces/srv/O2Request` |
| Request | `{amount: <float>}` |

---

### request_co2(amount: float) → ServiceResult

| 項目 | 値 |
| --- | --- |
| Service | `/ars/request_co2` |
| 型 | `space_station_interfaces/srv/Co2Request` |
| Request | `{amount: <float>}` |

OGS（Sabatier）前の CO₂ 原料供給に使用。

---

### request_product_water(liters: float) → ServiceResult

| 項目 | 値 |
| --- | --- |
| Service | `/wrs/product_water_request` |
| 型 | `space_station_interfaces/srv/RequestProductWater` |

---

### submit_grey_water(liters: float) → ServiceResult

| 項目 | 値 |
| --- | --- |
| Service | `/grey_water` |
| 型 | `space_station_interfaces/srv/GreyWater` |

---

### set_subsystem_failure(subsystem: str, enabled: bool) → None

| subsystem | Topic |
| --- | --- |
| `"ars"` | `/ars/self_diagnosis` |
| `"ogs"` | `/ogs/self_diagnosis` |
| `"wrs"` | `/wrs/self_diagnosis` |

`std_msgs/Bool` を publish。検証・異常注入用。

---

### 実装クラス

| クラス | ファイル | 用途 |
| --- | --- | --- |
| `MockEclssBackend` | `eclss/mock/backend.py` | pytest / 契約テスト |
| `LoopMockEclssBackend` | `scenario/ssos_eclss_loop/loop_mock_backend.py` | `ssos_eclss_loop` mock dynamics |
| `PlantSimEclssBackend` | `eclss/plant_sim/backend.py` | 物質収支プラント（`--backend plant_sim`） |
| `Ros2EclssBridge` | `eclss/ros2/bridge.py` | SSOS Docker |

パスは特記なき限り `src/environment/ssos/` 配下。

```python
from environment.ssos.eclss import MockEclssBackend, Ros2EclssBridge
from environment.ssos.eclss.types import ArsGoal, OgsGoal

backend = MockEclssBackend()
snap = backend.poll_telemetry()
backend.send_air_revitalisation_goal(ArsGoal())
backend.send_oxygen_generation_goal(OgsGoal())
backend.request_co2(100.0)
```

---

## EpsBackend

**定義**: `src/environment/scrubber/eps/backend.py`（scrubber シナリオ。`ssos_eclss_loop` には未接続）

EPS テレメトリ読取と放電スケジュール（`request_eps_boost` の下支え）。

### poll_solar() → SarjReading

| フィールド | SSOS topic |
| --- | --- |
| `solar_voltage_v` | `/solar_controller/ssu_voltage_v` |
| `beta_angle_deg` | `/solar_controller/sun_beta_deg` |
| `in_eclipse` | 電圧閾値から推定 |

---

### poll_bcdu() → BcduStatus

`/bcdu/status` を 1 回読取。Mock は内部状態、Ros2 は CLI echo + parse。

---

### tick_bcdu() → BcduStatus

シミュレーション 1 step 相当。Ros2 bridge では:

- BCDU 再読取
- `support_steps_remaining` をデクリメント
- 0 になったら armed watts をクリア

---

### request_discharge(support_w: float, duration_steps: int) → DischargeResult

| 検証 | 条件 |
| --- | --- |
| support_w | `(0, max_discharge_w]`（デフォルト 500 W） |
| duration_steps | `>= 1` |
| fault | BCDU fault 時は `success=False` |

**Ros2EpsBridge（Phase 3a）**: SSOS への直接 discharge コマンドは送らず、ローカルタイマーで arm。live watt は BCDU telemetry から推定。

---

### consume_scheduled_support() → float

現在 step で ECLSS に加算すべき support watts。

優先順:

1. BCDU `discharging` かつ `current_draw × bus_voltage > 0`
2. armed `support_w`（タイマー残あり）
3. `0.0`

---

### プロパティ

| プロパティ | 型 | 説明 |
| --- | --- | --- |
| `support_w` | `float` | 現在の支援電力 [W] |
| `support_steps_remaining` | `int` | 残り step 数 |
| `bcdu_mode` | `BcduMode` | IDLE / CHARGING / DISCHARGING / … |

---

### 実装クラス

| クラス | ファイル | 選択 |
| --- | --- | --- |
| `MockEpsBackend` | `scrubber/eps/mock/backend.py` | `eps.backend: mock` |
| `Ros2EpsBridge` | `ssos/eps/ros2/bridge.py` | `eps.backend: ssos_eps` |

```python
from scenario.runner import build_eps_backend

config = {"eps": {"backend": "mock", "sarj": {"beta_angle_deg": 45.0}}}
eps = build_eps_backend(config)
eps.request_discharge(120.0, duration_steps=5)
watts = eps.consume_scheduled_support()
```

---

## 関連型

| 型 | ファイル |
| --- | --- |
| `EclssTelemetrySnapshot`, `ActionResult`, `ServiceResult` | `ssos/eclss/types.py` |
| `BcduStatus`, `DischargeResult`, `SarjReading` | `scrubber/eps/types.py` |
| `EclssLoopObservation`, `EclssOperationalCommand` | `scenario/agents/eclss_loop_types.py` |

---

## 関連ドキュメント

- [ECLSS 統合](eclss-integration.md)
- [EPS 統合](eps-integration.md)
- [api-contracts.md](../api-contracts.md) — JSONL スキーマ（scrubber 系）
