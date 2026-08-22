# ドキュメント索引

MkDocs サイトの全ページ一覧です。ヘッダーの言語切替で English を選べます。

| セクション | ページ | 内容 |
| --- | --- | --- |
| 開始 | [クイックスタート](index.md) | インストール、CLI、結果ファイル |
| | [概要](overview.md) | 目的、ダッシュボード、詳細セットアップ |
| 設計 | [アーキテクチャ](architecture.md) | レイヤ、実行フロー、エージェント |
| | [API 契約](api-contracts.md) | JSONL スキーマ、プロトコル |
| | [エージェントガイド](AGENTS.md) | ミッション、コーディング規律 |
| シナリオ | [scrubber_degradation](scenario-scrubber-degradation.md) | Mock CO₂ スクラバー |
| | [ssos_eclss_loop](scenario-ssos-eclss-loop.md) | SSOS 実 ECLSS |
| SSOS | [SSOS 接合](ssos/index.md) | Docker / ROS 2 運用ガイド |
| | [ロードマップ](ssos/roadmap.md) | Phase 0–8 状態 |
| その他 | [CLI ガイド](cli.md) | `ea` コマンド |
| | [開発プラン](development-plan.md) | ロードマップ索引 |
| | [保守ガイド](MAINTENANCE.md) | ドキュメント編集・プレビュー |
| メモ | [バックログ](memo/backlog.md) | BL-001–BL-007 |
| | [MVP プラン](memo/scrubber_degradation/mvp_plan.md) | Scrubber MVP |
| | [EPS 実装プラン](memo/scrubber_degradation/eps_implementation_plan.md) | EPS ブリッジ |
| | [同種エージェントチーム](memo/agents/homogeneous_agent_team_plan.md) | チーム設計 |
| | [SSOS ECLSS 接合プラン](memo/ssos_eclss_loop/ssos_eclss_loop_connection_plan.md) | Phase 0–7 |
| | [事後設計エージェント](memo/ssos_eclss_loop/post_run_design_agent.md) | actor / designer 分離（実装済み） |
| | [SSOS EPS ROS2 プラン](memo/ssos_eclss_loop/ssos_eps_ros2_connection_plan.md) | EPS（Phase 3） |
| | [ROS2 グラフ設計調査](memo/ssos_eclss_loop/ssos_ros2_graph_design_investigation.md) | launch remap |
| | [ECLSS 物理現象](memo/ssos_eclss_loop/ssos_eclss_physical_phenomena_overview.md) | ECLSS 物理メモ |
| | [EPS 物理現象](memo/ssos_eclss_loop/ssos_eps_physical_phenomena_overview.md) | EPS 物理メモ |
| | [CLI v3 プラン](memo/cli_v3_plan.md) | SSOS ホスト 1 コマンド |
| | [Persona LLM OOP](memo/agents/persona_llm_core_oop_plan.md) | Persona 設計草案 |
| | [Persona ワークショップ](memo/agents/persona_workshop_draft.md) | ワークショップメモ |

GitHub 入口: ルート [README.md](https://github.com/hirototamura/engineering_agents/blob/main/README.md) と [AGENTS.md](https://github.com/hirototamura/engineering_agents/blob/main/AGENTS.md)。

```bash
pip install -e ".[dev]"
mkdocs serve
# → http://127.0.0.1:8000/ja/
```
