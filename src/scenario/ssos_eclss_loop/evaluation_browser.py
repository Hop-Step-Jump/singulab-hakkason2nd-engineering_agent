"""Multi-run evaluation browser (dropdown + side-by-side compare)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

AXIS_ORDER = (
    "actor_survival",
    "tcl",
    "environment_trajectory",
    "resource_recovery",
    "actor_decision",
    "physical_response",
)


def discover_evaluation_payloads(results_root: Path) -> Dict[str, Dict[str, Any]]:
    """Load ``evaluation.json`` for each run directory under ``results_root``."""

    root = Path(results_root)
    catalog: Dict[str, Dict[str, Any]] = {}
    if not root.is_dir():
        return catalog
    for entry in sorted(root.iterdir(), key=lambda path: path.name):
        if not entry.is_dir():
            continue
        path = entry / "evaluation.json"
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            catalog[entry.name] = payload
    return catalog


def render_evaluation_browser_html(
    catalog: Mapping[str, Mapping[str, Any]],
    *,
    default_run_id: Optional[str] = None,
) -> str:
    """Render a self-contained multi-run evaluation browser."""

    run_ids = list(catalog.keys())
    preferred = default_run_id if default_run_id in catalog else (run_ids[-1] if run_ids else "")
    payload_json = json.dumps(catalog, ensure_ascii=False)
    axis_json = json.dumps(list(AXIS_ORDER), ensure_ascii=False)
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ECLSS 評価ブラウザ</title>
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
    main {{ max-width: 1200px; margin: 0 auto; padding: 24px 28px; }}
    header {{
      display: grid;
      grid-template-columns: 1.4fr 1fr;
      gap: 16px;
      align-items: end;
      border-bottom: 3px solid var(--ink);
      padding-bottom: 12px;
      margin-bottom: 14px;
    }}
    h1 {{ margin: 0 0 4px; font-size: 24px; }}
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
      margin-top: 2px;
      color: var(--muted);
      font-weight: 500;
    }}
    .toolbar {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px 18px;
      align-items: end;
      border: 1px solid var(--line);
      background: var(--soft);
      padding: 12px 14px;
      margin-bottom: 14px;
    }}
    .toolbar label {{
      display: flex;
      flex-direction: column;
      gap: 4px;
      font-size: 11px;
      color: var(--muted);
      font-weight: 700;
    }}
    .toolbar select {{
      min-width: 180px;
      padding: 6px 8px;
      font-size: 13px;
    }}
    .toolbar .check {{
      flex-direction: row;
      align-items: center;
      gap: 8px;
      font-size: 13px;
      color: var(--ink);
      padding-bottom: 6px;
    }}
    .panels {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 14px;
    }}
    .panels.compare {{ grid-template-columns: 1fr 1fr; }}
    .panel {{
      border: 1px solid var(--line);
      padding: 12px 14px;
      min-width: 0;
    }}
    .panel h2 .tag {{
      margin-left: 8px;
      padding: 1px 6px;
      border: 1px solid currentColor;
      font-size: 10px;
      vertical-align: 1px;
    }}
    .kv {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 8px;
      margin-bottom: 10px;
    }}
    .kv div {{ background: var(--soft); padding: 8px 10px; }}
    .kv span {{ display: block; color: var(--muted); font-size: 11px; }}
    .kv strong {{ display: block; margin-top: 2px; overflow-wrap: anywhere; }}
    .scorebar {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
      margin: 10px 0;
      border: 1px solid var(--line);
    }}
    .scorebar > div {{
      display: flex;
      justify-content: space-between;
      gap: 6px;
      padding: 8px;
      color: #fff;
      font-weight: 700;
      border-right: 1px solid #fff;
    }}
    .scorebar > div:last-child {{ border-right: 0; }}
    .s-actor {{ background: var(--blue); }}
    .s-a {{ background: #39759b; }}
    .s-b {{ background: var(--green); }}
    .s-c {{ background: #8b6b25; }}
    .s-d {{ background: #644f1f; }}
    .s-e {{ background: #4e3d18; }}
    table.compare-table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 8px;
    }}
    table.compare-table th, table.compare-table td {{
      border: 1px solid var(--line);
      padding: 7px 8px;
      text-align: left;
      vertical-align: top;
    }}
    table.compare-table th {{ background: var(--soft); }}
    .delta-pos {{ color: var(--green); font-weight: 700; }}
    .delta-neg {{ color: var(--red); font-weight: 700; }}
    .note {{ color: var(--muted); font-size: 11.5px; margin-top: 10px; }}
    .empty {{
      border: 1px dashed var(--line);
      padding: 24px;
      color: var(--muted);
      text-align: center;
    }}
    @media screen and (max-width: 900px) {{
      header, .panels.compare {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
<main>
  <header>
    <div>
      <h1>ECLSS 評価ブラウザ</h1>
      <p class="subtitle">run を切り替えて閲覧し、別 run と比較できます</p>
    </div>
    <div class="principle">
      最重要要求：物理法則を守ること
      <small>得点より物理整合性を優先。詳細正本は各 run の evaluation.json。</small>
    </div>
  </header>

  <section class="toolbar">
    <label>表示する run
      <select id="primary-run"></select>
    </label>
    <label class="check">
      <input type="checkbox" id="compare-enabled">
      別 run と比較
    </label>
    <label>比較相手
      <select id="compare-run" disabled></select>
    </label>
  </section>

  <section id="compare-summary" hidden></section>
  <section class="panels" id="panels"></section>
  <p class="note">このファイルは results 直下の evaluation.html です。新規 run の評価書き出し時に自動更新されます。単一 run の詳細スナップショットは各 &lt;run_id&gt;/evaluation.html にも残ります。</p>
</main>
<script>
const CATALOG = {payload_json};
const AXIS_ORDER = {axis_json};
const AXIS_META = {{
  actor_survival: {{ short: "残存", css: "s-actor", points: 50 }},
  tcl: {{ short: "A TCL", css: "s-a", points: 10 }},
  environment_trajectory: {{ short: "B 生存環境", css: "s-b", points: 10 }},
  resource_recovery: {{ short: "C 資源余裕", css: "s-c", points: 10 }},
  actor_decision: {{ short: "D 判断", css: "s-d", points: 10 }},
  physical_response: {{ short: "E 応答", css: "s-e", points: 10 }},
}};
const STATUS = {{
  scored: "採点済",
  invalid: "検証無効",
  not_applicable: "適用対象外",
  incomplete: "不完全",
  right_censored: "右打ち切り",
  not_observed: "未観測",
}};
const DEFAULT_RUN = {json.dumps(preferred, ensure_ascii=False)};

function esc(value) {{
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}}

function fmt(value) {{
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number" && Number.isFinite(value)) {{
    if (Number.isInteger(value)) return String(value);
    return String(Math.round(value * 1000) / 1000);
  }}
  return esc(value);
}}

function statusLabel(status) {{
  return STATUS[status] || status || "—";
}}

function sideModel(side) {{
  if (!side) return "—";
  if (side.llm_active) {{
    return `${{fmt(side.provider)}} / ${{fmt(side.model)}}`;
  }}
  const configured = side.configured_model ? ` / configured=${{side.configured_model}}` : "";
  return `未使用（mode≠llm）${{configured}}`;
}}

function scorebar(payload) {{
  const axes = (payload.scores && payload.scores.axes) || {{}};
  const cells = AXIS_ORDER
    .filter((key) => axes[key])
    .map((key) => {{
      const meta = AXIS_META[key];
      const axis = axes[key];
      return `<div class="${{meta.css}}"><span>${{meta.short}}</span><span>${{fmt(axis.score)}} / ${{fmt(axis.max_score ?? meta.points)}}</span></div>`;
    }});
  if (!cells.length) {{
    const maxScore = payload.scores && payload.scores.max_score;
    cells.push(`<div class="s-actor"><span>総合</span><span>— / ${{fmt(maxScore)}}</span></div>`);
  }}
  return `<div class="scorebar">${{cells.join("")}}</div>`;
}}

function conditionsHtml(payload) {{
  const c = payload.run_conditions || {{}};
  const actor = c.actor || {{}};
  const design = c.design || {{}};
  const inv = c.initial_inventory || {{}};
  const items = [
    ["run_id", c.run_id],
    ["backend", c.backend],
    ["steps", c.steps],
    ["inject_failures", c.inject_failures],
    ["actor.mode", actor.mode],
    ["design.mode", design.mode],
    ["actor.llm", sideModel(actor)],
    ["design.llm", sideModel(design)],
    ["crew_size", c.crew_size],
    ["survival_enabled", c.survival_enabled],
    ["initial CO₂ kg", inv.co2_storage_kg],
    ["initial O₂ kg", inv.o2_storage_kg],
    ["initial water L", inv.product_water_l],
  ];
  return `<div class="kv">${{items.map(([k, v]) => `<div><span>${{esc(k)}}</span><strong>${{fmt(v)}}</strong></div>`).join("")}}</div>`;
}}

function panelHtml(runId, payload, tag) {{
  if (!payload) {{
    return `<article class="panel"><h2>${{esc(runId)}}</h2><p class="empty">evaluation.json がありません</p></article>`;
  }}
  const scores = payload.scores || {{}};
  const gate = payload.physics_gate || {{}};
  const total = `${{fmt(scores.total)}} / ${{fmt(scores.max_score)}}`;
  return `
    <article class="panel">
      <h2>${{esc(runId)}} <span class="tag">${{esc(tag)}}</span></h2>
      <div class="kv">
        <div><span>状態</span><strong>${{esc(statusLabel(payload.status))}}</strong></div>
        <div><span>総合点</span><strong>${{total}}</strong></div>
        <div><span>物理ゲート</span><strong>${{gate.passed ? "PASS" : "FAIL / N/A"}}</strong></div>
      </div>
      <h2>シミュレーション条件</h2>
      ${{conditionsHtml(payload)}}
      <h2>配点</h2>
      ${{scorebar(payload)}}
    </article>`;
}}

function axisScore(payload, key) {{
  const axis = (((payload || {{}}).scores || {{}}).axes || {{}})[key];
  return axis ? axis.score : null;
}}

function deltaClass(delta) {{
  if (delta === null || !Number.isFinite(delta) || delta === 0) return "";
  return delta > 0 ? "delta-pos" : "delta-neg";
}}

function compareTable(primaryId, primary, compareId, compare) {{
  const rows = [
    ["status", statusLabel(primary.status), statusLabel(compare.status), null],
    ["total", (primary.scores || {{}}).total, (compare.scores || {{}}).total,
      (Number.isFinite((primary.scores || {{}}).total) && Number.isFinite((compare.scores || {{}}).total))
        ? (primary.scores.total - compare.scores.total) : null],
    ["max_score", (primary.scores || {{}}).max_score, (compare.scores || {{}}).max_score, null],
    ["physics_gate", (primary.physics_gate || {{}}).passed, (compare.physics_gate || {{}}).passed, null],
  ];
  for (const key of AXIS_ORDER) {{
    const a = axisScore(primary, key);
    const b = axisScore(compare, key);
    const delta = (typeof a === "number" && typeof b === "number") ? (a - b) : null;
    rows.push([AXIS_META[key].short, a, b, delta]);
  }}
  const body = rows.map(([label, a, b, delta]) => `
    <tr>
      <td>${{esc(label)}}</td>
      <td>${{fmt(a)}}</td>
      <td>${{fmt(b)}}</td>
      <td class="${{deltaClass(delta)}}">${{delta === null ? "—" : ((delta > 0 ? "+" : "") + fmt(delta))}}</td>
    </tr>`).join("");
  return `
    <section class="panel" style="margin-bottom:14px">
      <h2>比較サマリ（Primary − Compare）</h2>
      <table class="compare-table">
        <thead>
          <tr>
            <th>項目</th>
            <th>${{esc(primaryId)}}</th>
            <th>${{esc(compareId)}}</th>
            <th>差</th>
          </tr>
        </thead>
        <tbody>${{body}}</tbody>
      </table>
    </section>`;
}}

function fillSelect(select, ids, selected) {{
  select.innerHTML = ids.map((id) =>
    `<option value="${{esc(id)}}"${{id === selected ? " selected" : ""}}>${{esc(id)}}</option>`
  ).join("");
}}

function render() {{
  const ids = Object.keys(CATALOG);
  const primarySelect = document.getElementById("primary-run");
  const compareSelect = document.getElementById("compare-run");
  const compareEnabled = document.getElementById("compare-enabled");
  const panels = document.getElementById("panels");
  const compareSummary = document.getElementById("compare-summary");

  if (!ids.length) {{
    panels.className = "panels";
    panels.innerHTML = `<div class="empty">evaluation.json を持つ run がありません。<br>plant_sim run 後にこのページが更新されます。</div>`;
    compareSummary.hidden = true;
    return;
  }}

  let primaryId = primarySelect.value || DEFAULT_RUN || ids[ids.length - 1];
  if (!CATALOG[primaryId]) primaryId = ids[ids.length - 1];
  fillSelect(primarySelect, ids, primaryId);

  const compareIds = ids.filter((id) => id !== primaryId);
  const comparing = compareEnabled.checked && compareIds.length > 0;
  compareSelect.disabled = !comparing;
  let compareId = compareSelect.value;
  if (!compareIds.includes(compareId)) compareId = compareIds[0] || "";
  fillSelect(compareSelect, compareIds, compareId);
  if (!comparing) compareSelect.value = compareId;

  const primary = CATALOG[primaryId];
  if (comparing && compareId) {{
    panels.className = "panels compare";
    panels.innerHTML = panelHtml(primaryId, primary, "Primary") + panelHtml(compareId, CATALOG[compareId], "Compare");
    compareSummary.hidden = false;
    compareSummary.innerHTML = compareTable(primaryId, primary, compareId, CATALOG[compareId]);
  }} else {{
    panels.className = "panels";
    panels.innerHTML = panelHtml(primaryId, primary, "Selected");
    compareSummary.hidden = true;
    compareSummary.innerHTML = "";
  }}
}}

document.getElementById("primary-run").addEventListener("change", render);
document.getElementById("compare-run").addEventListener("change", render);
document.getElementById("compare-enabled").addEventListener("change", render);
render();
</script>
</body>
</html>
"""


def write_evaluation_browser(
    results_root: Path,
    *,
    default_run_id: Optional[str] = None,
) -> Path:
    """Write ``evaluation.html`` under the results root for multi-run browsing."""

    root = Path(results_root)
    root.mkdir(parents=True, exist_ok=True)
    catalog = discover_evaluation_payloads(root)
    path = root / "evaluation.html"
    path.write_text(
        render_evaluation_browser_html(catalog, default_run_id=default_run_id),
        encoding="utf-8",
    )
    return path


__all__ = [
    "discover_evaluation_payloads",
    "render_evaluation_browser_html",
    "write_evaluation_browser",
]
