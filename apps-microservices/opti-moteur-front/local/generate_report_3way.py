#!/usr/bin/env python3
"""
Rapport HTML 3-way: OpenSearch (BM25+Hybrid) vs Typesense Hybrid.
Merge bench_opensearch.json + bench_results.json.
"""
import json
import html
import datetime

with open("bench_results.json", "r", encoding="utf-8") as f:
    ts_results = json.load(f)
with open("bench_opensearch.json", "r", encoding="utf-8") as f:
    os_results = json.load(f)

# Index OS par query
os_by_q = {r["query"]: r for r in os_results}


def esc(s):
    return html.escape(str(s or ""))


def render_hits(hits, label, latency, badge_color="#3b82f6"):
    rows = ""
    for i, h in enumerate(hits[:10], 1):
        nom = esc(h["nom"][:65])
        cat = esc(h["categorie"][:28])
        score = h.get("score", 0)
        score_str = f"<span class='score'>{score:.2f}</span>" if score else ""
        rows += f"<tr><td class='rank'>{i}</td><td>{nom}</td><td class='cat'>{cat}</td><td class='score-cell'>{score_str}</td></tr>"
    return f"""
    <div class="col">
        <div class="col-header">
            <h3>{label}</h3>
            <div class="lat" style="background:{badge_color}">{latency} ms</div>
        </div>
        <table>
            <thead><tr><th>#</th><th>Produit</th><th>Catégorie</th><th>Score</th></tr></thead>
            <tbody>{rows}</tbody>
        </table>
    </div>
    """


# Stats globales
n = len(ts_results)
avg_ts_sem = sum(r["semantic"]["lat_ms"] for r in ts_results) / n
avg_ts_hyb = sum(r["hybrid"]["lat_ms"] for r in ts_results) / n
os_n = len(os_results)
avg_os_bm = sum(r["os_bm25"]["lat_ms"] for r in os_results) / os_n
avg_os_knn = sum(r["os_knn"]["lat_ms"] for r in os_results) / os_n
avg_os_hyb = sum(r["os_hybrid"]["lat_ms"] for r in os_results) / os_n
milvus_baseline = 6000

queries_html = ""
for r in ts_results:
    q = r["query"]
    os_r = os_by_q.get(q, {})
    filter_info = ""
    if r.get("filter_applied"):
        filter_info = f"<div class='filter-info'>🎯 Typesense filter_by: <code>{esc(', '.join(r['filter_applied']))}</code></div>"
    detected = r.get("detected_cat") or "?"
    queries_html += f"""
    <section class="query-block">
        <h2>"{esc(q)}" <span class="meta">{r['n_tokens']} mots · catégorie détectée: <em>{esc(detected)}</em> ({int(r['confidence']*100)}%)</span></h2>
        {filter_info}
        <div class="cols">
            {render_hits(os_r.get('os_bm25', {}).get('hits', []), '🔤 OpenSearch BM25', os_r.get('os_bm25', {}).get('lat_ms', 0), '#0ea5e9')}
            {render_hits(os_r.get('os_hybrid', {}).get('hits', []), '⚡ OpenSearch Hybrid', os_r.get('os_hybrid', {}).get('lat_ms', 0), '#0ea5e9')}
            {render_hits(r['semantic']['hits'], '🧠 Typesense Sémantique (≈Milvus)', r['semantic']['lat_ms'], '#64748b')}
            {render_hits(r['hybrid']['hits'], '🚀 Typesense Hybrid (solution)', r['hybrid']['lat_ms'], '#059669')}
        </div>
    </section>
    """

html_doc = f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<title>POC HelloPro — OpenSearch vs Typesense (26 requêtes)</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 0; padding: 0; background: #f5f7fa; color: #222; }}
  header {{ background: linear-gradient(135deg, #1e3a8a, #3b82f6); color: #fff; padding: 30px 40px; }}
  header h1 {{ margin: 0; font-size: 26px; }}
  header p {{ margin: 8px 0 0; opacity: 0.9; font-size: 14px; }}
  .kpi-bar {{ display: flex; gap: 12px; margin: 20px 40px; padding: 18px; background: #fff; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); flex-wrap: wrap; }}
  .kpi {{ flex: 1; min-width: 100px; text-align: center; padding: 8px; border-right: 1px solid #eee; }}
  .kpi:last-child {{ border-right: none; }}
  .kpi .val {{ font-size: 22px; font-weight: 700; color: #1e3a8a; }}
  .kpi .label {{ font-size: 11px; color: #666; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 4px; }}
  .kpi.bad .val {{ color: #dc2626; }}
  .kpi.good .val {{ color: #059669; }}
  .kpi.os .val {{ color: #0ea5e9; }}
  .query-block {{ background: #fff; margin: 16px 40px; padding: 16px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }}
  .query-block h2 {{ margin: 0 0 8px; font-size: 17px; color: #1e3a8a; }}
  .meta {{ font-weight: normal; font-size: 12px; color: #666; }}
  .filter-info {{ background: #ecfdf5; color: #065f46; padding: 6px 10px; border-radius: 6px; font-size: 12px; margin-bottom: 10px; }}
  .filter-info code {{ background: #fff; padding: 2px 6px; border-radius: 4px; }}
  .cols {{ display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 10px; }}
  @media (max-width: 1400px) {{ .cols {{ grid-template-columns: 1fr 1fr; }} }}
  .col {{ background: #fafbfc; border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden; }}
  .col-header {{ padding: 8px 10px; background: #f3f4f6; border-bottom: 1px solid #e5e7eb; display: flex; justify-content: space-between; align-items: center; }}
  .col-header h3 {{ margin: 0; font-size: 12px; font-weight: 600; }}
  .lat {{ font-size: 10px; color: #fff; padding: 2px 7px; border-radius: 10px; font-weight: 600; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 11px; }}
  th, td {{ padding: 5px 8px; text-align: left; border-bottom: 1px solid #f0f0f0; }}
  th {{ background: #fafbfc; font-weight: 600; color: #666; font-size: 10px; text-transform: uppercase; }}
  td.rank {{ font-weight: 600; color: #3b82f6; width: 22px; }}
  td.cat {{ color: #666; font-size: 10px; }}
  td.score-cell {{ width: 45px; text-align: right; }}
  .score {{ background: #dbeafe; color: #1e40af; padding: 1px 5px; border-radius: 4px; font-weight: 600; font-size: 10px; }}
  footer {{ text-align: center; padding: 30px; color: #666; font-size: 12px; }}
</style></head><body>
<header>
  <h1>⚡ POC HelloPro — OpenSearch vs Typesense</h1>
  <p>Benchmark 3-way sur {n} requêtes commerciales · Dataset 34 301 produits (CamemBERT 1024 dims) · same VM same data</p>
</header>

<div class="kpi-bar">
  <div class="kpi bad"><div class="val">~{milvus_baseline}</div><div class="label">Milvus prod</div></div>
  <div class="kpi os"><div class="val">{avg_os_bm:.0f}</div><div class="label">OS BM25</div></div>
  <div class="kpi os"><div class="val">{avg_os_knn:.0f}</div><div class="label">OS kNN</div></div>
  <div class="kpi os"><div class="val">{avg_os_hyb:.0f}</div><div class="label">OS Hybrid</div></div>
  <div class="kpi"><div class="val">{avg_ts_sem:.0f}</div><div class="label">TS Sémantique</div></div>
  <div class="kpi good"><div class="val">{avg_ts_hyb:.0f}</div><div class="label">TS Hybrid</div></div>
  <div class="kpi good"><div class="val">×{milvus_baseline/avg_ts_hyb:.0f}</div><div class="label">Gain vitesse</div></div>
</div>

{queries_html}

<footer>POC généré le {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} · OpenSearch 2.19.1 + Typesense 27.1 sur même WSL2 · {n} requêtes pré-embeddées CamemBERT</footer>
</body></html>
"""

with open("bench_report_3way.html", "w", encoding="utf-8") as f:
    f.write(html_doc)

print(f"[OK] bench_report_3way.html généré ({n} requêtes, 4 colonnes par query)")
