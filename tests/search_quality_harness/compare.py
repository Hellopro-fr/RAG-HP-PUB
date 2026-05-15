#!/usr/bin/env python3
"""
=============================================================================
compare.py - Diff entre 2 runs du harness
=============================================================================
Usage :
  python3 compare.py results/run_T0_baseline.json results/run_T1_after_low_cert_fix.json

Sorties :
  - Tableau Markdown : keyword | audit | T0 | T1 | delta
  - Detection des regressions canari (canary_min_score depasse a la baisse)
  - Liste des gros gagnants / gros perdants

Verdicts :
  - VALIDE     : critical avg progresse ET canary tous >= canary_min_score
  - REGRESSE   : un canary tombe en dessous de canary_min_score -> ROLLBACK !
  - SANS-EFFET : critical avg ne progresse pas (<+0.3)
=============================================================================
"""

import argparse
import json
import sys
from pathlib import Path


def load_run(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("baseline", help="Run de reference (T0)")
    ap.add_argument("target", help="Run a comparer (T1, T2, etc.)")
    ap.add_argument("--md", default=None, help="Path output Markdown (default: stdout)")
    args = ap.parse_args()

    t0 = load_run(args.baseline)
    t1 = load_run(args.target)

    # Index par query
    t0_by_q = {k["query"]: k for k in t0["keywords"]}
    t1_by_q = {k["query"]: k for k in t1["keywords"]}

    canary_min = t0.get("regression_threshold", {}).get("canary_min_score", 9.5)

    rows = []
    regressions_canary = []
    gains = []
    losses = []

    for query, k0 in t0_by_q.items():
        k1 = t1_by_q.get(query)
        if not k1:
            continue
        if "auto_score" not in k0 or "auto_score" not in k1:
            continue

        score_0 = k0["auto_score"]
        score_1 = k1["auto_score"]
        delta = round(score_1 - score_0, 2)
        group = k1.get("group") or k0.get("group", "?")

        rows.append({
            "query": query[:60],
            "group": group,
            "audit": k0.get("audit_score"),
            "T0": score_0,
            "T1": score_1,
            "delta": delta,
        })

        if group == "canary" and score_1 < canary_min:
            regressions_canary.append((query, score_0, score_1))

        if delta >= 1.0:
            gains.append((query, score_0, score_1, delta))
        elif delta <= -1.0:
            losses.append((query, score_0, score_1, delta))

    rows.sort(key=lambda r: (0 if r["group"] == "critical" else 1, r["audit"] or 0))

    # Markdown
    md = []
    md.append(f"# Comparaison harness : {Path(args.baseline).name} vs {Path(args.target).name}")
    md.append("")
    md.append(f"- Baseline run : `{Path(args.baseline).name}` ({t0.get('run_id','?')})")
    md.append(f"- Target run   : `{Path(args.target).name}` ({t1.get('run_id','?')})")
    md.append("")
    md.append(f"## Synthese globale")
    md.append("")
    md.append(f"| Indicateur | T0 (baseline) | T1 (target) | Delta |")
    md.append(f"|---|---|---|---|")
    md.append(f"| Global avg | {t0['global_avg_auto_score']} | {t1['global_avg_auto_score']} | {round(t1['global_avg_auto_score']-t0['global_avg_auto_score'], 2):+} |")
    md.append(f"| Critical avg | {t0['critical_avg_auto_score']} | {t1['critical_avg_auto_score']} | {round(t1['critical_avg_auto_score']-t0['critical_avg_auto_score'], 2):+} |")
    md.append(f"| Canary avg | {t0['canary_avg_auto_score']} | {t1['canary_avg_auto_score']} | {round(t1['canary_avg_auto_score']-t0['canary_avg_auto_score'], 2):+} |")
    md.append("")

    md.append(f"## Verdict")
    md.append("")
    if regressions_canary:
        md.append(f"### ROLLBACK OBLIGATOIRE - Regression canari")
        md.append(f"Les keywords canari suivants ont chute sous le seuil {canary_min} :")
        for q, s0, s1 in regressions_canary:
            md.append(f"- **{q}** : {s0} -> {s1}")
    else:
        delta_critical = t1['critical_avg_auto_score'] - t0['critical_avg_auto_score']
        if delta_critical >= 0.3:
            md.append(f"### VALIDE - Critical avg progresse de +{round(delta_critical, 2)} sans regression canari")
        else:
            md.append(f"### SANS EFFET - Critical avg progresse de seulement +{round(delta_critical, 2)} (seuil +0.3 non atteint)")
    md.append("")

    md.append(f"## Detail par keyword")
    md.append("")
    md.append("| Group | Query | Audit | T0 | T1 | Delta |")
    md.append("|---|---|---|---|---|---|")
    for r in rows:
        emoji = ""
        if r["group"] == "canary" and r["T1"] < canary_min:
            emoji = " (REGR)"
        elif r["delta"] >= 1.0:
            emoji = " (+)"
        elif r["delta"] <= -1.0:
            emoji = " (-)"
        md.append(f"| {r['group']} | {r['query']} | {r['audit']} | {r['T0']} | {r['T1']} | {r['delta']:+}{emoji} |")
    md.append("")

    if gains:
        md.append(f"## Gros gagnants (delta >= +1.0)")
        for q, s0, s1, d in sorted(gains, key=lambda x: -x[3]):
            md.append(f"- **{q}** : {s0} -> {s1} ({d:+})")
        md.append("")
    if losses:
        md.append(f"## Gros perdants (delta <= -1.0)")
        for q, s0, s1, d in sorted(losses, key=lambda x: x[3]):
            md.append(f"- **{q}** : {s0} -> {s1} ({d:+})")
        md.append("")

    output = "\n".join(md)
    if args.md:
        Path(args.md).parent.mkdir(parents=True, exist_ok=True)
        with open(args.md, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Markdown ecrit : {args.md}")
    else:
        print(output)

    # Exit code : 1 si regression canari (pour CI)
    sys.exit(1 if regressions_canary else 0)


if __name__ == "__main__":
    main()
