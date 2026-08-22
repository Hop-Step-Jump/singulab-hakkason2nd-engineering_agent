# SSOS Mock ECLSS / Plant Simulation 設計・再現範囲

- 更新: 2026-07-29
- 対象リポジトリ: `hirototamura/engineering_agents`
- 実装PR: #40 `Feat/plant sim eclss`
- 対象backend: `PlantSimEclssBackend`（`backend.kind = plant_sim`）
- 状態: **PR #40の実装内容に合わせて更新済み**

> 本書の最優先目的は、Plant SimがSSOSの何を再現し、何を再現せず、なぜその忠実度を選んだのかを明確にすることである。
>
> Plant SimはSSOSのPython移植や代替実装ではない。AIエージェントによるECLSS運用判断を検証するため、SSOSの主要な物質フローと操作因果を抽出した、決定論的な中忠実度モデルである。

---

## 0. 結論

Plant Simの位置づけは、次の一文に集約される。

> **SSOSと同じ操作インターフェースを保ちながら、乗員代謝、ARS、OGS、Sabatier、WRSの主要な物質収支をPython上で再現し、装置内部の詳細物理、ROS2通信、熱・電力・水質モデルは意図的に省略した、エージェント検証用の中忠実度backend。**

今回重視したのは、SSOSとの時系列・内部状態の完全一致ではなく、次の性質である。

1. エージェントの操作によってプラント状態が変わる。
2. CO₂、O₂、水の入力・出力・損失が説明できる。
3. 在庫不足や故障によって操作が制限される。
4. 不正な操作によって物質が無から生成されない。
5. 同じ初期条件と操作列から同じ結果が得られる。
6. 上位のエージェントは、mock / plant_sim / ros2を同じ`EclssBackend`契約で差し替えられる。

したがって、Plant Simは「SSOSを簡略化して再実装したもの」というより、**SSOSを参照して構築した、運用判断に必要十分な物質収支モデル**と表現するのが正確である。

---

## 1. 3つのbackendの位置づけ

```text
SsosEclssLoopTeam / LLM
        │ commands / telemetry
        ▼
EclssBackend Protocol
        │
        ├─ MockEclssBackend / LoopMockEclssBackend
        │      契約確認・簡易シナリオ用
        │
        ├─ PlantSimEclssBackend
        │      主要物質フローと操作因果を再現する中忠実度モデル
        │
        └─ Ros2EclssBridge
               ROS2経由でSSOSへ接続
```

### 1.1 従来Mock・Plant Sim・SSOSの比較

| 比較項目 | 従来Mock / LoopMock | 今回のPlant Sim | SSOS |
|---|---|---|---|
| 主目的 | API疎通、テスト、簡易的な状態変化 | エージェントによるECLSS運用判断の検証 | ECLSS装置・環境の詳細シミュレーション |
| 実装 | Python | Python | ROS2 / C++ |
| ROS2依存 | なし | なし | あり |
| `EclssBackend` | 対応 | 対応 | `Ros2EclssBridge`を介して対応 |
| 状態変化 | 固定値または単純な増減 | 時間、乗員代謝、操作量、在庫、故障に基づく | 装置内部状態と物理モデルに基づく |
| 乗員代謝 | CO₂固定増加が中心 | CO₂発生、O₂消費、飲用水消費、尿・凝縮水生成 | Crew metabolic model |
| ARS | CO₂を固定量またはgoal比で削減 | 処理能力、goal scale、捕集効率、ventを再現 | 吸着床、流量、熱、サイクル等を含む |
| OGS | 水消費とO₂生成の簡易処理 | 水電解の量論、能力上限、在庫制限を再現 | 電解セル、電流、電圧、熱等を含む |
| Sabatier | CO₂を単純に減算 | H₂・CO₂・H₂O・CH₄の量論を再現 | 反応速度、平衡、温度等を含む |
| WRS | LoopMockでは未実装 | 尿・grey water buffer、回収率、brine lossを再現 | 蒸留、ろ過、水質等を含む |
| CO₂状態 | 空気中と処理済みが混在し得る | `cabin_co2_kg`と`captured_co2_kg`を分離 | キャビン大気と処理・貯蔵系を分離 |
| 質量収支 | 厳密な説明は困難 | 各operationと累積ledgerで検証可能 | 詳細モデル内で保存則を考慮 |
| 故障 | フラグ中心 | failure時は対象actionを停止し、状態を変更しない | 装置・構成要素レベルの故障表現が可能 |
| 温度・圧力 | なし | なし | あり |
| 電力・熱 | なし | なし | サブシステムごとにあり |
| 水質 | なし | なし | 導電率、ろ材、汚染等を扱う |
| ppm / 分圧 | なし | なし。kgのシナリオbandを使用 | キャビンモデルで扱う |
| 決定性 | 高い | 高い | 実行条件・動的モデルに依存 |
| 計算・環境コスト | 小 | 小 | 比較的大きい |
| 忠実度 | 低 | 中 | 高 |

### 1.2 再現度は一つの数値ではない

Plant Simの忠実度は、軸ごとに異なる。

| 再現軸 | Plant Simの再現度 | 説明 |
|---|---:|---|
| 上位API・操作契約 | 高 | `EclssBackend`のaction / service / telemetryを維持 |
| 主要物質フロー | 中〜高 | CO₂、O₂、水、H₂、CH₄、vent、brineを帳簿化 |
| 操作と状態変化の因果 | 中〜高 | goal量、在庫、能力上限、故障が結果に反映 |
| 装置のマクロ能力 | 中 | SSOS参照値をkg/day等の能力値として利用 |
| 装置内部の過渡応答 | 低 | 起動遅れ、破過、温度変化などは未再現 |
| 装置内部物理 | 低 | PDE、電気化学、反応速度、水質モデルは未移植 |
| ROS2通信・ノード構成 | なし | Python内の同期backendとして実装 |
| 実ISS環境の安全限界 | なし | thresholdはシナリオ用であり曝露限界ではない |

---

## 2. なぜこの再現度にしたのか

### 2.1 評価したい対象は装置性能ではなく、エージェントの運用判断

このシナリオの主対象は、次の問いである。

- CO₂が増えたとき、エージェントはARSを操作できるか。
- O₂が減ったとき、OGSを適切な量で動かせるか。
- waste waterが蓄積したとき、WRSを動かせるか。
- 故障や在庫不足を検知し、無効な操作を避けられるか。
- 操作後の結果を観測し、次の判断に反映できるか。

この評価に必要なのは、装置内部の温度分布や反応器内の局所濃度ではなく、**操作に対する在庫変化と成功・失敗の因果**である。

### 2.2 採用基準

SSOSの要素をPlant Simへ入れるかどうかは、次の基準で判断した。

| 判断基準 | 採用するもの | 採用しないもの |
|---|---|---|
| エージェントの判断に使うか | CO₂、O₂、水在庫、故障、waste feed | 吸着床内部温度、セル過電圧など |
| 操作結果を左右するか | 操作量、能力上限、在庫制限、回収率 | 利用先のない詳細電力・熱計算 |
| 物質収支に必要か | 量論、vent、brine、短不足 | 水質やフィルタ寿命 |
| 妥当な値を置けるか | 検証済み能力値、分子量による量論 | 較正パラメータが不足した詳細物理 |
| 実装リスクに見合うか | 単純で検証可能な決定論モデル | 不安定化や誤較正のリスクが高いPDE等 |
| 将来後付けできるか | 現時点で必要な状態 | EPS、thermal、ppm、水質は別レイヤで追加可能 |

### 2.3 「詳細物理を省略した」のではなく「評価目的に不要な軸を分離した」

例えばOGSの電圧・過電圧モデルは、電力や発熱を評価するには必要である。しかし、現行の`ssos_eclss_loop`はEPSやthermal系へ接続していない。その状態で電気化学モデルだけを移植しても、エージェントの判断や物質量評価にはほぼ使われない。

同様にWRSの水質モデルは重要だが、現行telemetryとエージェントは水量を判断対象としており、導電率やフィルタ破過を操作していない。したがって、初期Plant Simでは水量収支と回収率に限定した。

詳細物理は不要なのではなく、**それを評価する上位シナリオ・観測・操作が追加された段階で、別レイヤとして拡張すべき要素**である。

---

## 3. 実装されたモデルの全体像

### 3.1 状態遷移

```text
product water
   │
   ├─ Crew consumption ─→ urine buffer ─┐
   │                        condensate ──┼─→ WRS ─→ product water
   │                        water loss ──┘          └→ brine loss
   │
   └─ OGS electrolysis ─→ O₂ storage
                          └→ H₂ ─┐
                                 ├─ Sabatier ─→ regenerated water
captured CO₂ ────────────────────┘              └→ CH₄ vent

Crew metabolism ─→ cabin CO₂ ─→ ARS ─→ captured CO₂
                                      └→ CO₂ vent
Crew metabolism ─→ O₂ consumption
```

### 3.2 Single source of truth

Plant Simは`MockEclssBackend`を継承せず、`EclssBackend`を直接実装する。

内部状態は`PlantState`だけが保持する。telemetryは毎回`PlantState`から生成し、親クラスのtelemetryやwater bufferとの二重管理を行わない。

主な状態:

| 状態 | 意味 |
|---|---|
| `cabin_co2_kg` | キャビン空気中CO₂を簡略化した運用シグナル |
| `captured_co2_kg` | ARS処理後、Sabatierやserviceに使用可能なCO₂ |
| `available_o2_kg` | エージェントが監視する利用可能O₂プール |
| `product_water_l` | 乗員とOGSが利用できる水 |
| `urine_buffer_l` | WRSへ投入可能な尿系水 |
| `grey_water_l` | 凝縮水と外部投入されたgrey water |

累積diagnosticsとして、CO₂ vent、H₂ vent、CH₄ vent、WRS brine loss、O₂・水不足、各サブシステムの生成・消費量を記録する。

### 3.3 時間モデル

- 観測間隔: `step_seconds = 1200秒`（20分）
- 乗員代謝: stepごとにレートを時間積分
- ARS / OGS / WRS: action 1回が処理するoperation quantumを個別設定

simulation stepと装置actionの処理時間を分けた理由は、エージェントの観測周期と装置1回の処理量が同じとは限らないためである。

`ars_operation_seconds = 4800秒`は、SSOSの内部サイクルを忠実再現する値ではなく、1回のARS actionで処理する量を明示するシナリオ設定である。

---

## 4. サブシステム別の再現範囲と判断理由

## 4.1 乗員代謝

### 再現しているもの

- 乗員数
- 活動係数
- 時間経過に応じたCO₂発生
- O₂消費
- 飲用水消費
- 尿、凝縮水、回収不能水の生成
- O₂・水不足時のshortfall記録

初期値:

| パラメータ | 値 |
|---|---:|
| CO₂発生 | 1.04 kg/day/person |
| O₂消費 | 0.84 kg/day/person |
| 飲用水 | 2.28 kg/day/person |
| 尿 | 1.50 kg/day/person |
| 凝縮水 | 0.75 kg/day/person |
| 回収不能水 | 0.03 kg/day/person |

飲用水の出力内訳は、尿 + 凝縮水 + 回収不能水 = 飲用水となるようconfig validationで検査する。

### 再現していないもの

- キャビン熱負荷
- 呼吸・発汗の短周期変動
- 個人差
- 食事由来の物質フロー
- 活動スケジュールの時間変化

### この再現度にした理由

乗員代謝は、エージェントが対応すべきCO₂増加、O₂低下、水循環の起点である。そのため物質収支は必要であり、kg/dayのレートはPythonへ素直に移植できる。

一方、熱負荷や個人差は現在のagent observation・actionに接続されていないため、初期モデルでは対象外とした。

`scenario.yaml` の `plant_sim.crew.size` が乗員数の正本である。`plant_sim.survival.enabled: true` のとき、各ステップの操作後に **帯滞在**（運用ヘルス帯と同じ WARNING/CRITICAL。O2/水は WARNING 2 連続で −1、O2 CRITICAL は 1 ステップ −2、水 CRITICAL は −1。CO2 WARNING は 2 連続後に一度だけ `n // 4`、CO2 CRITICAL は 2 連続後に一度だけ `n // 2`。1 人では CO2 帯だけでは減らない。帯を出て再入場するまで再発火しない）を適用し、そのあと **物理下限**（次ステップの O2・水を払えない人数。cabin CO2 では物理減員しない。最終ステップは次の代謝がないので適用しない）をハードキャップとして残す。O2 と水が同時に下限なら減員人数は O2 に帰属する。テレメトリ `survival.lost_this_step` は帯滞在と物理下限の合計で、survival 有効時は `post_ops` の 1 行に載る（1 step あたり最大 2 行。survival オフでは運用コマンドがなければ出さない）。イベントでは `o2_warning` と `o2_physics` のように区別する。運用エージェントも同じ人数に同期する。N スイープと `plant_sim` ノブの感度はダッシュボードとは別アプリ `python3 -m tools.plant_sim_sensitivity_app`（port 8502。survival オフ。3×4: 行が CO2/O2/水。左3列は代謝 / 装置1回 / タンクΔで縦軸を共有。4列目は初期タンク+キャンペーンΔの終了量。符号は左3列が「タンクが増えたらプラス」）。

---

## 4.2 ARS

### 再現しているもの

- cabin CO₂からの除去
- goal量に応じた処理量の変化
- 1日当たりの処理能力
- 捕集効率
- 捕集CO₂とvent CO₂への分配
- cabin CO₂在庫による処理上限
- ARS故障時のno mutation

初期値:

| パラメータ | 値 | 分類 |
|---|---:|---|
| 処理能力 | 4.50 kg/day | SSOS参照 |
| 捕集効率 | 0.83 | SSOS参照 |
| reference goal | 1.80 kg | 既存mock互換 |
| operation quantum | 4800秒 | シナリオ調整 |

計算概念:

```text
operation capacity = capacity_per_day × operation_seconds / 86400
goal scale = goal.initial_co2_mass / reference_goal
removed = min(cabin inventory, operation capacity × goal scale)
captured = removed × capture efficiency
vented = removed - captured
```

### 再現していないもの

- 4床モレキュラーシーブ
- 1D有限体積PDE
- Toth等温線
- 吸着熱と温度変化
- ブロワ、プリクーラ、流量
- 10-60-10等のサイクル状態
- 破過と立ち上がりの動特性
- moisture / contaminantsによる性能変化

`initial_moisture_content`と`initial_contaminants`は入力範囲を検証するが、現行MVPの収支計算には使用せず、結果の`ignored_inputs`へ明示する。

### この再現度にした理由

ARSの詳細モデルを正しく再現するには、空間PDE、吸着平衡、吸着速度、熱収支、流量、サイクル切替を連成させ、多数の装置パラメータを較正する必要がある。

一方、今回エージェントが必要とするのは、主に次の関係である。

```text
ARSを動かす
→ cabin CO₂が減る
→ 一部がSabatier用に捕集される
→ 残りがventされる
```

破過や温度応答を判断対象にしていない段階では、SSOSで検証されたマクロな除去能力と捕集効率を使う方が、誤較正した詳細モデルより信頼性が高く、決定論的なテストもしやすい。

---

## 4.3 OGS

### 再現しているもの

- product waterの消費
- 水電解によるO₂とH₂の生成
- water inventoryによる処理上限
- OGS最大能力による処理上限
- goalの入力水量による操作量変化
- OGS故障時のno mutation

量論係数は丸めた経験係数ではなく、分子量から導出する。

```text
2 H₂O → 2 H₂ + O₂
```

初期値:

| パラメータ | 値 | 分類 |
|---|---:|---|
| 最大O₂能力 | 9.25 kg/day | SSOS参照 |
| operation quantum | 1200秒 | シナリオ設定 |
| labeled policyの入力水量 | 0.15 kg/action | 現行PRのシナリオ調整 |

### 再現していないもの

- Nernst電圧
- 活性化・抵抗・濃度過電圧
- セル電流とセル数の制御
- スタック温度
- 消費電力
- 発熱
- 膜含水率や劣化
- 起動・停止の過渡応答

### この再現度にした理由

OGSの電気化学モデルが主に追加するのは、電圧、消費電力、発熱、効率である。現在のシナリオはEPS・thermal系へ接続しておらず、エージェントもこれらを観測・制御していない。

O₂とH₂の生成量を物質収支として評価する目的では、水の処理量と量論が中心となる。そのため、物質量を決める部分を再現し、利用先のない電気・熱モデルは分離した。

`0.15 kg/action`はSSOSの物理値ではない。現行のエージェントラッチとaction発行頻度においてO₂を維持するためのscenario-tuned値であり、将来的にactionの再発行制御を整理した後、再調整する前提である。

---

## 4.4 Sabatier

### 再現しているもの

- OGSで生成されたH₂の利用
- `captured_co2_kg`の利用
- H₂・CO₂の少ない側による反応上限
- 再生水のproduct waterへの返却
- CH₄ vent
- 未使用H₂ vent
- 変換効率

反応:

```text
CO₂ + 4 H₂ → CH₄ + 2 H₂O
```

SabatierはOGS action内で自動実行し、default policyではOGS前に明示的な`request_co2`を行わない。これにより、同一stepにCO₂を二経路で引き出すことを避ける。

### 再現していないもの

- Arrhenius反応速度
- 化学平衡
- 反応器温度
- 滞在時間
- 圧力依存
- 触媒劣化
- 反応熱

### この再現度にした理由

反応速度・平衡・温度モデルが決めるのは、主に「どの速度で、何%反応するか」である。一方、反応した分のH₂、CO₂、H₂O、CH₄の比率は量論で決まる。

熱モデルや較正データを持たない状態でArrhenius式だけを追加しても、妥当な変換率にはならない。そこで、初期実装は変換効率をconfig化し、反応した分の量論を厳密に閉じる方針とした。

---

## 4.5 WRS

### 再現しているもの

- 乗員から生成された尿buffer
- 凝縮水・grey water buffer
- actionで指定された尿処理量
- 1operation当たりの処理能力
- 尿とgrey waterの回収率
- 回収水のproduct waterへの返却
- 未回収分のbrine loss
- feedがない場合のno-op / failure
- WRS故障時のbuffer保持とno mutation

初期値:

| パラメータ | 値 | 分類 |
|---|---:|---|
| 尿回収率 | 0.98 | SSOS参照・BPA込み |
| grey water回収率 | 0.90 | 簡略モデル設定 |
| 最大feed | 10.0 L/operation | シナリオ設定 |
| WRS trigger | waste feed 0.5 L | シナリオ設定 |

`WrsGoal.urine_volume`は、新しい水を外部から生成する入力ではなく、**内部のurine bufferから最大何L処理するか**を表す。

### 再現していないもの

- VCDの熱力学
- 蒸留器内部状態
- 多段ろ過
- 導電率
- 有機物・微生物
- 触媒酸化
- フィルタ破過
- 飲用可否の水質判定

### この再現度にした理由

今回必要なのは、水循環の量的な閉じ方である。

```text
product water
→ crew consumption
→ urine / condensate
→ WRS
→ product water
```

WRSの回収「量」は回収率で表現できる。一方、水質は別の状態軸であり、現行telemetry・agent action・health判定には含まれていない。水質判断をエージェントへ追加する際に、導電率、フィルタ残量、破過を独立して追加するのが適切である。

---

## 4.6 キャビン大気・ppm

### 再現しているもの

- `cabin_co2_kg`をCO₂危険シグナルとして使用
- `available_o2_kg`をO₂運用シグナルとして使用
- kg単位のthresholdによるagent判断

### 再現していないもの

- キャビン容積
- 総圧
- 温度
- 気体組成
- 分圧
- ppm
- 実ISSの曝露限界

### この再現度にした理由

現行`EclssTelemetrySnapshot`はkg単位のstorageを上位契約としており、エージェントもkg thresholdで判断している。ここへppmを導入するには、容積だけでなく温度、圧力、気体組成等の仮定が必要になる。

現在の2.0 kg / 8.0 kg等は、物理的なISS曝露限界ではなく、**teaching-scaleのシナリオband**である。物理ppmが必要になった段階で、cabin atmosphere modelを別レイヤとして追加する。

---

## 5. SSOSから参照したものと、シナリオ調整したもの

Plant Simのパラメータは、出所の異なる値を混同しない。

### 5.1 Source-derived

SSOSの資料・config・検証値、または分子量から採用した値。

- 乗員のCO₂ / O₂ / 水レート
- ARS処理能力
- ARS捕集効率
- OGS最大O₂能力
- WRS尿回収率
- 水電解の量論
- Sabatierの量論

これらは、SSOSの内部物理を移植したことを意味しない。**詳細モデルが出力するマクロ能力値や反応比を、簡略モデルの係数として利用している**。

### 5.2 Scenario-tuned

エージェントシナリオを成立させるために設定した値。

- initial inventory
- CO₂ / O₂ / water threshold
- observation step
- action operation seconds
- OGS goal water 0.15 kg/action
- WRS trigger
- WRS max feed

これらをSSOSやISSの実物値として説明してはならない。

### 5.3 Structural decisions

数値に依存しない設計上の決定。

- cabin CO₂とcaptured CO₂の分離
- `PlantState`をsingle source of truthとする
- failure時はno mutation
- 不正値をmutation前に拒否
- serviceの部分提供を明示
- vent、brine、shortfallをledgerへ残す
- ROS2との境界は`EclssBackend`で維持する

---

## 6. 質量収支の扱い

Plant Simは閉鎖系ではない。CO₂ vent、CH₄ vent、H₂ vent、brine、人体からの回収不能水、外部serviceが存在する。

したがって「全stateの総和が常に一定」ではなく、各境界を含むledgerで収支を検証する。

### ARS

```text
cabin CO₂ before
= cabin CO₂ after + captured CO₂ + vented CO₂
```

### OGS

```text
processed water
≈ generated O₂ + generated H₂
```

### Sabatier

```text
used CO₂ + used H₂
≈ regenerated water + generated CH₄
```

### WRS

```text
urine feed + grey water feed
≈ recovered water + brine loss
```

### Crew water

```text
potable water consumed
≈ urine + condensate + unrecoverable loss
```

このledgerを持つことが、従来MockからPlant Simへ上げた最も重要な忠実度の一つである。

---

## 7. 故障・不正入力・在庫不足

Plant Simでは、運用エージェントの評価に必要な異常挙動を再現する。

### 故障

- ARS failure: ARS actionを停止
- OGS failure: OGSと内包Sabatierを停止
- WRS failure: WRS actionを停止
- failure時は対象状態を変更しない
- serviceは既存在庫の払出であり、subsystem failureとは独立
- **タイミング指定の注入**は backend ではなくシナリオ層の `subsystem_failures`（`scenario.yaml`、**0-based steps**）が担当する。既定はオフ（`inject_failures: false`）。CLI `--inject-failures` で有効化し、任意 step で `set_subsystem_failure` を呼ぶ（`mock` / `plant_sim` / `ros2` 共通）。詳細は [scenario-ssos-eclss-loop.md](../../scenario-ssos-eclss-loop.md#サブシステム故障スケジュールsubsystem_failures)

### 不正入力

- negative、NaN、Infを拒否
- action goalの0はno-opとして許容
- service requestの0以下は拒否
- percent入力は0〜100で検証

### 在庫不足・能力不足

- actionは利用可能在庫・装置能力まで部分処理
- serviceは部分提供を行い、要求全量を満たせない場合は`success=False`
- O₂・水の乗員需要を満たせない場合はshortfallへ累積

これにより、「コマンドを発行したら必ず成功するmock」ではなく、エージェントの操作量とタイミングを評価できる。

---

## 8. 現在のPR #40で実装済みの範囲

### 本体モデル

以下は独立した`plant_sim/`パッケージとして実装済みである。

```text
src/environment/ssos/eclss/plant_sim/
├─ __init__.py
├─ backend.py
├─ config.py
├─ model.py
└─ stoichiometry.py
```

実装済み:

- `PlantSimConfig`と設定validation
- `PlantState`と累積ledger
- 乗員代謝
- ARS
- OGS + Sabatier
- WRS
- resource services
- failure gating
- input validation
- telemetry / `raw_topics.plant_sim`
- invariant検査
- model / backend / balance tests

### シナリオ配線

実装済み:

- `backend.kind = plant_sim`
- CLIの`--backend plant_sim`
- `advance_step()`を持つbackendの時間更新
- agentからの`water_recovery` command
- WRSのrule-based trigger
- Plant Sim用OGS / WRS policy

### テスト・デモ

PR #40時点の記録:

- plant_sim関連: 57 tests passed
- environment + scenario: 229 tests passed
- 72 stepsのlabeled rule baseデモでoverall SAFE
- CO₂ peak 1.54 kg
- O₂ minimum 0.41 kg
- product water 約97 L

これらはシナリオとして動作することの確認であり、SSOSとの数値一致を証明するものではない。

### 現在の統合上の注意

PR #40の本体`plant_sim/`は独立している。一方、`scenario_run.py`、agent、`agents.yaml`の配線部分は、#37のoperation timing変更と同じ領域を扱うため、#37統合後に再適用・調整する前提がある。

また、現行OGS goalの`0.15 kg/action`は、現行agentの一発ラッチと再発行頻度に合わせたshakeout tuningである。Plant Simの物理式ではなく、agent operation policy側の値である。

---

## 9. Plant Simで保証すること／保証しないこと

### 保証すること

- `EclssBackend`契約で利用できる。
- 同じ設定と操作列なら同じ結果になる。
- 在庫・累積値はfiniteかつ非負に保たれる。
- 主要operationの物質収支を説明できる。
- 在庫以上・能力以上の処理をしない。
- failure・invalid inputでは対象状態を変更しない。
- agent操作が状態推移へ反映される。

### 保証しないこと

- SSOSと同じ内部状態・時系列になること。
- SSOS C++コードと同じ計算を行うこと。
- 実ISSの安全限界を表すこと。
- キャビンppm、圧力、温度が物理的に正しいこと。
- 装置の起動遅れ、破過、熱応答を表すこと。
- 消費電力や発熱を表すこと。
- WRS処理水の飲用可否を表すこと。
- ROS2通信障害やノード故障を表すこと。

---

## 10. 今後、忠実度を上げる場合の順序

現在の上位契約とPlant Simの決定論性を保ちながら、必要になった軸から追加する。

1. agent actionの再発行・cooldown・operation durationの整理
2. subsystem capacity degradation / efficiency drift
3. sensor bias、欠測、noise
4. crew activity schedule（sleep / exercise）
5. makeup water、消耗品、補給
6. 電力消費の係数モデルとEPS連携
7. thermal state
8. cabin atmosphere（temperature / pressure / ppm）
9. WRS水質・filter状態
10. 詳細物理backendまたはSSOSとの比較adapter

高忠実度化する際も、Plant Simは単純で検証可能な回帰参照として残す。

---

## 11. レビュー時の読み方

レビューでは、Plant SimをSSOSの代替として評価するのではなく、次の観点で確認する。

1. エージェントのoperationが適切な物質フローへ接続されているか。
2. 在庫・能力・故障による制限が一貫しているか。
3. 各operationのledgerが閉じているか。
4. source-derived値とscenario-tuned値が区別されているか。
5. 非再現範囲が誤って実物相当と説明されていないか。
6. mock / plant_sim / ros2を同じ上位契約で比較できるか。

---

## 12. 最終的な位置づけ

Plant Simは、SSOSの内部物理を縮小コピーしたものではない。

**SSOSで採用・検証されている主要な能力値と化学量論を参照しながら、AIエージェントがECLSSを操作した結果を、物質収支、在庫制約、故障挙動として説明できるようにしたモデル**である。

そのため、Plant Simの価値は物理式の数ではなく、次にある。

- 操作と結果の因果が明確である。
- 物質がどこから来て、どこへ行ったかを説明できる。
- エージェントの判断の良否が状態推移に現れる。
- ローカルPythonだけで高速・決定論的に検証できる。
- 将来SSOSへ差し替えても、上位の操作契約を維持できる。

この目的に対して、現在の「主要物質フローは再現し、装置内部物理は意図的に分離する」という中忠実度は妥当である。

---

## 参照

### engineering_agents

- `src/environment/ssos/eclss/backend.py`
- `src/environment/ssos/eclss/types.py`
- `src/environment/ssos/eclss/units.py`
- `src/environment/ssos/eclss/plant_sim/`
- `src/scenario/ssos_eclss_loop/scenario_run.py`
- `src/scenario/agents/ssos_eclss_loop_team.py`
- `src/scenario/ssos_eclss_loop/agents.yaml`
- PR #40 `Feat/plant sim eclss`

### 関連PR

- #35: LoopMock dynamics / mass-conserving services
- #36: threshold / critical handling
- #37: operation timing / post-ops logging
- #38: document path alignment
- #39: kg-scale and ROS boundary documentation

### upstream SSOS

`space-station-os/space_station_os#231`および関連docs/configは、能力値・反応・考え方の参照に限る。Plant Simの実装契約・統合先・完全一致対象ではない。
