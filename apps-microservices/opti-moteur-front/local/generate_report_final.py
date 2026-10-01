#!/usr/bin/env python3
"""Rapport HTML final avec P@5, P@10 par methode + color-coding des hits pertinents."""
import json
import html
import datetime

with open("bench_metrics.json", "r", encoding="utf-8") as f:
    metrics = json.load(f)


def esc(s):
    return html.escape(str(s or ""))


def is_relevant(categorie, gt):
    accept = set(gt.get("accept", []))
    if categorie in accept: return True
    for p in gt.get("prefix", []):
        if categorie and categorie.startswith(p): return True
    return False


def badge_color(p):
    if p >= 80: return "#059669"     # vert
    if p >= 60: return "#f59e0b"     # orange
    return "#dc2626"                  # rouge


def render_col(label, mode_data, gt, badge_bg="#3b82f6", highlight=False):
    if not mode_data:
        return f"<div class='col empty'><div class='col-header'><h3>{label}</h3></div><div class='no-data'>—</div></div>"
    hits = mode_data.get("hits", [])
    p5 = mode_data.get("p5", 0)
    p10 = mode_data.get("p10", 0)
    lat = mode_data.get("lat_ms", 0)
    rows = ""
    for i, h in enumerate(hits[:10], 1):
        nom = esc(h["nom"][:60])
        cat = esc(h["categorie"][:28])
        rel = is_relevant(h.get("categorie", ""), gt)
        rel_cls = "rel" if rel else "nonrel"
        icon = "✓" if rel else "✗"
        rows += f"<tr class='{rel_cls}'><td class='rank'>{i}</td><td class='icon'>{icon}</td><td>{nom}</td><td class='cat'>{cat}</td></tr>"

    hl = " highlight" if highlight else ""
    return f"""
    <div class="col{hl}">
        <div class="col-header" style="background:{badge_bg}">
            <h3>{label}</h3>
            <div class="stats">
                <span class="stat" title="Precision@5">P@5 <b style='color:{badge_color(p5)}'>{p5}%</b></span>
                <span class="stat" title="Precision@10">P@10 <b style='color:{badge_color(p10)}'>{p10}%</b></span>
                <span class="stat lat">{lat} ms</span>
            </div>
        </div>
        <table>
            <thead><tr><th>#</th><th>✓</th><th>Produit</th><th>Catégorie</th></tr></thead>
            <tbody>{rows}</tbody>
        </table>
    </div>
    """


# Agregats globaux
def global_avg(metric_key, mode):
    vals = [m["modes"][mode][metric_key] for m in metrics if mode in m["modes"]]
    return sum(vals) / len(vals) if vals else 0


modes_info = [
    ("ts_semantic",   "TS Sémantique (≈Milvus)", "#64748b"),
    ("ts_hybrid",     "🏆 TS Hybrid (filter_by)", "#059669"),
    ("os_bm25",       "OS BM25", "#0ea5e9"),
    ("os_hybrid",     "OS Hybrid", "#0ea5e9"),
    ("os_hybrid_v2",  "OS Hybrid v2 (filter)", "#0ea5e9"),
]

queries_html = ""
for m in metrics:
    q = m["query"]
    gt = m["ground_truth"]
    gt_text = []
    if gt.get("accept"):
        gt_text.append("accept: " + ", ".join(esc(c) for c in gt["accept"]))
    if gt.get("prefix"):
        gt_text.append("prefix: " + ", ".join(esc(p) for p in gt["prefix"]))
    gt_html = " · ".join(gt_text)

    filter_info = ""
    if m.get("filter_ts"):
        filter_info += f"<div class='flt flt-ts'>🎯 TS filter: <code>{esc(', '.join(m['filter_ts']))}</code></div>"
    if m.get("filter_os_v2"):
        filter_info += f"<div class='flt flt-os'>🎯 OS v2 filter: <code>{esc(', '.join(m['filter_os_v2']))}</code></div>"

    cols_html = ""
    for mode, label, color in modes_info:
        cols_html += render_col(label, m["modes"].get(mode), gt, color, highlight=(mode == "ts_hybrid"))

    queries_html += f"""
    <section class="query-block">
        <h2>"{esc(q)}"</h2>
        <div class='gt'>📖 Ground truth: <code>{gt_html}</code></div>
        {filter_info}
        <div class="cols">{cols_html}</div>
    </section>
    """

n = len(metrics)
kpi = ""
for mode, label, _ in modes_info:
    p5 = global_avg("p5", mode)
    p10 = global_avg("p10", mode)
    lat = global_avg("lat_ms", mode)
    win_cls = "winner" if mode == "ts_hybrid" else ""
    kpi += f"""
    <div class="kpi {win_cls}">
      <div class="kpi-label">{label}</div>
      <div class="kpi-row">
        <div class="kpi-item"><span class="v" style="color:{badge_color(p5)}">{p5:.0f}%</span><span class="l">P@5</span></div>
        <div class="kpi-item"><span class="v" style="color:{badge_color(p10)}">{p10:.0f}%</span><span class="l">P@10</span></div>
        <div class="kpi-item"><span class="v">{lat:.0f}</span><span class="l">ms</span></div>
      </div>
    </div>
    """

html_doc = f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<title>POC HelloPro — Pertinence 5-way (P@5, P@10)</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 0; background: #f5f7fa; color: #222; }}
  header {{ background: linear-gradient(135deg, #1e3a8a, #3b82f6); color: #fff; padding: 30px 40px; }}
  header h1 {{ margin: 0; font-size: 26px; }}
  header p {{ margin: 8px 0 0; opacity: 0.9; font-size: 14px; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin: 20px 40px; }}
  .kpi {{ background: #fff; padding: 14px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); border-top: 3px solid #e5e7eb; }}
  .kpi.winner {{ border-top-color: #059669; background: linear-gradient(180deg, #f0fdf4 0%, #fff 30%); }}
  .kpi-label {{ font-size: 12px; color: #333; font-weight: 600; margin-bottom: 10px; }}
  .kpi-row {{ display: flex; gap: 8px; justify-content: space-between; }}
  .kpi-item {{ display: flex; flex-direction: column; align-items: center; flex: 1; }}
  .kpi-item .v {{ font-size: 18px; font-weight: 700; }}
  .kpi-item .l {{ font-size: 10px; color: #666; text-transform: uppercase; margin-top: 2px; }}
  .query-block {{ background: #fff; margin: 16px 40px; padding: 16px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }}
  .query-block h2 {{ margin: 0 0 8px; font-size: 17px; color: #1e3a8a; }}
  .gt {{ font-size: 11px; color: #666; margin-bottom: 8px; }}
  .gt code {{ background: #f3f4f6; padding: 1px 5px; border-radius: 3px; font-size: 10px; }}
  .flt {{ padding: 4px 10px; border-radius: 5px; font-size: 11px; margin-bottom: 6px; display: inline-block; }}
  .flt-ts {{ background: #ecfdf5; color: #065f46; }}
  .flt-os {{ background: #e0f2fe; color: #0c4a6e; margin-left: 8px; }}
  .flt code {{ background: #fff; padding: 1px 5px; border-radius: 3px; }}
  .cols {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; margin-top: 10px; }}
  @media (max-width: 1600px) {{ .cols {{ grid-template-columns: repeat(3, 1fr); }} }}
  .col {{ background: #fafbfc; border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden; }}
  .col.highlight {{ border: 2px solid #059669; box-shadow: 0 0 0 3px rgba(5,150,105,0.1); }}
  .col.empty {{ opacity: 0.5; }}
  .col-header {{ padding: 7px 10px; color: #fff; }}
  .col-header h3 {{ margin: 0 0 3px; font-size: 12px; }}
  .stats {{ display: flex; gap: 6px; font-size: 10px; }}
  .stat {{ background: rgba(255,255,255,0.2); padding: 1px 5px; border-radius: 3px; color: #fff; }}
  .stat b {{ color: #fff; }}
  .stat.lat {{ margin-left: auto; background: rgba(0,0,0,0.25); }}
  .no-data {{ padding: 20px; text-align: center; color: #999; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 11px; }}
  th, td {{ padding: 5px 8px; text-align: left; border-bottom: 1px solid #f0f0f0; }}
  th {{ background: #fafbfc; font-weight: 600; color: #666; font-size: 10px; text-transform: uppercase; }}
  td.rank {{ font-weight: 600; color: #3b82f6; width: 20px; }}
  td.icon {{ width: 15px; text-align: center; font-weight: 700; }}
  tr.rel td.icon {{ color: #059669; }}
  tr.nonrel td.icon {{ color: #dc2626; }}
  tr.nonrel {{ background: #fef2f2; }}
  tr.rel {{ background: #f0fdf4; }}
  td.cat {{ color: #666; font-size: 10px; }}
  footer {{ text-align: center; padding: 30px; color: #666; font-size: 12px; }}
</style></head><body>
<header>
  <h1>⚡ POC HelloPro — OpenSearch vs Typesense · Pertinence</h1>
  <p>Benchmark {n} requêtes · Dataset 34 301 produits · Metrics P@5 / P@10 vs ground truth</p>
</header>

<div class="kpi-grid">{kpi}</div>

{queries_html}

<footer>POC généré le {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} · Lignes vertes = pertinent · Lignes rouges = non pertinent · Badge P@5 vert si ≥ 80%, orange si 60-79%, rouge sinon</footer>
</body></html>
"""

with open("bench_report_final.html", "w", encoding="utf-8") as f:
    f.write(html_doc)

print(f"[OK] bench_report_final.html généré ({n} queries, 5 colonnes, color-coded)")
