# Engineering Agents — ECLSS レジリエンス・ループ

**→ [クイックスタート](index.md)** — インストール、初回シミュレーション、結果ファイルの場所

**ECLSS**（Environmental Control and Life Support System / 環境制御・生命維持システム）の異常に対し、**エージェントチームが検知・対応し、事後に設計変更を提案する**までをシミュレートする研究用リポジトリです。ECLSS は物理実験装置ではなく、乗員の生存に必要な**生命維持装置**を指します。

本リポジトリは **二系統のシナリオ** を持ちます。

- **`scrubber_degradation`** — Python モック（`StationSimulator`）上の CO₂ スクラバー異常。生命維持プラント（ECLSS）と電力系（**EPS**）を再現し、ROS2 風トピック契約でエージェントと接続します。
- **`ssos_eclss_loop`** — **Space Station OS（SSOS）** Docker 内の実 ROS2 ECLSS（`Ros2EclssBridge`）へ接続。ARS/OGS/WRS の運用と事後 `ssos_graph` 設計提案を検証します（Phase 0–7 完了）。

いずれも将来の宇宙ステーション運用ソフトウェア（SSOS）との接合を見据えた研究用実装です。

自律的なハードウェア設計の**一つ手前**として、「運用中の異常 → チームの判断 → 恒久設計の提案」というループを検証するのが目的です。

---

## 二つのシナリオ

| | [scrubber_degradation](scenario-scrubber-degradation.md) | [ssos_eclss_loop](scenario-ssos-eclss-loop.md) |
| --- | --- | --- |
| 目的 | Mock 上の CO₂ スクラバー異常と EPS 連動 | SSOS 実 ROS2 ECLSS の運用代替（Crew Simulation 置換） |
| バックエンド | `StationSimulator` | `EclssBackend`（mock / plant_sim / `Ros2EclssBridge`） |
| テレメトリ | CO₂ ppm、電力マージン | CO₂/O₂/水ストレージ（kg / L） |
| ランタイム | 回復コマンド（ファン、EPS ブースト） | 運用コマンド（ARS、OGS、request_co2） |
| 事後提案 | scrubber トポロジ | `ssos_graph`（action_profile、graph_rewire） |

---

## 一目でわかる（ダッシュボード） { #一目でわかるダッシュボード }

シミュレーション結果は JSONL に記録され、[Streamlit ダッシュボード](#ダッシュボード) で確認できます。`scrubber_degradation` は CO₂ ppm・EPS・トポロジ Before/After、`ssos_eclss_loop` はストレージ kg・運用タイムライン・`ssos_graph` 設計提案を表示します。

### 1. Overview — 2 ランの並列比較（scrubber）

同じ `scrubber_degradation` 異常に対し、**異なる LLM エージェント**（例: `qwen2.5` vs `gemma4:e4b`）がどう違う軌道を描くかを step 単位で比較します。CO2 ppm・電力マージン・EPS 支援・スクラバー効率のプロットが横並びで並び、モデル間のトレードオフ（CO2 抑制 vs 電力消費など）が一目でわかります。

<p align="center">
  <img src="../../images/dashboard-overview-compare.png" alt="ECLSS Resilience Dashboard — Overview で 2 つの LLM run を step 49 で横並び比較" width="900"/>
</p>

### 2. 設計提案 — トポロジの Before / After

ラン終了後、代表エージェントが **恒久設計変更** を提案します。左はバイパス弁（`bypass_valve`）の追加、右は非常電源（`emergency_power_source`）の追加といった案で、赤破線が提案エッジ、ノード表の `proposed` 列が新規部品を示します。

<p align="center">
  <img src="../../images/dashboard-topology-proposals.png" alt="設計提案 — バイパス弁と非常電源の 2 つのトポロジ変更案" width="900"/>
</p>

### 3. Step replay — ステップ単位の詳細再生

1 run を step ごとに追い、**タイムライン**（回復コマンドの適用）、**エージェント発言**、**reasoning**（状況判断の根拠）、**テレメトリプロット**（現 step の縦線マーカー）を同期表示します。下図は step 17 で `request_eps_boost` が適用された瞬間の例です。

<p align="center">
  <img src="../../images/dashboard-step-replay.png" alt="Step replay — scrubber_degradation_llm の step 17、EPS ブースト適用とエージェント reasoning" width="900"/>
</p>

### ssos_eclss_loop — ストレージと運用タイムライン

`ssos_eclss_loop` の run を選ぶと、ダッシュボードは **CO₂ / O₂ / 製品水のストレージ kg** プロット、ヘルスカード（safe / warning / critical）、**運用タイムライン**（`air_revitalisation`、`oxygen_generation`、`request_co2` 等の `operational_applied`）を表示します。2 run 比較で labeled と LLM、または異なるモデルの運用タイミングの差を追えます。事後の `ssos_graph` 設計提案（`action_profile`、`graph_rewire`）も Step replay から確認できます。

詳細: [scenario-ssos-eclss-loop.md](scenario-ssos-eclss-loop.md#ダッシュボードでの見方)。

---

## なぜこのシミュレーションか

### scrubber_degradation（Mock 実験）

宇宙ステーションでは、CO2 除去（スクラバー）や電力マージンの悪化が連鎖すると、乗員の安全に直結します。現実では：

1. テレメトリで異常を検知する  
2. 運用チームが状況を共有し、一時的な回復操作を打つ  
3. 恒久対策としてハードウェア／配管／電源の設計変更を検討する  

[`scrubber_degradation`](scenario-scrubber-degradation.md) では step 20 からスクラバー効率が落ち、CO2 と電力マージンが悪化します。エージェントはランタイム中に回復コマンドを出し、**ラン終了後**にトポロジ変更案を `design_proposals.json` に残します。

### ssos_eclss_loop（SSOS 実 ECLSS）

SSOS の ECLSS は、閉鎖環境の **CO₂ 除去（ARS）**、**O₂ 生成（OGS）**、**水回収（WRS）** を ROS2 Action / Service で操作します。従来の Crew Simulation の代わりに、エージェントチームが同じインターフェースを叩くことを検証します。

[`ssos_eclss_loop`](scenario-ssos-eclss-loop.md) では:

1. `/co2_storage`・`/o2_storage` 等のストレージを毎 step 監視する  
2. 閾値超過時に ARS / OGS（および Sabatier 用 `request_co2`）を運用コマンドとして発行する  
3. ラン終了後、`action_profile` や `graph_rewire` 等の恒久案を `design_proposals.json`（`ssos_graph`）に残す  

**ros2** モードは SSOS Docker 内の実プラントに接続します。**mock** モードはホストのみで pytest / 開発に使えます（簡易ストレージ動態）。

---

## なぜ LLM か（ルールベースとの違い）

両シナリオとも `agents.mode` は `none` / `labeled_rule_base` / `llm`。**同種 N 体 + 代表 action** のチーム設計は共通です（scrubber: `engineer_*`、ssos: `eclss_operator_*`）。

| | `labeled_rule_base` | `llm` |
| --- | --- | --- |
| 判断の源泉 | `policy` / 閾値（scrubber: CO₂ ppm、ssos: ストレージ kg） | Persona + テレメトリ + チーム発言（**policy は読まない**） |
| 議論 | ルールが決めた定型メッセージ | 同種 N 体が 1 ラウンド deliberation |
| 行動 | 代表が閾値に応じてコマンド | 代表が LLM 出力の `commands` を実行 |
| scrubber ランタイム | 回復コマンド（ファン、EPS ブースト） | 同上 |
| ssos ランタイム | 運用コマンド（ARS、OGS、request_co2） | 同上 |
| 再現性 | 高い（回帰テスト向き） | モデル・温度に依存（比較実験向き） |

ルールベースは **「正しい挙動の足場」** です。LLM モードは、固定閾値では表現しきれない **状況理解・チーム合意・回復タイミングの違い** を観察するための実験モードです。LLM 設計で重要だった点は次のとおりです（詳細は [homogeneous agent team plan](memo/agents/homogeneous_agent_team_plan.md)）。

- **Persona とシナリオの分離** — 閾値や数値はプロンプトの `### Telemetry` / `### World state` にだけ載せる  
- **同種 N 体 + 代表 action** — 役割の硬直を避け、step ごとに発言者と実行者をローテーション  
- **ランタイム中はトポロジ変更しない** — シミュレーションと設計提案を分離し、One Piece provenance と整合  
- **policy を LLM から隔離** — ルールの答えをプロンプトに混ぜず、比較実験を可能にする  

---

## シミュレーション世界（用語）

### scrubber_degradation

| 略称 | 英語名 | 説明 |
| --- | --- | --- |
| **ECLSS** | Environmental Control and Life Support System | **生命維持装置**。CO2 スクラバー・送気配管・居住空間 |
| **EPS** | Electrical Power System | 発電・蓄電・配電。SARJ/BCDU モックを通じ ECLSS へ電力支援 |
| **テレメトリ** | — | CO2 ppm、スクラバー効率、電力マージン、EPS 支援ワット |
| **回復コマンド** | — | 一時操作（ファン加速、負荷削減、EPS ブースト、バイパス） |
| **設計提案** | — | ラン終了後の恒久変更（ノード／エッジ追加） |

**ヘルス閾値**: CO2 safe < 800 / warning < 1200 / critical ≥ 1200 ppm；電力マージン safe > 0 / warning > −150 / critical ≤ −150 W。

#### デフォルトトポロジ

```
  [cabin] --flow--> [manifold] --flow--> [scrubber] --flow--> [cabin]
                                              ^
                                              | power
                                         [power_bus]
```

仕様: [scenario-scrubber-degradation.md](scenario-scrubber-degradation.md)。

### ssos_eclss_loop

| 略称 | 英語名 | 説明 |
| --- | --- | --- |
| **ARS** | Air Revitalisation System | CO₂ ストレージ除去（`air_revitalisation` Action） |
| **OGS** | Oxygen Generation System | O₂ 生成（`oxygen_generation`）。Sabatier に CO₂ feedstock が必要 |
| **WRS** | Water Recovery System | 水回収（`water_recovery_systems`）— ros2 ブリッジ実装済み |
| **テレメトリ** | — | `/co2_storage`、`/o2_storage`、`/wrs/product_water_reserve`（kg / L） |
| **運用コマンド** | — | ARS / OGS Action、`request_co2` / `request_o2` Service |
| **設計提案** | — | `ssos_graph`（`action_profile`、`graph_rewire` 等） |

**ヘルス閾値（ストレージ）**: CO₂ warning ≥ 2.0 kg / critical ≥ 8.0 kg；O₂ warning ≤ 6.0 kg / critical ≤ 1.0 kg。詳細は [scenario-ssos-eclss-loop.md](scenario-ssos-eclss-loop.md)。

#### SSOS ECLSS サブシステム（概念）

```
  代謝 CO₂ ──► /co2_storage ──► ARS (air_revitalisation)
                                    │
  /o2_storage ◄── OGS (oxygen_generation) ◄── request_co2 (Sabatier)
```

仕様: [scenario-ssos-eclss-loop.md](scenario-ssos-eclss-loop.md)。

### エージェントチーム（共通パターン）

| シナリオ | ID プレフィックス | デフォルト人数 | 代表 action |
| --- | --- | --- | --- |
| scrubber | `engineer` | 4 | `engineer_{(step-1) % N}` |
| ssos | `eclss_operator` | 3 | `eclss_operator_{step % N}`（0-based steps） |

各 step で全員が議論（llm）またはルール診断（labeled）。**事後設計**は最終 step の代表が `design_proposals.json` を出力。

---

## このリポジトリと SSOS / One Piece の位置づけ

```text
[ scrubber_degradation — Mock 完了 ]
  StationSimulator (MockEclss + EPS mock)
       ↑ SimulatorProtocol
  ScrubberDegradationTeam
       ↓ JSONL + design_proposals.json（scrubber）
  Streamlit dashboard / pytest

[ ssos_eclss_loop — Phase 0–7 完了 ]
  Ros2EclssBridge (SSOS Docker 内 ros2)
       ↑ EclssBackend
  SsosEclssLoopTeam (Team ABC)
       ↓ JSONL + design_proposals.json（ssos_graph）
  ea-loop / graph_rewire（client remap）/ ssos ダッシュボードビュー

[ 次・バックログ ]
  Phase 8 launch remap     … [backlog BL-003](memo/backlog.md#bl-003)
  design → provenance      … [development-plan.md](development-plan.md)
  One Piece Web UI         … スコープ外
```

| 領域 | 状態 | 参照 |
| --- | --- | --- |
| scrubber モックシミュレーション | **利用可能** | [architecture.md](architecture.md) |
| ssos_eclss_loop（実 ECLSS） | **利用可能**（Phase 0–7） | [connection plan](memo/ssos_eclss_loop/ssos_eclss_loop_connection_plan.md) |
| One Piece provenance | **部分完了**（回復 + 運用） | [one-piece-integration.md](one-piece-integration.md) |
| ROS launch remap（Phase 8） | バックログ | [development-plan.md](development-plan.md) |
| One Piece Web / SSOT UI | 未接続 | [one-piece-integration.md](one-piece-integration.md) |

開発途中のタスク・ロードマップ・研究メモは [docs/development-plan.md](development-plan.md) に集約しています。

---

## ドキュメント { #ドキュメント }

| ドキュメント | 対象読者 | 内容 |
| --- | --- | --- |
| [docs/architecture.md](architecture.md) | コントリビュータ | レイヤ構成、二系統実行フロー、エージェントモード、ダッシュボード |
| [docs/scenario-scrubber-degradation.md](scenario-scrubber-degradation.md) | デモ・分析 | scrubber 背景、設定、出力の読み方 |
| [docs/scenario-ssos-eclss-loop.md](scenario-ssos-eclss-loop.md) | SSOS 接合・デモ | ssos 背景、ARS/OGS 運用、Docker 実行、出力の読み方 |
| [docs/api-contracts.md](api-contracts.md) | インテグレータ | `SimulatorProtocol` / `EclssBackend`、JSONL、`design_proposals.json` |
| [docs/one-piece-integration.md](one-piece-integration.md) | 設計追跡 | provenance（回復・運用）、One Piece 連携の現状と予定 |
| [docs/development-plan.md](development-plan.md) | 開発者 | 完了マイルストーン、次タスク、ロードマップ、`docs/ja/memo/` 索引 |
| [memo/ssos_eclss_loop/](memo/ssos_eclss_loop/) | SSOS 接合 | ECLSS Phase 0–7 詳細、EPS ブリッジ、graph 調査 |

---

## 必要条件

- **Python 3.11+**
- **Git**
- **Ollama** または研究室 **vLLM**（`agents.mode: llm` を使う場合のみ）
- **SSOS Docker**（`ssos_eclss_loop` の **ros2** モードのみ）— [scenario-ssos-eclss-loop.md](scenario-ssos-eclss-loop.md#実行方法)

---

## インストール（ゼロから）

Python の mock シナリオはローカル環境で実行できます。SSOS の `ros2` / live smoke は
Linux コンテナ上の SSOS に接続するため、macOS でも Windows でも Docker を使います。

### 1. リポジトリを取得

```bash
git clone https://github.com/hirototamura/engineering_agents.git
cd engineering_agents
```

### 2A. macOS / Linux

macOS で検証済みの SSOS live 実行も、SSOS 本体は Docker 上の Linux コンテナで動かします。
ここでは、ローカルで使う Python 環境を準備します。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"
```

`pip install -e ".[dev]"` により `src/` 配下の `scenario`, `environment`, `core` などが import 可能になります。

### 2B. Windows PowerShell + Docker Desktop { #2b-windows-powershell--docker-desktop }

#### 2B-1. Python 環境を作る

PowerShell で実行します。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[dev]"
python -m pytest -q
```

#### 2B-2. Docker Desktop を入れる

Docker Desktop は WSL 2 backend で入れます。Windows Containers は使いません。

```powershell
wsl --status

curl.exe -L -o C:\tmp\DockerDesktopInstaller.exe `
  "https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe"
Start-Process C:\tmp\DockerDesktopInstaller.exe
```

このプロジェクトでの推奨選択は次のとおりです。

| Option | Selection | 理由 |
| --- | --- | --- |
| All-users installation | 有効 | 管理者承認が使える場合の無難な既定値です。 |
| Use WSL 2 instead of Hyper-V | 有効 | SSOS / ROS2 で使う Linux コンテナ向けの推奨 backend です。 |
| Allow Windows Containers | 無効 | このプロジェクトは Linux コンテナを使うため不要です。 |
| Add shortcut to desktop | 任意 | 利便性だけの設定です。 |

インストール後、Docker Desktop を起動して確認します。

```powershell
docker info --format "OSType={{.OSType}} OperatingSystem={{.OperatingSystem}}"
# OSType=linux OperatingSystem=Docker Desktop
docker run --rm hello-world
```

#### 2B-3. SSOS live smoke を実行する

`scripts/*.sh` は Git Bash から実行します。`SSOS_CONTAINER` は実行中の SSOS
コンテナ名に合わせます。

```powershell
$env:SSOS_CONTAINER = "ssos-regression-1807"
& "C:\Program Files\Git\bin\bash.exe" -lc "scripts/run_ssos_regression.sh --skip-pytest --use-existing --steps 3 --artifact-dir artifacts/ssos-regression/windows-wrapper-fixed-cli --keep-container"
```

期待結果: ARS、Phase 1b、Phase 2、graph_rewire smoke が通り、その後に短い
`ssos_eclss_loop` run が `backend: ros2` で実行されます。

補足:

- `python` が Microsoft Store を開く場合は、Windows の Python App Execution Alias を無効化するか、インストール済み Python のフルパスを指定します。
- PowerShell が `Activate.ps1` をブロックする場合は、`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` を一度だけ実行するか、`.\.venv\Scripts\python.exe` を直接呼び出します。
- `wsl --status` で WSL 未インストールの場合は、管理者 PowerShell で `wsl --install` を実行し、再起動後に Docker Desktop を起動します。
- Git Bash のパス変換、CRLF による `bash\r`、`rclpy` reader 終了時 abort は、この PR の wrapper / `.gitattributes` 側で対策しています。

### 3. 動作確認（テスト）

```bash
pytest
# scrubber 回帰
pytest tests/scenario/test_scrubber_baseline.py tests/scenario/test_scrubber_with_agents.py -q
# ssos / graph_rewire
pytest tests/scenario/test_ssos_eclss_loop*.py tests/environment/test_graph_rewire*.py -q
# または
python src/scripts/run_tests.py
```

### 4. LLM バックエンド（LLM モード用）

`agents.mode: llm` は次のいずれかが必要です。既定は **Ollama**。`--llm-provider vllm` または `LLM_PROVIDER=vllm` で切り替えます。

#### Ollama（ローカル）

[https://ollama.com](https://ollama.com) から Ollama をインストールし、デーモンを起動します。

```bash
# 例: agents.yaml で指定しているモデルを pull
ollama pull gemma4:e4b

# 別モデルで試す場合は agents.yaml の llm.model を変更するか、
# --llm-model で上書き
ollama list
```

コンテナ内 `ea-loop` は `OLLAMA_BASE_URL=host.docker.internal` を既定設定します。

#### 研究室 vLLM（GPU サーバー）

研究室マシン `gpu-sv-008`（`10.10.0.108`）が OpenAI 互換 API を公開しています。研究室 LAN または VPN から到達できます（公開アドレスではありません）。そのマシンで別の `vllm serve` を立てないこと。セットアップ: [hirototamura/vllm_server](https://github.com/hirototamura/vllm_server)。

| 用途 | URL | `model` |
| --- | --- | --- |
| 日常の議論（既定） | `http://10.10.0.108:8000/v1` | `qwen3-8b` |
| 重い判断 | `http://10.10.0.108:8001/v1` | `qwen3-32b` |

```bash
ea run scrubber_degradation --agents-mode llm --llm-provider vllm
ea run scrubber_degradation --agents-mode llm --llm-provider vllm --llm-model qwen3-32b \
  --set agents.llm.base_url=http://10.10.0.108:8001/v1
```

環境変数: `VLLM_BASE_URL`、`VLLM_MODEL`、`VLLM_API_KEY`、`VLLM_API_TIMEOUT`、`LLM_PROVIDER`。SSH トンネル例: `VLLM_BASE_URL=http://127.0.0.1:8000/v1`。`agents.llm.api_timeout` は Ollama 用。vLLM は既定 300s（`VLLM_API_TIMEOUT` で上書き）。

デフォルトの LLM 設定は各シナリオの `agents.yaml`（scrubber: [``scrubber_degradation/agents.yaml``](https://github.com/hirototamura/engineering_agents/blob/main/src/scenario/scrubber_degradation/agents.yaml)、ssos: [``ssos_eclss_loop/agents.yaml``](https://github.com/hirototamura/engineering_agents/blob/main/src/scenario/ssos_eclss_loop/agents.yaml)）。選択したバックエンドに届かないと `llm` モードは失敗します。

---

## 実行方法 { #実行方法 }

### 統一 CLI（推奨）

```bash
ea run
```

`scrubber_degradation` を `labeled_rule_base` で実行します（Ollama 不要）。詳細は [docs/cli.md](cli.md)。

```bash
ea scenarios
ea run scrubber_degradation --agents-mode none
ea run scrubber_degradation --agents-mode labeled_rule_base
ea run scrubber_degradation --agents-mode llm   # Ollama または vLLM
ea results
ea doctor
```

### scrubber_degradation

#### エージェントなし（ベースライン）

```bash
ea run scrubber_degradation --agents-mode none
```

レガシー:

```bash
python3 src/scripts/run_mock_eclss.py
```

### ルールベースチーム（scrubber · `labeled_rule_base`）

```bash
ea run scrubber_degradation --agents-mode labeled_rule_base
```

出力先: `src/experiments/results/scrubber_degradation_labeled_rule_base/`

### LLM チーム（scrubber · `llm`・Ollama または vLLM 必須）

```bash
ea run scrubber_degradation --agents-mode llm
```

出力先: `src/experiments/results/scrubber_degradation_llm/`（`scenario.yaml` の `run_id_llm`）

別モデルで別 run 名にしたい場合は、実行前に `agents.yaml` の `llm.model` を変更するか、`output.run_id_llm` をオーバーライドしてください。

### ssos_eclss_loop（SSOS 実 ECLSS）

#### mock（ホスト、ROS2 不要）

```bash
ea run ssos_eclss_loop --backend mock --agents-mode none
ea run ssos_eclss_loop --backend mock --agents-mode labeled_rule_base
ea run ssos_eclss_loop --backend mock --agents-mode llm
```

出力先例: `src/experiments/results/ssos_eclss_loop_labeled_rule_base/`

PowerShell では次のように実行できます。

```powershell
python -m scenario.ssos_eclss_loop.scenario_run --backend mock --agents-mode labeled_rule_base --steps 8
```

#### ros2（SSOS Docker 内）

```bash
# Terminal 1: SSOS コンテナ起動後、ECLSS headless
~/dev/ssos/ssos-run.sh
# コンテナ内: bash /root/ssos-eclss-headless.sh

# Terminal 2: ホスト repo ルート
./scripts/run_ssos_eclss_loop.sh --agents-mode labeled_rule_base
./scripts/run_ssos_eclss_loop.sh --agents-mode llm
```

コンテナ内: `ea-loop --agents-mode labeled_rule_base`（`src/` 同期済み前提）。

前 run の設計提案を次 run に反映:

```bash
python -m scenario.ssos_eclss_loop.scenario_run --backend mock --agents-mode llm \
  --apply-proposals src/experiments/results/ssos_eclss_loop_llm/design_proposals.json
```

graph_rewire E2E: `./scripts/run_graph_rewire_e2e.sh`（ECLSS headless 前提）

詳細: [scenario-ssos-eclss-loop.md](scenario-ssos-eclss-loop.md)。

### 主な出力ファイル

#### scrubber_degradation

| ファイル | 説明 |
| --- | --- |
| `telemetry.jsonl` | CO2、効率、電力マージン、EPS 支援など |
| `messages.jsonl` | エージェント発言・reasoning |
| `events.jsonl` | 異常注入、回復コマンド、設計変更イベント |
| `design_state.jsonl` | 各 step 開始時点のトポロジ（エージェント行動前） |
| `design_proposals.json` | ラン終了後の恒久設計案 |
| `summary.json` | 実行サマリ（`agents_mode`, 最終 CO2 など） |

#### ssos_eclss_loop

| ファイル | 説明 |
| --- | --- |
| `telemetry.jsonl` | CO₂/O₂/水ストレージ（kg / L） |
| `health_metrics.jsonl` | ストレージベースの safe / warning / critical |
| `messages.jsonl` | `operational_command`、deliberation、reasoning |
| `events.jsonl` | `operational_applied` / `operational_rejected` |
| `design_proposals.json` | 事後 `ssos_graph` 案（`action_profile`、`graph_rewire` 等） |
| `summary.json` | `backend`、`peak_co2_storage_kg`、`operational_command_count` 等 |
| `provenance.jsonl` | 運用レコード（`record_type: operational`） |

スキーマ詳細: [docs/api-contracts.md](api-contracts.md) · 読み方: [scenario-ssos-eclss-loop.md](scenario-ssos-eclss-loop.md#出力の読み方)

---

## ダッシュボード

```bash
source .venv/bin/activate
python -m streamlit run src/tools/dashboard/app.py
```

ブラウザで `http://localhost:8501` を開きます。表示例は冒頭の [一目でわかる（ダッシュボード）](#一目でわかるダッシュボード) を参照してください。

- **Overview** — 単一 run または 2 run 比較（scrubber: CO₂ ppm / EPS、ssos: ストレージ kg）  
- **Step replay** — タイムライン・発言・思考を step ごとに再生（ssos は運用タイムライン）  
- サイドバーで run 選択、`Compare with another run` で LLM 同士などを比較可能  
- `summary.scenario == "ssos_eclss_loop"` の run は `ssos_views` で専用 UI に分岐

実行結果の保存先: `src/experiments/results/<run_id>/`

---

## リポジトリ構成

| パス | 用途 |
| --- | --- |
| `src/core/agents/` | Persona、Team ABC、メモリ、LLM クライアント |
| `src/environment/` | `SimulatorProtocol`（scrubber）、`EclssBackend` / `Ros2EclssBridge`（ssos）、EPS mock / `Ros2EpsBridge` |
| `src/scenario/` | `scrubber_degradation`、`ssos_eclss_loop`、各 Team、`design_proposals` |
| `src/experiments/results/` | 実行結果（gitignore 推奨） |
| `src/tools/dashboard/` | Streamlit UI |
| `src/integrations/one_piece/` | provenance レコード生成 |
| `docs/ja/` | 設計・API・シナリオドキュメント（開発プラン含む） |
| `docs/ja/memo/` | 実装プロセス記録・バックログ（[development-plan.md](development-plan.md) から参照） |
| `docs/en/` | English documentation |
| `docs/en/memo/` | English research memos |

依存方向: `tools → scenario → environment → core`

---

## ライセンス

[Apache License 2.0](https://github.com/hirototamura/engineering_agents/blob/main/LICENSE.txt) — Copyright 2026 One Piece Engineering
