#!/usr/bin/env python3
"""Genere un rapport HTML side-by-side depuis bench_results.json."""
import json
import html

with open("bench_results.json", "r", encoding="utf-8") as f:
    results = json.load(f)

def esc(s):
    return html.escape(str(s or ""))

def render_hits(hits, label, latency, extra=""):
    rows = ""
    for i, h in enumerate(hits, 1):
        nom = esc(h["nom"][:70])
        cat = esc(h["categorie"][:30])
        score = h.get("score", 0)
        score_str = f"<span class='score'>{score:.2f}</span>" if score else ""
        rows += f"<tr><td class='rank'>{i}</td><td>{nom}</td><td class='cat'>{cat}</td><td class='score-cell'>{score_str}</td></tr>"
    return f"""
    <div class="col">
        <div class="col-header">
            <h3>{label}</h3>
            <div class="lat">{latency} ms {extra}</div>
        </div>
        <table>
            <thead><tr><th>#</th><th>Produit</th><th>Catégorie</th><th>Score</th></tr></thead>
            <tbody>{rows}</tbody>
        </table>
    </div>
    """

# Stats globales
n = len(results)
avg_sem = sum(r["semantic"]["lat_ms"] for r in results) / n
avg_bm  = sum(r["bm25"]["lat_ms"] for r in results) / n
avg_hyb = sum(r["hybrid"]["lat_ms"] for r in results) / n

# Milvus prod baseline (connu : 5000-7000 ms)
milvus_baseline = 6000

queries_html = ""
for r in results:
    filter_info = ""
    if r.get("filter_applied"):
        filter_info = f"<div class='filter-info'>🎯 Filter_by: <code>{esc(', '.join(r['filter_applied']))}</code></div>"
    detected = r.get("detected_cat") or "?"
    queries_html += f"""
    <section class="query-block">
        <h2>"{esc(r['query'])}" <span class="meta">{r['n_tokens']} mots · détecté: <em>{esc(detected)}</em> (conf={int(r['confidence']*100)}%)</span></h2>
        {filter_info}
        <div class="cols">
            {render_hits(r['semantic']['hits'], '🧠 Sémantique pur (simule Milvus)', r['semantic']['lat_ms'])}
            {render_hits(r['bm25']['hits'],     '🔤 BM25 pur (keyword)',            r['bm25']['lat_ms'])}
            {render_hits(r['hybrid']['hits'],   '⚡ Hybrid Typesense (solution)',   r['hybrid']['lat_ms'])}
        </div>
    </section>
    """

html_doc = f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<title>POC Typesense — Benchmark HelloPro</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 0; padding: 0; background: #f5f7fa; color: #222; }}
  header {{ background: linear-gradient(135deg, #1e3a8a, #3b82f6); color: #fff; padding: 30px 40px; }}
  header h1 {{ margin: 0; font-size: 28px; }}
  header p {{ margin: 8px 0 0; opacity: 0.9; }}
  .kpi-bar {{ display: flex; gap: 15px; margin: 20px 40px; padding: 20px; background: #fff; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }}
  .kpi {{ flex: 1; text-align: center; padding: 10px; border-right: 1px solid #eee; }}
  .kpi:last-child {{ border-right: none; }}
  .kpi .val {{ font-size: 26px; font-weight: 700; color: #1e3a8a; }}
  .kpi .label {{ font-size: 12px; color: #666; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 4px; }}
  .kpi.good .val {{ color: #059669; }}
  .kpi.bad .val {{ color: #dc2626; }}
  .query-block {{ background: #fff; margin: 20px 40px; padding: 20px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }}
  .query-block h2 {{ margin: 0 0 10px; font-size: 18px; color: #1e3a8a; }}
  .meta {{ font-weight: normal; font-size: 13px; color: #666; }}
  .filter-info {{ background: #ecfdf5; color: #065f46; padding: 8px 12px; border-radius: 6px; font-size: 13px; margin-bottom: 12px; }}
  .filter-info code {{ background: #fff; padding: 2px 6px; border-radius: 4px; }}
  .cols {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 15px; }}
  .col {{ background: #fafbfc; border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden; }}
  .col-header {{ padding: 10px 12px; background: #f3f4f6; border-bottom: 1px solid #e5e7eb; display: flex; justify-content: space-between; align-items: center; }}
  .col-header h3 {{ margin: 0; font-size: 13px; font-weight: 600; }}
  .lat {{ font-size: 11px; background: #3b82f6; color: #fff; padding: 2px 8px; border-radius: 10px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th, td {{ padding: 6px 10px; text-align: left; border-bottom: 1px solid #f0f0f0; }}
  th {{ background: #fafbfc; font-weight: 600; color: #666; font-size: 11px; text-transform: uppercase; }}
  td.rank {{ font-weight: 600; color: #3b82f6; width: 25px; }}
  td.cat {{ color: #666; font-size: 11px; }}
  td.score-cell {{ width: 50px; text-align: right; }}
  .score {{ background: #dbeafe; color: #1e40af; padding: 2px 6px; border-radius: 4px; font-weight: 600; font-size: 11px; }}
  footer {{ text-align: center; padding: 30px; color: #666; font-size: 13px; }}
</style></head><body>
<header>
  <h1>⚡ POC Typesense — Benchmark HelloPro</h1>
  <p>Comparaison sur {n} requêtes commerciales réelles · Dataset 30k produits (CamemBERT 1024 dims)</p>
</header>

<div class="kpi-bar">
  <div class="kpi bad"><div class="val">~{milvus_baseline}</div><div class="label">Milvus prod (baseline)</div></div>
  <div class="kpi"><div class="val">{avg_sem:.0f}</div><div class="label">TS Sémantique pur</div></div>
  <div class="kpi"><div class="val">{avg_bm:.0f}</div><div class="label">TS BM25 pur</div></div>
  <div class="kpi good"><div class="val">{avg_hyb:.0f}</div><div class="label">TS Hybrid (solution)</div></div>
  <div class="kpi good"><div class="val">×{milvus_baseline/avg_hyb:.0f}</div><div class="label">Gain vitesse</div></div>
</div>

{queries_html}

<footer>POC généré le {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')} · {n} requêtes · ms de latence en haut de chaque colonne</footer>
</body></html>
"""

with open("bench_report.html", "w", encoding="utf-8") as f:
    f.write(html_doc)

print(f"[OK] bench_report.html généré ({n} requêtes)")
