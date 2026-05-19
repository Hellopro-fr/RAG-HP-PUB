#!/usr/bin/env python3
"""
=============================================================================
compare.py - Diff entre 2 runs du harness
=============================================================================
Usage :
  python3 compare.py results/run_T0_baseline.json results/run_T1_after_low_cert_fix.json
                     [--md results/diff.md]
                     [--canary-max-drop 0.5]
                     [--critical-min-gain 0.3]

Sorties :
  - Tableau Markdown : keyword | audit | T0 | T1 | delta
  - Detection des regressions canari par DELTA RELATIF (au lieu d'un seuil absolu)
  - Liste des gros gagnants / gros perdants

Verdicts :
  - ROLLBACK    : un canari chute de plus de canary_max_drop vs T0 -> ROLLBACK !
  - VALIDE      : critical avg progresse d'au moins critical_min_gain ET aucun
                  canari ne chute de plus de canary_max_drop
  - SANS-EFFET  : critical avg ne progresse pas suffisamment

Seuils par defaut (overridables via CLI ou via keywords.json regression_threshold) :
  - canary_max_drop = 0.5  (un canari T1 < T0 - 0.5 -> ROLLBACK)
  - critical_min_gain = 0.3 (critical avg T1 < T0 + 0.3 -> SANS EFFET)

Changement 2026-05-15 :
  Anciennement seuil absolu canary_min_score=9.5. Abandonne car en baseline T0
  5/8 canaris sont sous 9.5 (calibration auto-score plus strict que humain).
  Le seuil relatif (delta vs T0) est plus juste : detecte une vraie regression
  introduite par la modif, pas la valeur absolue.
=============================================================================
"""

import argparse
import json
import sys
from pathlib import Path


def load_run(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_thresholds(t0_data, cli_canary_drop, cli_critical_gain):
    """Resolution des seuils : CLI override > keywords.json > defaults."""
    rt = t0_data.get("regression_threshold", {}) or {}
    canary_max_drop = (
        cli_canary_drop
        if cli_canary_drop is not None
        else rt.get("canary_max_drop", 0.5)
    )
    critical_min_gain = (
        cli_critical_gain
        if cli_critical_gain is not None
        else rt.get("critical_min_gain", 0.3)
    )
    return float(canary_max_drop), float(critical_min_gain)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("baseline", help="Run de reference (T0)")
    ap.add_argument("target", help="Run a comparer (T1, T2, etc.)")
    ap.add_argument("--md", default=None, help="Path output Markdown (default: stdout)")
    ap.add_argument("--canary-max-drop", type=float, default=None,
                    help="Override : un canari T1 < T0 - max_drop = ROLLBACK. Default = 0.5 ou valeur du keywords.json")
    ap.add_argument("--critical-min-gain", type=float, default=None,
                    help="Override : critical avg T1 < T0 + min_gain = SANS EFFET. Default = 0.3 ou valeur du keywords.json")
    args = ap.parse_args()

    t0 = load_run(args.baseline)
    t1 = load_run(args.target)

    canary_max_drop, critical_min_gain = get_thresholds(
        t0, args.canary_max_drop, args.critical_min_gain
    )

    # Index par query
    t0_by_q = {k["query"]: k for k in t0["keywords"]}
    t1_by_q = {k["query"]: k for k in t1["keywords"]}

    rows = []
    regressions_canary = []  # tuples (query, T0, T1, delta)
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

        # NOUVEAU 2026-05-15 : regression canari = delta < -canary_max_drop
        # (au lieu de score absolu < canary_min_score)
        if group == "canary" and delta < -canary_max_drop:
            regressions_canary.append((query, score_0, score_1, delta))

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
    md.append(f"- Seuils utilises : canary_max_drop = {canary_max_drop}, critical_min_gain = {critical_min_gain}")
    md.append("")
    md.append(f"## Synthese globale")
    md.append("")
    delta_global = round(t1['global_avg_auto_score'] - t0['global_avg_auto_score'], 2)
    delta_critical = round(t1['critical_avg_auto_score'] - t0['critical_avg_auto_score'], 2)
    delta_canary = round(t1['canary_avg_auto_score'] - t0['canary_avg_auto_score'], 2)
    md.append(f"| Indicateur | T0 (baseline) | T1 (target) | Delta |")
    md.append(f"|---|---|---|---|")
    md.append(f"| Global avg | {t0['global_avg_auto_score']} | {t1['global_avg_auto_score']} | {delta_global:+} |")
    md.append(f"| Critical avg | {t0['critical_avg_auto_score']} | {t1['critical_avg_auto_score']} | {delta_critical:+} |")
    md.append(f"| Canary avg | {t0['canary_avg_auto_score']} | {t1['canary_avg_auto_score']} | {delta_canary:+} |")
    md.append("")

    md.append(f"## Verdict")
    md.append("")
    if regressions_canary:
        md.append(f"### ROLLBACK OBLIGATOIRE - Regression canari")
        md.append(f"Les keywords canari suivants ont chute de plus de {canary_max_drop} pts vs baseline T0 :")
        for q, s0, s1, d in regressions_canary:
            md.append(f"- **{q}** : {s0} -> {s1} ({d:+})")
    elif delta_critical >= critical_min_gain:
        md.append(f"### VALIDE - Critical avg progresse de +{delta_critical} (seuil +{critical_min_gain}) sans regression canari")
    else:
        md.append(f"### SANS EFFET - Critical avg progresse de seulement +{delta_critical} (seuil +{critical_min_gain} non atteint)")
    md.append("")

    md.append(f"## Detail par keyword")
    md.append("")
    md.append("| Group | Query | Audit | T0 | T1 | Delta |")
    md.append("|---|---|---|---|---|---|")
    for r in rows:
        emoji = ""
        if r["group"] == "canary" and r["delta"] < -canary_max_drop:
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
