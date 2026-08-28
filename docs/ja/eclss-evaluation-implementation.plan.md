---
name: eclss-evaluation-implementation
overview: A3スコアカードを、plant_simのラン成果物から決定論的に採点する評価器として実装します。物理整合性を配点外ゲートにし、`evaluation.json`を正本、`summary.json`を索引として出力します。
todos:
  - id: define-evaluation-contract
    content: evaluation設定・JSON契約・決定論的採点純関数を実装する
    status: completed
  - id: expose-physics-ledger
    content: plant_sim台帳をテレメトリへ公開し物理ゲートを実装する
    status: completed
  - id: integrate-run-output
    content: ラン終了処理へevaluation.json生成とsummary索引を接続する
    status: completed
  - id: add-tests-docs
    content: 単体・統合テストと日英API文書・A3スコアカードを同期する
    status: completed
  - id: verify-regression
    content: 非E2E pytestと2-run smokeで回帰検証する
    status: completed
isProject: false
---

# ECLSS評価器の実装

## 評価契約
- 完全採点の対象は `ssos_eclss_loop` の `backend=plant_sim` かつ `survival.enabled=true`。それ以外も `evaluation.json` は生成し、理由付き `not_applicable` にする。
- 配点外の物理ゲートを最初に実行し、必須値の欠損・非有限値、負在庫、台帳残差、故障中の処理、操作結果の物理符号を検査する。FAIL時は各軸と総合点を算出せず `invalid` にする。
- actor有効時は100点満点（50+10×5）、`actor.mode=none` はD/Eを除外して80点満点。適用不能軸を0点扱いや再配分にしない。

## 決定論的な採点式
- actor残存：`50 × crew_remaining / crew_initial`。原因別喪失は説明値として物理下限と帯滞在を分離する。
- A/TCL：本ラン内で観測された最初の `/eclss/events/crew_lost` の `simulation_time_s` を使用し、`10 × min(TCL / T_ref, 1)`。喪失なしで観測時間が `T_ref` 以上なら10点、未満なら右打ち切りで `incomplete`。未来外挿・自動延長はしない。
- B/生存環境：CO₂・O₂・水を均等配分し、safe境界からcritical境界までを0〜1に正規化した危険度の時間積分から10点を算出する。同一stepのpre/post行を二重計上しない。
- C/資源余裕・回復：3資源を均等配分。初期値、最初の故障イベント時のactor操作前値、最悪値、終了値と差分を記録し、終端安全余裕と故障後最悪点からの回復率を設定済み比率で合成する。
- D/actor判断：危険episodeへの応答遅延と、観測状態・故障状態・payload範囲に対するコマンド妥当率を設定済み比率で合成する。装置結果は判断判定に使わない。
- E/装置応答：Dで妥当と判定した操作だけを対象に、成功、要求量に対する実処理量、期待する物理符号を合成する。複数操作時は個別result detailsを正本とし、step全体の差分を個別操作へ誤帰属しない。

## 実装箇所
- [`src/scenario/ssos_eclss_loop/evaluation.py`](/Users/naoya/develop/Singulab/hakkason2nd/engineering_agents/src/scenario/ssos_eclss_loop/evaluation.py)を新設し、JSONL読取、canonical行選択、物理ゲート、各軸の純関数、`evaluation.json`書込を集約する。
- [`src/scenario/ssos_eclss_loop/scenario.yaml`](/Users/naoya/develop/Singulab/hakkason2nd/engineering_agents/src/scenario/ssos_eclss_loop/scenario.yaml)に `evaluation` セクションを追加する。`T_ref`、均等資源重み、B/Cの正規化、Dの許容遅延・payload範囲、D/Eの内部重み、物理ゲート許容誤差をすべて明示する。
- [`src/environment/ssos/eclss/plant_sim/backend.py`](/Users/naoya/develop/Singulab/hakkason2nd/engineering_agents/src/environment/ssos/eclss/plant_sim/backend.py)の `raw_topics.plant_sim` に、ラン単位の保存則を成果物から再計算するための既存累積台帳を追加する。物理モデル自体や判定閾値はenvironment層へ入れない。
- [`src/scenario/ssos_eclss_loop/scenario_run.py`](/Users/naoya/develop/Singulab/hakkason2nd/engineering_agents/src/scenario/ssos_eclss_loop/scenario_run.py)でラン終了後に評価器を呼び、`evaluation.json`を生成する。`summary.json`には `evaluation_path/status/score/max_score/physics_gate_passed` のみ追加し、詳細の正本は分離する。
- [`docs/ja/api-contracts.md`](/Users/naoya/develop/Singulab/hakkason2nd/engineering_agents/docs/ja/api-contracts.md)と[`docs/en/api-contracts.md`](/Users/naoya/develop/Singulab/hakkason2nd/engineering_agents/docs/en/api-contracts.md)へ新成果物、適用条件、打ち切り、canonical行規則を追加し、[`docs/ja/evaluation-scorecard-a3.html`](/Users/naoya/develop/Singulab/hakkason2nd/engineering_agents/docs/ja/evaluation-scorecard-a3.html)も実装上の項目名・式に同期する。

## 検証
- [`tests/scenario/test_ssos_eclss_loop_evaluation.py`](/Users/naoya/develop/Singulab/hakkason2nd/engineering_agents/tests/scenario/test_ssos_eclss_loop_evaluation.py)を新設し、各式、post_ops重複排除、TCL発生/右打ち切り、actor noneの80点、物理ゲート失敗、故障時値、D/Eの対象選別を単体検証する。
- plant_sim統合テストで `evaluation.json` と `summary.json` の索引一致、台帳出力、provenance後も評価参照が残ることを確認する。
- `python3 -m pytest --ignore=tests/e2e` を実行し、可能ならAGENTS.md指定のmock 2-run smokeも実行して既存の設計→検証ループを回帰確認する。
