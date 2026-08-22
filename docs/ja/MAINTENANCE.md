# MkDocs — ドキュメント保守ガイド

## スコープ

- `docs/ja/` — 日本語ページ（クイックスタート、概要、設計 doc、SSOS 運用ガイド、memo）
- `docs/en/` — 英語ページ（同一構成）
- `mkdocs.yml` — `mkdocs-static-i18n` による言語切替設定
- ルート `README.md` / `AGENTS.md` — GitHub・Cursor 向け入口（本文は `docs/{lang}/`）

## ローカルプレビュー

```bash
pip install -e ".[dev]"
mkdocs serve
# 日本語: http://127.0.0.1:8000/ja/
# English: http://127.0.0.1:8000/
```

ビルド成果物 `site/` は `.gitignore` 済み。コミットしない。

## CI

PR では `mkdocs build --strict` を実行（`.github/workflows/docs.yml`）。

SSOS / scrubber バックエンドのドキュメントを更新するときは、`src/environment/` の実パスと照合すること — ECLSS は `ssos/eclss/`、scrubber EPS は `scrubber/eps/`、SSOS EPS ブリッジは `ssos/eps/ros2/`（environment リファクタ後）。

## 参照

- [ドキュメント索引](catalog.md) — メインナビ外の memo も含む全ページ一覧
- [SSOS ECLSS 接合プラン](memo/ssos_eclss_loop/ssos_eclss_loop_connection_plan.md)
- [事後設計エージェント](memo/ssos_eclss_loop/post_run_design_agent.md)
- [SSOS ロードマップ](ssos/roadmap.md)
