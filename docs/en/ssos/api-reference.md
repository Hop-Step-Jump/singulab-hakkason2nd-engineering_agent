
# API Reference

Key methods on the `EclssBackend` and `EpsBackend` Protocols. Source docstrings are authoritative for implementation details.

---

## EclssBackend

**Definition**: `src/environment/ssos/eclss/backend.py`

ECLSS operation interface replacing Crew Simulation. Phase 1b covers ARS+OGS; Phase 2 adds WRS.

### poll_telemetry() → EclssTelemetrySnapshot

Fetch the latest snapshot from ROS 2 topics. `Ros2EclssBridge` converts SSOS topic **grams** to snapshot **kg**; see [ECLSS integration — Units and conversions](eclss-integration.md#units-and-conversions).

| Field | Source topic | Unit (snapshot) |
| --- | --- | --- |
| `co2_storage_kg` | `/co2_storage` | kg |
| `o2_storage_kg` | `/o2_storage` | kg |
| `product_water_reserve_l` | `/wrs/product_water_reserve` | L |
| `ars_diagnostics` | `/ars/diagnostics` | str / dict |
| `ogs_diagnostics` | `/ogs/diagnostics` | str / dict |
| `wrs_diagnostics` | `/wrs/diagnostics` | str / dict |

**Mock**: synthesized from internal state. **Ros2**: `ros2 topic echo --once`

---

### send_air_revitalisation_goal(goal: ArsGoal) → ActionResult

| Item | Value |
| --- | --- |
| Action name | `air_revitalisation` |
| Type | `space_station_interfaces/action/AirRevitalisation` |
| Goal fields | `initial_co2_mass`, `initial_moisture_content`, `initial_contaminants` |

---

### send_oxygen_generation_goal(goal: OgsGoal) → ActionResult

| Item | Value |
| --- | --- |
| Action name | `oxygen_generation` |
| Type | `space_station_interfaces/action/OxygenGeneration` |
| Goal fields | `input_water_mass`, `iodine_concentration` |

---

### send_water_recovery_goal(goal: WrsGoal) → ActionResult

| Item | Value |
| --- | --- |
| Action name | `water_recovery_systems` |
| Type | `space_station_interfaces/action/WaterRecovery` |
| Goal fields | `urine_volume` |

Phase 2 onward. Implemented in both Mock and Ros2.

---

### request_o2(amount: float) → ServiceResult

| Item | Value |
| --- | --- |
| Service | `/ogs/request_o2` |
| Type | `space_station_interfaces/srv/O2Request` |
| Request | `{amount: <float>}` |

---

### request_co2(amount: float) → ServiceResult

| Item | Value |
| --- | --- |
| Service | `/ars/request_co2` |
| Type | `space_station_interfaces/srv/Co2Request` |
| Request | `{amount: <float>}` |

Used to supply CO₂ feedstock before OGS (Sabatier).

---

### request_product_water(liters: float) → ServiceResult

| Item | Value |
| --- | --- |
| Service | `/wrs/product_water_request` |
| Type | `space_station_interfaces/srv/RequestProductWater` |

---

### submit_grey_water(liters: float) → ServiceResult

| Item | Value |
| --- | --- |
| Service | `/grey_water` |
| Type | `space_station_interfaces/srv/GreyWater` |

---

### set_subsystem_failure(subsystem: str, enabled: bool) → None

| subsystem | Topic |
| --- | --- |
| `"ars"` | `/ars/self_diagnosis` |
| `"ogs"` | `/ogs/self_diagnosis` |
| `"wrs"` | `/wrs/self_diagnosis` |

Publishes `std_msgs/Bool`. For verification and fault injection.

---

### Implementation Classes

| Class | File | Use |
| --- | --- | --- |
| `MockEclssBackend` | `eclss/mock/backend.py` | pytest / contract tests |
| `LoopMockEclssBackend` | `scenario/ssos_eclss_loop/loop_mock_backend.py` | `ssos_eclss_loop` mock dynamics |
| `PlantSimEclssBackend` | `eclss/plant_sim/backend.py` | Mass-balance plant (`--backend plant_sim`) |
| `Ros2EclssBridge` | `eclss/ros2/bridge.py` | SSOS Docker |

Paths are under `src/environment/ssos/` unless noted.

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

**Definition**: `src/environment/scrubber/eps/backend.py` (scrubber scenario; not wired into `ssos_eclss_loop`)

EPS telemetry reads and discharge scheduling (supports `request_eps_boost`).

### poll_solar() → SarjReading

| Field | SSOS topic |
| --- | --- |
| `solar_voltage_v` | `/solar_controller/ssu_voltage_v` |
| `beta_angle_deg` | `/solar_controller/sun_beta_deg` |
| `in_eclipse` | Inferred from voltage threshold |

---

### poll_bcdu() → BcduStatus

Single read of `/bcdu/status`. Mock uses internal state; Ros2 uses CLI echo + parse.

---

### tick_bcdu() → BcduStatus

One simulation step equivalent. On the Ros2 bridge:

- Re-read BCDU
- Decrement `support_steps_remaining`
- Clear armed watts when it reaches 0

---

### request_discharge(support_w: float, duration_steps: int) → DischargeResult

| Validation | Condition |
| --- | --- |
| support_w | `(0, max_discharge_w]` (default 500 W) |
| duration_steps | `>= 1` |
| fault | `success=False` when BCDU fault |

**Ros2EpsBridge (Phase 3a)**: Does not send a direct discharge command to SSOS; arms a local timer. Live watts are estimated from BCDU telemetry.

---

### consume_scheduled_support() → float

Support watts to add to ECLSS for the current step.

Priority:

1. BCDU `discharging` and `current_draw × bus_voltage > 0`
2. Armed `support_w` (timer remaining)
3. `0.0`

---

### Properties

| Property | Type | Description |
| --- | --- | --- |
| `support_w` | `float` | Current support power [W] |
| `support_steps_remaining` | `int` | Remaining step count |
| `bcdu_mode` | `BcduMode` | IDLE / CHARGING / DISCHARGING / … |

---

### Implementation Classes

| Class | File | Selection |
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

## Related Types

| Type | File |
| --- | --- |
| `EclssTelemetrySnapshot`, `ActionResult`, `ServiceResult` | `ssos/eclss/types.py` |
| `BcduStatus`, `DischargeResult`, `SarjReading` | `scrubber/eps/types.py` |
| `EclssLoopObservation`, `EclssOperationalCommand` | `scenario/agents/eclss_loop_types.py` |

---

## Related Documentation

- [ECLSS Integration](eclss-integration.md)
- [EPS Integration](eps-integration.md)
- [api-contracts.md](../api-contracts.md) — JSONL schema (scrubber track)
