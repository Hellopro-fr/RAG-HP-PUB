"""
Simulation autonome du chemin BO de run_questionnaire_v2 (sans import du service).

Ne teste PAS le service complet (Milvus, LLM, API HelloPro). Reproduit la logique
métier touchée par l'ajout de la source BO dans
app/core/prix_service.py::run_questionnaire_v2 :

  - construction du payload matching_prix/matching/get (avec `source`),
  - substitution des placeholders du prompt 114 avec le garde-fou
    `nom_reponse_q1 or ""` (cas BO : pas de réponse Q1 → ne doit pas planter),
  - formatage d'un chunk de prix matché.

Lancer :  python tests/test_prix_service.py   |   pytest tests/test_prix_service.py
"""

PROMPT_114 = "Cat={nom_categorie} | Q1={nom_reponse_q1} | Req={requete_rag}\nCHUNKS:\n{chunks}"


def build_matching_payload(id_categorie, equivalences, id_reponse_q1, source):
    """Miroir du payload envoyé à matching_prix/matching/get."""
    return {
        "id_categorie": id_categorie,
        "equivalences": equivalences,
        "id_reponse_q1": id_reponse_q1,
        "source": source,
    }


def format_chunk(item):
    """Miroir simplifié du formatage chunk de run_questionnaire_v2."""
    prix = item.get("prix", {})
    return (
        f'Titre du produit : {prix.get("nom_produit", "N/A")}\n'
        f'Prix : {prix.get("prix", "")}'
    )


def build_final_prompt(prompt_text, chunks_text, requete_rag, nom_categorie, nom_reponse_q1):
    """Miroir des .replace() du prompt 114, avec garde-fou nom_reponse_q1 or ""."""
    p = prompt_text
    p = p.replace("{chunks}", chunks_text)
    p = p.replace("{requete_rag}", requete_rag)
    p = p.replace("{nom_categorie}", nom_categorie)
    p = p.replace("{nom_reponse_q1}", nom_reponse_q1 or "")
    return p


def test_payload_contains_source_bo():
    pl = build_matching_payload("2007702", [{"id_caracteristique": "1"}], None, "bo")
    assert pl["source"] == "bo"
    assert pl["id_reponse_q1"] is None


def test_payload_defaults_source_ia():
    pl = build_matching_payload("2007702", [], "100", "ia")
    assert pl["source"] == "ia"


def test_prompt_substitution_guards_none_nom_reponse_q1():
    # Cas BO : nom_reponse_q1 absent (None) → pas de crash, placeholder vidé
    out = build_final_prompt(PROMPT_114, "C1", "req", "Pont élévateur", None)
    assert "{nom_reponse_q1}" not in out
    assert "Q1= |" in out  # le placeholder a bien été remplacé par ""


def test_prompt_substitution_keeps_nom_reponse_q1_when_present():
    out = build_final_prompt(PROMPT_114, "C1", "req", "Pont", "2 colonnes")
    assert "Q1=2 colonnes |" in out


def test_chunk_format():
    item = {"prix": {"nom_produit": "Pont X", "prix": "100 EUR HT"}}
    chunk = format_chunk(item)
    assert "Titre du produit : Pont X" in chunk
    assert "100 EUR HT" in chunk


def _run():
    failures = 0
    for fn in (
        test_payload_contains_source_bo,
        test_payload_defaults_source_ia,
        test_prompt_substitution_guards_none_nom_reponse_q1,
        test_prompt_substitution_keeps_nom_reponse_q1_when_present,
        test_chunk_format,
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
