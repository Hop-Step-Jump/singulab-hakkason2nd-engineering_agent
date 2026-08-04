# ssos_eclss_loop — コンテナ ros2 E2E 記録

**日付**: 2026-06-14  
**環境**: Docker `ssos`、SSOS headless 起動済み、`ea-loop`（`d62ca77` sync 後）

## labeled_rule_base + ros2

コマンド:

```bash
ea-loop --agents-mode labeled_rule_base --output-dir /tmp/e2e_labeled_ros2
```

| 項目 | 結果 |
|------|------|
| `backend` | `ros2` |
| `operational_command_count` | **2** |
| `ogs_invoked_step` | 0 |
| `co2_requested_step` | 0 |
| telemetry topics | `/co2_storage`, `/o2_storage`, `/wrs/product_water_reserve` |

**events.jsonl（step 0）**:

- `request_co2` — applied（SSOS: `Insufficient CO₂ in storage` — 実機 CO₂=0 kg）
- `oxygen_generation` — **SUCCEEDED**（`total_o2_generated: ~8.9 kg`）

**注**: 実機 SSOS は CO₂ storage=0、O₂=26.7 kg のため **OGS 経路**が発火。mock 想定の CO₂ ≥ `co2_storage_high_kg`（1.5 kg）→ ARS 経路ではなかった。

成果物: `labeled_rule_base_ros2_summary.json`, `labeled_rule_base_ros2_events.jsonl`

## llm + ros2

コマンド:

```bash
ea-loop --agents-mode llm --output-dir /tmp/e2e_llm_ros2 --steps 3
```

| 項目 | 結果 |
|------|------|
| `backend` | `ros2` |
| Ollama | `host.docker.internal:11434` / `gemma4:e4b` — **接続成功** |
| `message_count` | 12（deliberation ×3 + action skip ×3） |
| `operational_command_count` | 0（LLM が hold を選択 — CO₂=0 の状況判断） |
| `design_proposals` | `decision_source: llm`、valid JSON（`changes: []`） |

**注**: インフラ E2E（ros2 telemetry + Ollama + deliberation + post-run design）は成功。operational 発火は plant 状態依存。

成果物: `llm_ros2_summary.json`, `llm_ros2_design_proposals.json`
