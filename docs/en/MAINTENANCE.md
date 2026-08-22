# MkDocs — documentation maintenance

## Scope

- `docs/en/` — English pages (quick start, overview, design docs, SSOS guides, memos)
- `docs/ja/` — Japanese pages (same structure)
- `mkdocs.yml` — site config with `mkdocs-static-i18n` (header language switcher)
- Root `README.md` / `AGENTS.md` — GitHub and Cursor entry hubs (content lives under `docs/{lang}/`)

## Local preview

```bash
pip install -e ".[dev]"
mkdocs serve
# English: http://127.0.0.1:8000/
# Japanese: http://127.0.0.1:8000/ja/
```

Build output `site/` is gitignored. Do not commit it.

## CI

Pull requests run `mkdocs build --strict` (see `.github/workflows/docs.yml`).

When updating SSOS or scrubber backend docs, verify file paths against `src/environment/` — ECLSS lives under `ssos/eclss/`, scrubber EPS under `scrubber/eps/`, and SSOS EPS bridge under `ssos/eps/ros2/` (post–environment refactor).

## References

- [Document catalog](catalog.md) — full page index including memos not in the main nav
- [SSOS connection plan](memo/ssos_eclss_loop/ssos_eclss_loop_connection_plan.md)
- [Post-run design agent](memo/ssos_eclss_loop/post_run_design_agent.md)
- [SSOS roadmap](ssos/roadmap.md)
