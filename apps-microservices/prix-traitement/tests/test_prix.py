"""
Simulation autonome du contrat "source" côté router + branche BO du matching
(sans import du service ni du backend PHP).

Reproduit en Python :
  - le forwarding du paramètre `source` par le router (/prix/questionnaire-v2),
  - le routage de table des caracs Q1 selon la source (_mp_eqc_source) :
    BO → equivalence_question_caracteristique_bo, IA → _ia,
  - la règle de restriction allowed_ids (désactivée en mode BO car pas de
    table carac-prix par réponse BO ; les équivalences BO sont déjà la sélection).

NB : en BO comme en IA, `id_reponse_q1` est utilisé — c'est la réponse à la
première question du questionnaire (cf. question_reponses_bo.php, branche
question_number == 1).

Lancer :  python tests/test_prix.py   |   pytest tests/test_prix.py
"""


def router_forward_source(request):
    """Miroir : le router transmet request.source, défaut 'ia'."""
    return request.get("source", "ia")


def eqc_source(source):
    """Miroir de _mp_eqc_source (PHP) : table/colonnes des équivalences selon la source."""
    if str(source).lower() == "bo":
        return {
            "table": "equivalence_question_caracteristique_bo",
            "id_col": "id_reponse_bo_eqcbo",
            "carac_col": "id_caracteristique_eqcbo",
            "pond_col": "ponderation_eqcbo",
        }
    return {
        "table": "equivalence_question_caracteristique_ia",
        "id_col": "id_reponses_question_eqci",
        "carac_col": "id_caracteristique_eqci",
        "pond_col": "ponderation_eqci",
    }


def allowed_filter(equivalences, is_bo, strict, carac_prix):
    """Miroir : BO garde toutes les équivalences ; IA restreint à strict ∪ carac_prix."""
    if not is_bo and (strict or carac_prix):
        allowed = set(strict) | set(carac_prix)
        return [e for e in equivalences if e["id_caracteristique"] in allowed]
    return list(equivalences)


EQUIVS = [
    {"id_caracteristique": "10"},
    {"id_caracteristique": "20"},
    {"id_caracteristique": "30"},
]


def test_router_defaults_source_ia():
    assert router_forward_source({}) == "ia"
    assert router_forward_source({"source": "bo"}) == "bo"


def test_eqc_source_routes_bo_to_eqcbo():
    src = eqc_source("bo")
    assert src["table"] == "equivalence_question_caracteristique_bo"
    assert src["id_col"] == "id_reponse_bo_eqcbo"
    assert src["pond_col"] == "ponderation_eqcbo"


def test_eqc_source_defaults_to_eqci():
    src = eqc_source("ia")
    assert src["table"] == "equivalence_question_caracteristique_ia"
    assert src["id_col"] == "id_reponses_question_eqci"


def test_bo_keeps_all_equivalences():
    kept = allowed_filter(EQUIVS, is_bo=True, strict=["10"], carac_prix=[])
    assert len(kept) == len(EQUIVS)  # aucune restriction en BO


def test_ia_restricts_to_strict_union_caracprix():
    kept = allowed_filter(EQUIVS, is_bo=False, strict=["10"], carac_prix=["99"])
    ids = {e["id_caracteristique"] for e in kept}
    assert ids == {"10"}  # 20 et 30 écartés (hors strict ∪ carac_prix)


def _run():
    failures = 0
    for fn in (
        test_router_defaults_source_ia,
        test_eqc_source_routes_bo_to_eqcbo,
        test_eqc_source_defaults_to_eqci,
        test_bo_keeps_all_equivalences,
        test_ia_restricts_to_strict_union_caracprix,
    ):
        try:
            fn()
            print(f"PASS: {fn.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL: {fn.__name__} — {e}")
    print("\nTOUS LES CONTRÔLES PASSENT" if failures == 0 else f"\n{failures} ÉCHEC(S)")
    return failures


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(1 if _run() else 0)
