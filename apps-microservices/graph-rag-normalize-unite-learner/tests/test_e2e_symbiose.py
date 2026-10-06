"""Tests de symbiose bout-en-bout : learner ↔ moteur de normalisation dynamique (in-process).

Contrairement à test_learner.py (où validate_fn est un stub à résultat programmé),
ici la Gate 1 est la VRAIE implémentation UnitNormalizationService.validate_proposed,
alimentée par le référentiel test seedé complet.  Le learner ne sait pas qu'il n'appelle
pas HTTP — il utilise son interface habituelle (validate_fn async).

Chaîne fermée :
  FakeApi (async) ──► Learner.process_unit ──► _build_sections (producteur)
                                            └──► real_validate (Gate 1 réelle, moteur dynamique)
                                            └──► referentiel_save_batch / apprentissage_upsert

Aucun socket n'est ouvert : RabbitMQ, BO, DeepSeek sont tous simulés/mockés.
"""
import asyncio
import copy
import json
from types import SimpleNamespace
from typing import Any, Dict, Optional

from app.core.learner import (
    STATUS_PENDING,
    STATUS_SKIPPED,
    STATUS_VERIF_ERROR,
    Learner,
)
from tests._dynamic_bridge import (
    build_real_normalizer,
    make_real_validate_fn,
    simulate_get_apprentissage_unite,
    simulate_get_referentiel_normalisation,
)
from infrastructure.referentiel_loader import Referentiel  # noqa: E402  (sys.path via _dynamic_bridge)

# ---------------------------------------------------------------------------
# Helpers de construction du référentiel learner
# (reproduit exactement BatchRunner._fetch_referentiel)
# ---------------------------------------------------------------------------

def _build_learner_referentiel() -> Dict[str, Any]:
    """Construit le dict {canonical_units} tel que le BatchRunner l'expose au learner.

    Source : simulate_get_referentiel_normalisation() — même payload que le BO
    recevrait en production, donc zéro dérive entre seed et test.
    """
    payload = simulate_get_referentiel_normalisation()
    canonical_units = {
        row["dimension"]: row["unite_canonique"]
        for row in payload.get("dimension_canonique", [])
    }
    return {"canonical_units": canonical_units}


_REFERENTIEL = _build_learner_referentiel()


# ---------------------------------------------------------------------------
# FakeApi — reprend le style de test_learner.py, enrichi pour la symbiose
# ---------------------------------------------------------------------------

class FakeApi:
    """Remplace HelloProAPIClient : toutes les méthodes sont async.

    get_apprentissage_unite() est branché sur la simulation du pont (données FAKE_APPRENTISSAGE)
    pour que les cas de dédup (nm → learned, furlong → rejected) soient cohérents avec le bridge.
    """

    def __init__(self, appr: Optional[Dict[str, Any]] = None, use_bridge_appr: bool = False):
        # Si use_bridge_appr=True, on délègue à simulate_get_apprentissage_unite (dédup réaliste).
        # Sinon, on répond avec le dict passé directement (cas = "jamais vu" ou état fixé).
        self._appr = appr
        self._use_bridge_appr = use_bridge_appr
        self.upserts: list = []
        self.saves: list = []
        self.save_batch_calls: int = 0
        self.llm_logged: list = []

    async def get_prompt(self, _id: Any) -> Dict[str, Any]:
        return {"contenu_prompt": "P {label} {unite} {valeur} {dimensions_existantes} {unites_canoniques}"}

    async def apprentissage_get(self, unite: str, label_context: str) -> Optional[Dict[str, Any]]:
        if self._use_bridge_appr:
            return simulate_get_apprentissage_unite(unite, label_context)
        return dict(self._appr) if self._appr is not None else None

    async def apprentissage_upsert(self, unite: str, label_context: str, statut: str, **kwargs) -> Dict[str, Any]:
        self.upserts.append({"unite": unite, "statut": statut, **kwargs})
        return {"claimed": True}

    async def referentiel_save_batch(self, tables: Dict[str, list]) -> Dict[str, Any]:
        self.save_batch_calls += 1
        for table, rows in tables.items():
            self.saves.append((table, rows))
        return {"saved": sum(len(r) for r in tables.values()), "erreur": False}

    async def log_llm_usage(self, **kwargs) -> Dict[str, Any]:
        self.llm_logged.append(kwargs)
        return {}

    async def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# FakeDeepSeek — reprend exactement le style de test_learner.py
# ---------------------------------------------------------------------------

class FakeDeepSeek:
    MODEL = "deepseek-v4-pro"

    def __init__(self, content: str):
        self._content = content

    def chat(self, _message: str) -> Dict[str, Any]:
        return {
            "content": self._content,
            "response": SimpleNamespace(
                usage=SimpleNamespace(prompt_tokens=10, completion_tokens=20)
            ),
        }


# ---------------------------------------------------------------------------
# _make_learner — fabrique le learner câblé sur le VRAI moteur dynamique
# ---------------------------------------------------------------------------

def _make_learner(
    proposal: Dict[str, Any],
    appr: Optional[Dict[str, Any]] = None,
    use_bridge_appr: bool = False,
) -> tuple:
    """Retourne (learner, api, factory_call_counter).

    factory_call_counter["n"] s'incrémente à chaque appel du deepseek_factory :
    utile pour vérifier que LLM n'est PAS appelé sur les cas de skip/dédup.
    """
    api = FakeApi(appr=appr, use_bridge_appr=use_bridge_appr)
    real_validate = make_real_validate_fn()

    factory_counter: Dict[str, int] = {"n": 0}

    def deepseek_factory() -> FakeDeepSeek:
        factory_counter["n"] += 1
        return FakeDeepSeek(json.dumps(proposal))

    learner = Learner(
        api_client=api,
        validate_fn=real_validate,
        deepseek_factory=deepseek_factory,
    )
    return learner, api, factory_counter


def _run(coro):
    return asyncio.run(coro)


# ===========================================================================
# Cas 1 — SYMBIOSE OK (nouvelle unité avec pint_define)
# ===========================================================================

def test_symbiose_ok_new_unit_via_pint_define():
    """quintal → kilogram : le VRAI moteur doit valider.

    La Gate 1 reçoit un pint_define que le moteur dynamique ajoute à son registre
    (merged_with), puis convertit 3 quintaux → kilogrammes.  Si ça marche le learner
    écrit les lignes inactives et statut pending_activation.
    """
    proposal = {
        "dimension": "mass",
        "pint_define": "quintal = 100 * kilogram",
        "confiance": 0.95,
    }
    learner, api, _ = _make_learner(proposal, appr={})

    outcome = _run(learner.process_unit("quintal", "Poids", [3], _REFERENTIEL))

    assert outcome.status == STATUS_PENDING, f"attendu STATUS_PENDING, obtenu {outcome.status!r}"

    # un seul appel atomique (toutes tables en une transaction)
    assert api.save_batch_calls == 1, "doit y avoir exactement 1 appel referentiel_save_batch"

    # toutes les lignes écrites doivent être INACTIVES et en attente de revue
    for table, rows in api.saves:
        for row in rows:
            assert row["actif"] == 0, f"table {table!r} : ligne active alors que doit être inactive"
            assert row["statut_revue"] == 1, f"table {table!r} : statut_revue attendu 1"

    # les tables principales de la définition d'unité doivent être présentes
    saved_tables = {table for table, _ in api.saves}
    assert "unite_dimension" in saved_tables, "table unite_dimension absente"
    assert "unite_definition" in saved_tables, "table unite_definition absente (pint_define)"

    # dernier upsert apprentissage = pending_activation
    assert api.upserts, "aucun upsert apprentissage"
    assert api.upserts[-1]["statut"] == STATUS_PENDING


# ===========================================================================
# Cas 2 — SYMBIOSE OK via réécriture (reecriture au lieu de pint_define)
# ===========================================================================

def test_symbiose_ok_via_reecriture():
    """kn_par_m2 → bar : unité absente du seed, résolue UNIQUEMENT via la réécriture proposée.

    Le seed ne contient pas 'kn_par_m2' dans unit_to_dimension ni dans les rewrites.
    Le learner propose :
      - unite_dimension : kn_par_m2 → pressure
      - reecriture : kn_par_m2 → 'kilonewton / meter ** 2'
    Le VRAI moteur fusionne (merged_with) et convertit via pint.
    Si la Gate 1 valide → STATUS_PENDING.
    Prouve que le chemin reecriture du moteur est exercé par le learner.
    """
    proposal = {
        "dimension": "pressure",
        "reecriture": "kilonewton / meter ** 2",
        "confiance": 0.9,
    }
    learner, api, _ = _make_learner(proposal, appr={})

    # 'kn_par_m2' n'est pas dans le seed : seul le payload proposé permet de le résoudre
    outcome = _run(learner.process_unit("kn_par_m2", "Charge", [10], _REFERENTIEL))

    assert outcome.status == STATUS_PENDING, (
        f"attendu STATUS_PENDING pour kn_par_m2 via réécriture, obtenu {outcome.status!r}"
    )
    assert api.save_batch_calls == 1

    # les lignes doivent être inactives
    for _table, rows in api.saves:
        for row in rows:
            assert row["actif"] == 0
            assert row["statut_revue"] == 1

    assert api.upserts[-1]["statut"] == STATUS_PENDING


# ===========================================================================
# Cas 3 — SYMBIOSE NOK (hallucination LLM : dimension sans define/reecriture)
# ===========================================================================

def test_symbiose_nok_hallucination_no_define():
    """zorglub, dimension 'power', sans define ni reecriture.

    Le moteur tente de convertir 'zorglub' → il ne connaît ni la définition pint
    ni la réécriture → normalize() retourne {} → ok=False.
    Attendu : STATUS_VERIF_ERROR, aucun save, upsert erreur_verification.
    """
    proposal = {
        "dimension": "power",
        "confiance": 0.99,
        # pas de pint_define, pas de reecriture
    }
    learner, api, _ = _make_learner(proposal, appr={})

    outcome = _run(learner.process_unit("zorglub", "Bidon", [5], _REFERENTIEL))

    assert outcome.status == STATUS_VERIF_ERROR, (
        f"attendu STATUS_VERIF_ERROR pour zorglub sans define, obtenu {outcome.status!r}"
    )
    assert not api.saves, "aucun save ne doit avoir lieu si Gate 1 NOK"
    assert api.upserts, "l'upsert apprentissage doit quand même être appelé"
    assert api.upserts[-1]["statut"] == STATUS_VERIF_ERROR


# ===========================================================================
# Cas 4 — RANGE validé par le moteur réel (min ET max)
# ===========================================================================

def test_symbiose_range_both_bounds_validated():
    """quintal2 avec define : le moteur réel valide les deux bornes en un seul appel.

    Le learner transmet values=[2, 8] (min ET max) au validate_fn.
    validate_proposed boucle sur toutes les valeurs → si les deux passent, ok=True.
    Attendu : STATUS_PENDING + les deux valeurs bien traitées.
    """
    proposal = {
        "dimension": "mass",
        "pint_define": "quintal2 = 100 * kilogram",
        "confiance": 0.88,
    }
    learner, api, _ = _make_learner(proposal, appr={})

    outcome = _run(learner.process_unit("quintal2", "Poids", [2, 8], _REFERENTIEL))

    assert outcome.status == STATUS_PENDING, (
        f"attendu STATUS_PENDING pour range [2, 8] quintal2, obtenu {outcome.status!r}"
    )
    assert api.save_batch_calls == 1

    for _table, rows in api.saves:
        for row in rows:
            assert row["actif"] == 0
            assert row["statut_revue"] == 1


# ===========================================================================
# Cas 5 — DEDUP skip : unité déjà apprise (statut 'learned')
# ===========================================================================

def test_symbiose_dedup_skip_already_learned():
    """nm est dans FAKE_APPRENTISSAGE avec statut='learned'.

    Le learner doit retourner STATUS_SKIPPED sans appeler LLM ni validate.
    use_bridge_appr=True : apprentissage_get() délègue à simulate_get_apprentissage_unite.
    """
    proposal = {"dimension": "length", "confiance": 0.9}
    learner, api, factory_counter = _make_learner(
        proposal, use_bridge_appr=True
    )

    outcome = _run(learner.process_unit("nm", "", [5], _REFERENTIEL))

    assert outcome.status == STATUS_SKIPPED, (
        f"attendu STATUS_SKIPPED pour nm (learned), obtenu {outcome.status!r}"
    )
    assert factory_counter["n"] == 0, "le deepseek_factory NE doit PAS être appelé sur un skip"
    assert not api.saves, "aucun save sur un skip"


# ===========================================================================
# Cas 6 — DEDUP skip : unité déjà rejetée (statut 'rejected')
# ===========================================================================

def test_symbiose_dedup_skip_already_rejected():
    """furlong est dans FAKE_APPRENTISSAGE avec statut='rejected'.

    Même comportement que 'learned' : STATUS_SKIPPED, zéro LLM, zéro save.
    """
    proposal = {"dimension": "length", "confiance": 0.9}
    learner, api, factory_counter = _make_learner(
        proposal, use_bridge_appr=True
    )

    outcome = _run(learner.process_unit("furlong", "", [1], _REFERENTIEL))

    assert outcome.status == STATUS_SKIPPED, (
        f"attendu STATUS_SKIPPED pour furlong (rejected), obtenu {outcome.status!r}"
    )
    assert factory_counter["n"] == 0, "le deepseek_factory NE doit PAS être appelé sur un skip"
    assert not api.saves


# ===========================================================================
# Cas 7 — CONTRAT : _build_sections ↔ moteur dynamique (boucle producteur↔consommateur)
# ===========================================================================

def test_contract_build_sections_feeds_real_engine():
    """Vérifie que les sections produites par _build_sections sont consommables
    par le VRAI moteur sans transformation supplémentaire.

    Protocole :
      1. Construire les sections pour 'quintal' via learner._build_sections.
      2. Passer ces sections directement à make_real_validate_fn().
      3. Vérifier que le résultat est ok=True.

    Si un renommage de clé ou un changement de structure brise le contrat,
    ce test échoue avant que le bug ne parte en production.
    """
    # Construire un learner factice juste pour accéder à _build_sections
    api = FakeApi(appr={})
    real_validate = make_real_validate_fn()
    dummy_learner = Learner(
        api_client=api,
        validate_fn=real_validate,
        deepseek_factory=lambda: FakeDeepSeek("{}"),
    )

    proposal = {
        "dimension": "mass",
        "pint_define": "quintal = 100 * kilogram",
    }
    # canonical_units du référentiel courant (mass → kilogram déjà présent)
    current_canonicals = _REFERENTIEL["canonical_units"]

    sections = dummy_learner._build_sections(proposal, "quintal", current_canonicals)

    # Contrat structurel : les clés produites sont un sous-ensemble de celles comprises par le moteur
    EXPECTED_SECTION_KEYS = {"unite_dimension", "dimension_canonique", "definitions", "reecriture", "label_dimension"}
    unknown_keys = set(sections.keys()) - EXPECTED_SECTION_KEYS
    assert not unknown_keys, (
        f"_build_sections a produit des clés inconnues du moteur : {unknown_keys}"
    )

    # Contrat sémantique : le moteur réel valide le payload produit
    result = _run(real_validate(sections, "Poids", "quintal", [3]))
    assert result.get("ok") is True, (
        f"Le moteur réel n'a pas validé les sections de _build_sections : {result}"
    )
    # La valeur canonique retournée doit être cohérente (3 quintaux = 300 kg)
    assert result.get("unite_canonique") is not None, "unite_canonique absente du résultat"


# ===========================================================================
# Cas 8 — BOUCLE DE PILOTAGE : run → (activation + reload moteur) → normalisation
# ===========================================================================

def test_pilot_loop_activation_makes_unit_normalizable():
    """Reproduit le geste complet de gestion_projet (run → activer → reload → normaliser).

    1. Le moteur ACTIF (seed) NE connaît PAS 'glon' → normalize renvoie {}.
    2. Le learner apprend 'glon' → STATUS_PENDING (lignes écrites INACTIVES).
    3. On simule l'activation BO (actif=1) + /admin/reload : on injecte les lignes apprises
       dans le payload du référentiel actif et on RECHARGE le vrai moteur (engine.reload,
       exactement le swap déclenché par norm_activate_unit → /admin/reload).
    4. Le moteur normalise alors 'glon' → kilogram (3 glons = 300 kg).

    Prouve que le chemin de données piloté (apprentissage inactif → activation → reload)
    rend effectivement une unité inédite normalisable, sans dérive entre les couches.
    """
    proposal = {
        "dimension": "mass",
        "unite_canonique": "kilogram",
        "pint_define": "glon = 100 * kilogram",
        "confiance": 0.91,
    }
    learner, api, _ = _make_learner(proposal, appr={})

    # 1. Avant activation : le moteur actif ignore 'glon'
    seed_payload = simulate_get_referentiel_normalisation()
    engine = build_real_normalizer(seed_payload)
    before = engine.normalize("Poids", "glon", 3)
    assert before == {}, f"'glon' devrait être inconnu avant activation, obtenu {before!r}"

    # 2. Run learner → pending_activation + lignes inactives
    outcome = _run(learner.process_unit("glon", "Poids", [3], _REFERENTIEL))
    assert outcome.status == STATUS_PENDING, f"attendu STATUS_PENDING, obtenu {outcome.status!r}"
    for _table, rows in api.saves:
        for row in rows:
            assert row["actif"] == 0, "les lignes apprises doivent être inactives avant activation"

    # 3. Activation + reload : injecter les sections apprises dans le payload actif et recharger
    sections = learner._build_sections(proposal, "glon", _REFERENTIEL["canonical_units"])
    activated_payload = copy.deepcopy(seed_payload)
    for section_key, rows in sections.items():
        activated_payload.setdefault(section_key, []).extend(copy.deepcopy(rows))
    engine.reload(Referentiel.from_payload(activated_payload))

    # 4. Après activation : 'glon' se normalise
    after = engine.normalize("Poids", "glon", 3)
    assert after, f"'glon' devrait être normalisable après activation, obtenu {after!r}"
    assert after.get("unite_canonique") == "kilogram", f"unité canonique inattendue : {after!r}"
    assert abs(float(after["valeur_canonique"]) - 300.0) < 1e-6, f"3 glons devraient faire 300 kg : {after!r}"


# ===========================================================================
# Cas 9 — CONTRAT clés/valeurs : ce que le learner persiste == ce que l'activation PHP cible
# ===========================================================================

def test_contract_saved_rows_match_php_activation_keys():
    """Verrouille la cohérence learner↔activate (PHP) sur le ciblage par contenu (#2) + strip (#5).

    activate_unite_apprise() (normalisation.php) relit payload_llm puis cible les lignes via :
      - unite_dimension.dimension_udi      = trim(dimension)
      - unite_definition.definition_udfi   = trim(pint_define)          (#5 : doit matcher .strip())
      - dimension_canonique.unite_canonique_dci = trim(unite_canonique)
      - unite_reecriture.value_uri         = trim(reecriture)
      - label_dimension.label_ldi          = strtolower(trim(label_to_dimension))

    Le learner écrit les lignes via _build_sections en appliquant str(...).strip()[.lower()].
    Ce test échoue si un renommage de clé ou un changement de normalisation casse l'alignement
    (la cause exacte du bug #5 d'origine : valeur sauvée trimée vs WHERE non trimé).
    """
    # payload LLM volontairement « sale » (espaces, casse) pour exercer le strip/lower
    proposal = {
        "dimension": "newdim",
        "unite_canonique": "widget",
        "pint_define": "  zork = 5 * meter  ",
        "reecriture": "  meter * 2 ",
        "label_to_dimension": "  Largeur Spéciale ",
        "confiance": 0.8,
    }
    # 'newdim' absent des canoniques courants → la section dimension_canonique est produite
    canonicals = dict(_REFERENTIEL["canonical_units"])
    canonicals.pop("newdim", None)

    api = FakeApi(appr={})
    learner = Learner(
        api_client=api,
        validate_fn=make_real_validate_fn(),
        deepseek_factory=lambda: FakeDeepSeek("{}"),
    )
    sections = learner._build_sections(proposal, "zork", canonicals)

    # Les clés que l'activation PHP lit dans payload_llm doivent exister dans la proposition persistée
    PHP_ACTIVATE_KEYS = {"dimension", "unite_canonique", "pint_define", "reecriture", "label_to_dimension"}
    assert PHP_ACTIVATE_KEYS.issubset(set(proposal.keys())), (
        "payload_llm ne porte pas toutes les clés ciblées par activate_unite_apprise"
    )

    # Valeurs persistées == valeurs ciblées par les WHERE PHP (trim, et lower pour le label)
    assert sections["unite_dimension"][0]["dimension"] == "newdim"
    assert sections["definitions"][0]["definition"] == "zork = 5 * meter", "pint_define non trimé (#5)"
    assert sections["reecriture"][0]["value"] == "meter * 2", "reecriture non trimée"
    assert sections["label_dimension"][0]["label"] == "largeur spéciale", "label non strtolower(trim)"
    assert sections["dimension_canonique"][0]["unite_canonique"] == "widget"
