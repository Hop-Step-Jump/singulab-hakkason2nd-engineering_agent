"""HTML report renderer for ``ssos_eclss_loop`` evaluation payloads."""

from __future__ import annotations

import html
import json
from typing import Any, Mapping, Sequence

AXIS_META = {
    "actor_survival": {
        "label": "actor残存",
        "short": "残存",
        "css": "s-actor",
        "card": "actor",
        "points": 50,
    },
    "tcl": {
        "label": "A. Time to Crew Loss（TCL）",
        "short": "A TCL",
        "css": "s-a",
        "card": "a",
        "points": 10,
    },
    "environment_trajectory": {
        "label": "B. actorが置かれた生存環境",
        "short": "B 生存環境",
        "css": "s-b",
        "card": "b",
        "points": 10,
    },
    "resource_recovery": {
        "label": "C. 資源余裕と回復能力",
        "short": "C 資源余裕・回復",
        "css": "s-c",
        "card": "c",
        "points": 10,
    },
    "actor_decision": {
        "label": "D. actorの操作判断",
        "short": "D 判断",
        "css": "s-d",
        "card": "d",
        "points": 10,
    },
    "physical_response": {
        "label": "E. 設計・装置の物理応答",
        "short": "E 応答",
        "css": "s-e",
        "card": "e",
        "points": 10,
    },
}

STATUS_LABELS = {
    "scored": "採点済",
    "invalid": "検証無効",
    "not_applicable": "適用対象外",
    "incomplete": "不完全",
    "right_censored": "右打ち切り",
    "not_observed": "未観測",
}


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _fmt_score(value: Any) -> str:
    if value is None:
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return _esc(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.3f}".rstrip("0").rstrip(".")


def _status_label(status: Any) -> str:
    key = str(status or "")
    return STATUS_LABELS.get(key, key or "—")


def _metric_preview(metrics: Any, *, limit: int = 8) -> str:
    if not isinstance(metrics, Mapping) or not metrics:
        return "<p class=\"note\">メトリクスなし</p>"
    items = []
    for index, (key, value) in enumerate(metrics.items()):
        if index >= limit:
            items.append("<li>…（詳細は evaluation.json）</li>")
            break
        if isinstance(value, (dict, list)):
            rendered = _esc(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
            if len(rendered) > 160:
                rendered = rendered[:157] + "…"
        else:
            rendered = _esc(value)
        items.append(f"<li><code>{_esc(key)}</code>: {rendered}</li>")
    return "<ul>" + "".join(items) + "</ul>"


def _scorebar(axes: Mapping[str, Any], max_score: Any) -> str:
    cells = []
    for key, meta in AXIS_META.items():
        axis = axes.get(key)
        if axis is None:
            continue
        score = axis.get("score") if isinstance(axis, Mapping) else None
        axis_max = (
            axis.get("max_score", meta["points"]) if isinstance(axis, Mapping) else meta["points"]
        )
        cells.append(
            "<div class=\"{css}\">"
            "<span>{short}</span>"
            "<span class=\"points\">{score} / {axis_max}</span>"
            "</div>".format(
                css=_esc(meta["css"]),
                short=_esc(meta["short"]),
                score=_fmt_score(score),
                axis_max=_fmt_score(axis_max),
            )
        )
    if not cells:
        cells.append(
            "<div class=\"s-actor\"><span>総合</span>"
            f"<span class=\"points\">— / {_fmt_score(max_score)}</span></div>"
        )
    return "<div class=\"scorebar\" aria-label=\"配点と得点\">" + "".join(cells) + "</div>"


def _axis_cards(axes: Mapping[str, Any]) -> str:
    cards = []
    for key, meta in AXIS_META.items():
        axis = axes.get(key)
        if not isinstance(axis, Mapping):
            continue
        cards.append(
            "<article class=\"card {card}\">"
            "<h2>{label} — {points}点</h2>"
            "<p><strong>状態:</strong> {status}　"
            "<strong>得点:</strong> {score} / {axis_max}</p>"
            "{metrics}"
            "</article>".format(
                card=_esc(meta["card"]),
                label=_esc(meta["label"]),
                points=_fmt_score(meta["points"]),
                status=_esc(_status_label(axis.get("status"))),
                score=_fmt_score(axis.get("score")),
                axis_max=_fmt_score(axis.get("max_score", meta["points"])),
                metrics=_metric_preview(axis.get("metrics")),
            )
        )
    if not cards:
        return "<p class=\"note\">採点対象の軸はありません。</p>"
    return "<section class=\"axes\">" + "".join(cards) + "</section>"


def _gate_section(gate: Mapping[str, Any], status: str) -> str:
    passed = bool(gate.get("passed"))
    checks = gate.get("checks") if isinstance(gate.get("checks"), Sequence) else []
    check_html = []
    for check in checks:
        if not isinstance(check, Mapping):
            continue
        ok = bool(check.get("passed"))
        mark = "✓" if ok else "✗"
        css = "pass" if ok else "fail"
        check_html.append(
            f"<span class=\"{css}\">{_esc(mark)} {_esc(check.get('name'))}</span>"
        )
    if not check_html:
        check_html.append("<span class=\"muted\">チェック未実行</span>")

    if status == "not_applicable":
        result = "適用対象外<br>採点しない"
        result_css = "gate-result muted-box"
    elif passed:
        result = "PASS<br>採点へ進む"
        result_css = "gate-result pass-box"
    else:
        result = "FAIL → 検証無効<br>総合点は算出しない"
        result_css = "gate-result fail-box"

    return (
        "<section class=\"gate\">"
        "<div class=\"gate-title\">物理整合性ゲート<br>配点外・必須</div>"
        f"<div class=\"gate-checks\">{''.join(check_html)}</div>"
        f"<div class=\"{result_css}\">{result}</div>"
        "</section>"
    )


def render_evaluation_html(payload: Mapping[str, Any]) -> str:
    """Render a self-contained HTML scorecard from an evaluation payload."""

    scores = payload.get("scores") if isinstance(payload.get("scores"), Mapping) else {}
    axes = scores.get("axes") if isinstance(scores.get("axes"), Mapping) else {}
    gate = payload.get("physics_gate") if isinstance(payload.get("physics_gate"), Mapping) else {}
    applicability = (
        payload.get("applicability") if isinstance(payload.get("applicability"), Mapping) else {}
    )
    status = str(payload.get("status") or "")
    total = scores.get("total")
    max_score = scores.get("max_score", applicability.get("applicable_max_score"))
    scenario = payload.get("scenario") or "ssos_eclss_loop"
    reason = applicability.get("reason")

    total_line = f"{_fmt_score(total)} / {_fmt_score(max_score)}"
    applicability_bits = [
        f"backend={_esc(applicability.get('backend'))}",
        f"survival={_esc(applicability.get('survival_enabled'))}",
        f"actor.mode={_esc(applicability.get('actor_mode'))}",
    ]
    if reason:
        applicability_bits.append(f"reason={_esc(reason)}")

    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>評価結果 — {_esc(scenario)}</title>
  <style>
    :root {{
      --ink: #17212b;
      --muted: #566573;
      --line: #b9c4cc;
      --soft: #eef2f4;
      --blue: #174f78;
      --blue-soft: #e8f1f7;
      --red: #8a2e2e;
      --red-soft: #f8eaea;
      --green: #296044;
      --green-soft: #e9f3ed;
      --gold: #765914;
      --gold-soft: #f6f0df;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background: #fff;
      font-family: -apple-system, BlinkMacSystemFont, "Hiragino Sans",
        "Yu Gothic", "Noto Sans JP", sans-serif;
      font-size: 13px;
      line-height: 1.45;
    }}
    main {{
      width: 100%;
      max-width: 1100px;
      margin: 0 auto;
      padding: 24px 28px;
    }}
    header {{
      display: grid;
      grid-template-columns: 1.6fr 1fr;
      gap: 20px;
      align-items: end;
      border-bottom: 3px solid var(--ink);
      padding-bottom: 12px;
      margin-bottom: 14px;
    }}
    h1 {{ margin: 0 0 4px; font-size: 24px; line-height: 1.2; }}
    h2 {{ margin: 0 0 8px; font-size: 15px; }}
    .subtitle {{ margin: 0; color: var(--muted); }}
    .principle {{
      border-left: 5px solid var(--red);
      background: var(--red-soft);
      padding: 10px 12px;
      font-weight: 700;
    }}
    .principle small {{
      display: block;
      color: var(--muted);
      font-weight: 500;
      margin-top: 2px;
    }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 10px;
      margin-bottom: 14px;
    }}
    .summary div {{
      border: 1px solid var(--line);
      background: var(--soft);
      padding: 10px 12px;
    }}
    .summary strong {{ display: block; font-size: 18px; margin-top: 2px; }}
    .gate {{
      display: grid;
      grid-template-columns: 170px 1fr 220px;
      gap: 12px;
      align-items: center;
      border: 2px solid var(--red);
      padding: 9px 12px;
      margin-bottom: 14px;
    }}
    .gate-title {{ color: var(--red); font-size: 15px; font-weight: 800; }}
    .gate-checks {{ display: flex; flex-wrap: wrap; gap: 4px 14px; }}
    .gate-checks .pass {{ color: var(--green); font-weight: 700; }}
    .gate-checks .fail {{ color: var(--red); font-weight: 700; }}
    .gate-checks .muted {{ color: var(--muted); }}
    .gate-result {{ padding: 7px 10px; font-weight: 700; text-align: center; }}
    .pass-box {{ background: var(--green-soft); color: var(--green); }}
    .fail-box {{ background: var(--red-soft); color: var(--red); }}
    .muted-box {{ background: var(--soft); color: var(--muted); }}
    .scorebar {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
      min-height: 54px;
      margin-bottom: 14px;
      border: 1px solid var(--line);
    }}
    .scorebar > div {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      padding: 8px 11px;
      border-right: 1px solid #fff;
      color: #fff;
      font-weight: 700;
    }}
    .scorebar > div:last-child {{ border-right: 0; }}
    .s-actor {{ background: var(--blue); }}
    .s-a {{ background: #39759b; }}
    .s-b {{ background: var(--green); }}
    .s-c {{ background: #8b6b25; }}
    .s-d {{ background: #644f1f; }}
    .s-e {{ background: #4e3d18; }}
    .points {{ font-size: 16px; white-space: nowrap; }}
    .axes {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 12px;
      margin-bottom: 14px;
    }}
    .card {{
      border: 1px solid var(--line);
      padding: 11px 13px;
      break-inside: avoid;
    }}
    .card.actor {{ border-top: 5px solid var(--blue); background: var(--blue-soft); }}
    .card.a {{ border-top: 5px solid #39759b; }}
    .card.b {{ border-top: 5px solid var(--green); }}
    .card.c {{ border-top: 5px solid var(--gold); }}
    .card.d, .card.e {{ border-top: 5px solid var(--gold); background: var(--gold-soft); }}
    ul {{ margin: 6px 0 0; padding-left: 18px; }}
    li {{ margin: 2px 0; overflow-wrap: anywhere; }}
    code {{ font-size: 11px; }}
    .note {{ margin: 6px 0 0; color: var(--muted); font-size: 11.5px; }}
    footer {{
      margin-top: 12px;
      padding-top: 8px;
      border-top: 1px solid var(--line);
      color: var(--muted);
      font-size: 11px;
    }}
    @media screen and (max-width: 800px) {{
      header, .summary, .gate {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
<main>
  <header>
    <div>
      <h1>ECLSSシミュレーション 評価結果</h1>
      <p class="subtitle">{_esc(scenario)} — schema {_esc(payload.get('schema_version'))}</p>
    </div>
    <div class="principle">
      最重要要求：物理法則を守ること
      <small>得点より物理整合性を優先する。物理ゲート不合格のランは採点せず、検証無効とする。</small>
    </div>
  </header>

  <section class="summary">
    <div>状態<strong>{_esc(_status_label(status))}</strong></div>
    <div>総合点<strong>{_esc(total_line)}</strong></div>
    <div>物理ゲート<strong>{"PASS" if gate.get("passed") else "FAIL / N/A"}</strong></div>
    <div>適用条件<strong>{' / '.join(applicability_bits)}</strong></div>
  </section>

  {_gate_section(gate, status)}
  {_scorebar(axes, max_score)}
  {_axis_cards(axes)}

  <p class="note">詳細の正本は同ディレクトリの <code>evaluation.json</code> です。この HTML は閲覧用の派生出力です。</p>
  <footer>
    <span>evidence: {_esc((payload.get('evidence') or {}).get('telemetry'))},
      {_esc((payload.get('evidence') or {}).get('events'))}</span>
    <span>generated from evaluation payload</span>
  </footer>
</main>
</body>
</html>
"""


__all__ = ["render_evaluation_html"]
