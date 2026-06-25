"""
Simulation autonome de l'équivalence BO (sans import du service).

Ce fichier NE teste PAS le service complet (RabbitMQ, LLM réel, API HelloPro).
Il **simule** la logique métier de la façade BO telle qu'implémentée dans
app/core/equivalence_generator.py (méthodes `_create_bo_question_prompt`,
`_generate_equivalence_bo`, `generate_equivalences_bo`) :

  questionnaire BO (liste plate) + jeu de caractéristiques + faux LLM
      → construction du prompt (intitulé + réponses anonymisées "reponse-N")
      → reverse mapping "reponse-N" → vrai id de réponse BO
      → exclusion cumulative des caractéristiques le long de la liste
      → équivalences "sauvegardées" par réponse

But : valider le comportement (mapping correct, exclusion cumulative, skip des
questions sans réponse) de façon déterministe et reproductible.

Lancer la simulation :   python tests/test_equivalence_generator.py
Lancer en pytest      :   pytest tests/test_equivalence_generator.py
"""
import json
import re


# ---------------------------------------------------------------------------
# Données d'entrée simulées — catégorie "Hélice de bateau"
# ---------------------------------------------------------------------------

JEU_CARACTERISTIQUE = [
    {
        "id_caracteristique": "701",
        "nom": "Type d'hélice",
        "type": "Text",
        "exemple": "à supprimer au nettoyage",
        "valeurs": [
            {"id_valeur": "1", "valeur": "Hélice à pales repliable", "micro_explication": "x"},
            {"id_valeur": "2", "valeur": "Hélice à pales orientables"},
            {"id_valeur": "3", "valeur": "Hélice à pas réglable"},
        ],
    },
    {"id_caracteristique": "702", "nom": "Nombre de pales", "type": "Numeric"},
    {"id_caracteristique": "703", "nom": "Diamètre", "unite": "pouce", "type": "Numeric"},
]

# Questionnaire BO au format natif (liste plate, comme ao_questions_criteres_algo_v2).
# La 4e question est volontairement sans réponse visible (choix vide) pour vérifier
# qu'elle est ignorée (correctif #1 : sinon save avec clé "reponse-N" littérale).
QUESTIONNAIRE_BO_RAW = [
    {
        "id": 91040, "question": "Type d'hélice de bateau", "description": "",
        "choix": [
            {"id": 91041, "choix": "Hélice à pales repliable"},
            {"id": 91042, "choix": "Hélice à pales orientables"},
            {"id": 91043, "choix": "Hélice à pas réglable"},
        ],
    },
    {
        "id": 91046, "question": "Nombre de pale de l'hélice", "description": "",
        "choix": [
            {"id": 91047, "choix": "2"},
            {"id": 91048, "choix": "3"},
            {"id": 91049, "choix": "4"},
        ],
    },
    {
        "id": 91052, "question": "Diamètre de l'hélice", "description": "",
        "choix": [
            {"id": 91053, "choix": "< à 15\""},
            {"id": 91054, "choix": "De 15 à 25\""},
        ],
    },
    # Question sans réponse exploitable (toutes les réponses étaient invisibles) :
    {"id": 91099, "question": "Question désactivée", "description": "", "choix": []},
]


# ---------------------------------------------------------------------------
# Logique BO simulée — miroir fidèle de equivalence_generator.py
# ---------------------------------------------------------------------------

def normalize_string(text):
    """Miroir de EquivalenceGenerator._normalize_string."""
    return re.sub(r'[^a-zA-Z0-9àâäéèêëïîôùûüç]', '', text.lower())


def get_questionnaire_bo_filter(raw):
    """Simule le filtre backend get_questionnaire_bo : on ne retourne pas les
    questions sans réponse (choix vide)."""
    return [q for q in raw if q.get("choix")]


def clean_jeu_caracteristique(jeu):
    """Miroir de _clean_jeu_caracteristique (retire exemple/micro_explication)."""
    cleaned = []
    for carac in jeu:
        c = carac.copy()
        c.pop("exemple", None)
        if "valeurs" in c:
            c["valeurs"] = [
                {k: v for k, v in val.items() if k not in ("micro_explication", "autres_formulations")}
                for val in c["valeurs"]
            ]
        cleaned.append(c)
    return cleaned


def filter_jeu(jeu, exclude_ids):
    """Miroir de _filter_jeu_caracteristique."""
    if not exclude_ids:
        return jeu
    exclude = {str(i) for i in exclude_ids}
    return [c for c in jeu if str(c.get("id_caracteristique", "")) not in exclude]


def create_bo_question_prompt(question):
    """Miroir de _create_bo_question_prompt (format BO natif)."""
    data_final = {
        "intitule-question": question.get("question", ""),
        "bulle-aide": question.get("description", "") or question.get("libelle_info", ""),
    }
    corres_reponse = {}
    for index, choix in enumerate(question.get("choix", []), start=1):
        key = f"reponse-{index}"
        data_final[key] = choix.get("choix", "")
        corres_reponse[key] = str(choix.get("id", "")).strip()
    return {"json_question": json.dumps(data_final, ensure_ascii=False), "corres_reponse": corres_reponse}


def normalize_single_equivalence(c):
    """Miroir de _normalize_single_equivalence (extraction tolérante des clés)."""
    id_carac = val_cibles = val_bloq = unite = niveau = justification = None
    for key, val in c.items():
        k = key.lower().replace("-", "_").replace(" ", "_")
        if ("id" in k and "caracteristique" in k) or k == "id_caracteristique":
            id_carac = val
        elif k == "id" and id_carac is None:
            id_carac = val
        elif "cible" in k and val_cibles is None:
            val_cibles = val
        elif "bloquant" in k and val_bloq is None:
            val_bloq = val
        elif "unite" in k and unite is None:
            unite = val
        elif "ponder" in k:
            if isinstance(val, dict):
                niveau = val.get("niveau")
                justification = val.get("justification")
            else:
                niveau = val
    return {
        "id_caracteristique": id_carac,
        "valeurs_cibles": val_cibles,
        "valeurs_bloquantes": val_bloq,
        "unite": unite,
        "ponderation": {"niveau": niveau, "justification": justification},
    }


def normalize_equivalence(data):
    """Miroir de _normalize_equivalence."""
    if isinstance(data, dict) and "equivalences" in data:
        items = data.get("equivalences", [])
        return [normalize_single_equivalence(i) for i in items if isinstance(i, dict)]
    if isinstance(data, list):
        return [normalize_single_equivalence(i) for i in data if isinstance(i, dict)]
    if isinstance(data, dict):
        return [normalize_single_equivalence(data)]
    return []


def extract_carac_ids(mapped):
    """Miroir de _extract_carac_ids_from_equivalences."""
    ids = set()
    for equivs in mapped.values():
        for equiv in normalize_equivalence(equivs):
            cid = equiv.get("id_caracteristique")
            if cid is not None:
                ids.add(str(cid))
    return list(ids)


def reverse_map(json_data, corres_reponse):
    """Miroir du reverse mapping de _generate_equivalence_bo."""
    if not corres_reponse:
        return json_data  # cas pathologique (question sans réponse) — non atteint après filtre
    mapped = {}
    for key, value in json_data.items():
        real_id = corres_reponse.get(key)
        if not real_id:
            for kmap, idr in corres_reponse.items():
                if normalize_string(key) == normalize_string(kmap):
                    real_id = idr
                    break
        if not real_id:
            raise ValueError(f"Pas de mapping trouvé pour la clé {key}")
        mapped[real_id] = normalize_equivalence(value)
    return mapped


def generate_equivalence_bo(question, jeu, exclude_carac_ids, fake_llm, trace):
    """Miroir de _generate_equivalence_bo : prompt → LLM → reverse map → 'save'."""
    jeu_eff = filter_jeu(jeu, exclude_carac_ids)
    jeu_clean = clean_jeu_caracteristique(jeu_eff)
    prompt = create_bo_question_prompt(question)
    carac_ids_dispo = [c["id_caracteristique"] for c in jeu_clean]

    llm_raw = fake_llm(question, carac_ids_dispo)          # simule l'appel Gemini
    mapped = reverse_map(llm_raw, prompt["corres_reponse"])  # "reponse-N" → id réel

    trace.append({
        "id_question": str(question["id"]),
        "caracs_disponibles": carac_ids_dispo,
        "corres_reponse": prompt["corres_reponse"],
        "equivalences_sauvees": mapped,
    })
    return mapped  # ce qui serait envoyé à equivalence/reponse_bo/save


def simulate_equivalences_bo(questionnaire_raw, jeu, fake_llm):
    """Miroir de generate_equivalences_bo : boucle + exclusion cumulative."""
    questionnaire = get_questionnaire_bo_filter(questionnaire_raw)
    cumulative_exclude = []
    saved = {}
    trace = []
    for question in questionnaire:
        mapped = generate_equivalence_bo(question, jeu, cumulative_exclude, fake_llm, trace)
        saved[str(question["id"])] = mapped
        cumulative_exclude.extend(extract_carac_ids(mapped))
    return {"saved": saved, "trace": trace, "cumulative_exclude": cumulative_exclude}


# ---------------------------------------------------------------------------
# Faux LLM déterministe : chaque question pointe vers UNE caractéristique
# ---------------------------------------------------------------------------

# id_question BO -> caractéristique "naturelle" de la question
_QUESTION_TO_CARAC = {"91040": "701", "91046": "702", "91052": "703"}


def fake_llm(question, caracs_disponibles):
    """Renvoie, pour la 1re réponse, une équivalence vers la carac de la question
    SI elle est encore disponible (non exclue). Simule un Gemini cohérent."""
    cid = _QUESTION_TO_CARAC.get(str(question["id"]))
    if cid is None or cid not in caracs_disponibles:
        return {}  # rien à mapper (carac déjà attribuée à une question précédente)
    return {
        "reponse-1": {
            "equivalences": [
                {
                    "id_caracteristique": cid,
                    "valeurs_cibles": [1],
                    "ponderation": {"niveau": "CRITIQUE", "justification": "sim"},
                }
            ]
        }
    }


# ---------------------------------------------------------------------------
# Assertions (exécutables aussi via pytest)
# ---------------------------------------------------------------------------

def test_question_sans_reponse_est_ignoree():
    filtered = get_questionnaire_bo_filter(QUESTIONNAIRE_BO_RAW)
    ids = [q["id"] for q in filtered]
    assert 91099 not in ids
    assert len(filtered) == 3


def test_reverse_mapping_utilise_les_vrais_ids_bo():
    res = simulate_equivalences_bo(QUESTIONNAIRE_BO_RAW, JEU_CARACTERISTIQUE, fake_llm)
    # Q1 : la clé "reponse-1" doit être devenue l'id BO 91041 (1er choix), pas "reponse-1"
    saved_q1 = res["saved"]["91040"]
    assert "91041" in saved_q1
    assert all(not str(k).startswith("reponse-") for k in saved_q1)


def test_equivalence_pointe_vers_la_bonne_caracteristique():
    res = simulate_equivalences_bo(QUESTIONNAIRE_BO_RAW, JEU_CARACTERISTIQUE, fake_llm)
    equiv = res["saved"]["91040"]["91041"][0]
    assert equiv["id_caracteristique"] == "701"
    assert equiv["ponderation"]["niveau"] == "CRITIQUE"


def test_exclusion_cumulative_le_long_de_la_liste():
    res = simulate_equivalences_bo(QUESTIONNAIRE_BO_RAW, JEU_CARACTERISTIQUE, fake_llm)
    trace = {t["id_question"]: t for t in res["trace"]}
    # Q1 voit les 3 caracs ; Q2 ne voit plus 701 ; Q3 ne voit plus 701 ni 702
    assert trace["91040"]["caracs_disponibles"] == ["701", "702", "703"]
    assert "701" not in trace["91046"]["caracs_disponibles"]
    assert "701" not in trace["91052"]["caracs_disponibles"]
    assert "702" not in trace["91052"]["caracs_disponibles"]
    assert set(res["cumulative_exclude"]) == {"701", "702", "703"}


def test_chaque_question_mappe_sa_caracteristique():
    res = simulate_equivalences_bo(QUESTIONNAIRE_BO_RAW, JEU_CARACTERISTIQUE, fake_llm)
    assert res["saved"]["91046"]["91047"][0]["id_caracteristique"] == "702"
    assert res["saved"]["91052"]["91053"][0]["id_caracteristique"] == "703"


# ---------------------------------------------------------------------------
# Exécution en simulation lisible (python tests/test_equivalence_generator.py)
# ---------------------------------------------------------------------------

def _run_simulation():
    print("=" * 70)
    print("SIMULATION — Équivalence BO (catégorie: Hélice de bateau)")
    print("=" * 70)
    res = simulate_equivalences_bo(QUESTIONNAIRE_BO_RAW, JEU_CARACTERISTIQUE, fake_llm)

    filtered = get_questionnaire_bo_filter(QUESTIONNAIRE_BO_RAW)
    print(f"\nQuestions reçues: {len(QUESTIONNAIRE_BO_RAW)} | retenues (avec réponses): {len(filtered)}")
    print("Question 91099 (sans réponse) ignorée:",
          91099 not in [q["id"] for q in filtered])

    for t in res["trace"]:
        print("\n" + "-" * 70)
        print(f"Question {t['id_question']}")
        print(f"  caracs disponibles (après exclusion cumulative) : {t['caracs_disponibles']}")
        print(f"  corres_reponse (reponse-N → id BO)             : {t['corres_reponse']}")
        for id_rep, equivs in t["equivalences_sauvees"].items():
            for e in equivs:
                print(f"  → réponse {id_rep} ↦ carac {e['id_caracteristique']} "
                      f"(cibles={e['valeurs_cibles']}, pondération={e['ponderation']['niveau']})")
        if not t["equivalences_sauvees"]:
            print("  → (aucune équivalence : carac déjà attribuée en amont)")

    print("\n" + "=" * 70)
    print(f"Exclusion cumulative finale : {sorted(res['cumulative_exclude'])}")
    print("=" * 70)

    # Assertions de la simulation
    failures = 0
    for fn in (
        test_question_sans_reponse_est_ignoree,
        test_reverse_mapping_utilise_les_vrais_ids_bo,
        test_equivalence_pointe_vers_la_bonne_caracteristique,
        test_exclusion_cumulative_le_long_de_la_liste,
        test_chaque_question_mappe_sa_caracteristique,
    ):
        try:
            fn()
            print(f"PASS: {fn.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL: {fn.__name__} — {e}")
    print(f"\n{'TOUS LES CONTRÔLES PASSENT' if failures == 0 else str(failures) + ' ÉCHEC(S)'}")
    return failures


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # console Windows cp1252 → UTF-8
    except Exception:
        pass
    sys.exit(1 if _run_simulation() else 0)
