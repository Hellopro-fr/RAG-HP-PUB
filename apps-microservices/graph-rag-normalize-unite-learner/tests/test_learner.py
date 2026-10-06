"""Tests de Learner.process_unit() — dépendances mockées (pas de RabbitMQ/LLM/dynamique réels)."""
import asyncio
import json
from types import SimpleNamespace

from app.core.learner import (
    STATUS_PENDING,
    STATUS_SKIPPED,
    STATUS_VERIF_ERROR,
    Learner,
    ProcessingError,
)
from app.core.dynamic_client import DynamicValidationError

_REFERENTIEL = {"canonical_units": {"mass": "kilogram", "length": "meter", "count": "count"}}


class FakeApi:
    def __init__(self, appr=None):
        self._appr = appr or {}
        self.upserts = []
        self.saves = []
        self.save_batch_calls = 0
        self.llm_logged = []

    async def get_prompt(self, _id):
        return {"contenu_prompt": "P {label} {unite} {valeur} {dimensions_existantes} {unites_canoniques}"}

    async def apprentissage_get(self, unite, label_context):
        return dict(self._appr)

    async def apprentissage_upsert(self, unite, label_context, statut, **kwargs):
        self.upserts.append({"unite": unite, "statut": statut, **kwargs})
        return {"claimed": True}

    async def referentiel_save_batch(self, tables):
        # save atomique multi-tables : on aplatit en (table, rows) pour les assertions
        self.save_batch_calls += 1
        for table, rows in tables.items():
            self.saves.append((table, rows))
        return {"saved": sum(len(r) for r in tables.values()), "erreur": False}

    async def log_llm_usage(self, **kwargs):
        self.llm_logged.append(kwargs)
        return {}

    async def close(self):
        pass


class FakeDeepSeek:
    MODEL = "deepseek-v4-pro"

    def __init__(self, content, error=False):
        self._content = content
        self._error = error

    def chat(self, _message):
        if self._error:
            return {"code": 500, "error": "boom", "content": None, "response": None}
        return {
            "content": self._content,
            "response": SimpleNamespace(usage=SimpleNamespace(prompt_tokens=10, completion_tokens=20)),
        }


def _learner(api, proposal=None, llm_error=False, validate_results=None, validate_raises=False):
    content = json.dumps(proposal) if proposal is not None else "{}"

    def factory():
        return FakeDeepSeek(content, error=llm_error)

    calls = {"validate": 0, "last_values": None}
    results = list(validate_results or [])

    async def validate_fn(proposed, label, unit, values):
        calls["validate"] += 1
        calls["last_values"] = values
        if validate_raises:
            raise DynamicValidationError("dynamic injoignable")
        return results.pop(0) if results else {"ok": True, "valeur_canonique": 1.0, "unite_canonique": "kilogram"}

    learner = Learner(api_client=api, validate_fn=validate_fn, deepseek_factory=factory)
    return learner, calls


def _run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------------- #
def test_gate1_ok_saves_inactive_pending_activation():
    api = FakeApi(appr={})
    proposal = {"dimension": "mass", "pint_define": "quintal = 100 * kilogram", "confiance": 0.9}
    learner, calls = _learner(api, proposal)

    outcome = _run(learner.process_unit("quintal", "Poids", [3], _REFERENTIEL))

    assert outcome.status == STATUS_PENDING
    assert api.saves, "doit écrire des lignes"
    assert api.save_batch_calls == 1, "#4 : un seul appel save atomique (multi-tables)"
    # toutes INACTIVES + en revue
    for _table, rows in api.saves:
        for row in rows:
            assert row["actif"] == 0 and row["statut_revue"] == 1
    assert api.upserts[-1]["statut"] == STATUS_PENDING


def test_gate1_nok_marks_verification_error_no_save():
    api = FakeApi(appr={})
    proposal = {"dimension": "mass", "confiance": 0.9}
    learner, _ = _learner(api, proposal, validate_results=[{"ok": False}])

    outcome = _run(learner.process_unit("zorglub", "Bidon", [5], _REFERENTIEL))

    assert outcome.status == STATUS_VERIF_ERROR
    assert not api.saves
    assert api.upserts[-1]["statut"] == STATUS_VERIF_ERROR


def test_range_values_forwarded_in_single_call():
    # Le learner délègue min ET max au dynamique en UN seul appel (validation interne au moteur).
    api = FakeApi(appr={})
    proposal = {"dimension": "mass", "pint_define": "quintal = 100 * kilogram", "confiance": 0.9}
    learner, calls = _learner(api, proposal)  # validate_fn renvoie ok=True par défaut

    outcome = _run(learner.process_unit("quintal", "Poids", [3, 9], _REFERENTIEL))

    assert outcome.status == STATUS_PENDING
    assert calls["validate"] == 1                 # un seul appel
    assert calls["last_values"] == [3, 9]         # min ET max transmis


def test_range_nok_marks_verification_error():
    api = FakeApi(appr={})
    proposal = {"dimension": "mass", "pint_define": "quintal = 100 * kilogram", "confiance": 0.9}
    learner, calls = _learner(api, proposal, validate_results=[{"ok": False}])

    outcome = _run(learner.process_unit("quintal", "Poids", [3, 9], _REFERENTIEL))

    assert outcome.status == STATUS_VERIF_ERROR
    assert calls["validate"] == 1
    assert not api.saves


def test_llm_error_is_processing_error_and_tracked():
    api = FakeApi(appr={})
    learner, _ = _learner(api, proposal={"dimension": "mass"}, llm_error=True)

    try:
        _run(learner.process_unit("quintal", "Poids", [3], _REFERENTIEL))
        assert False, "doit lever ProcessingError"
    except ProcessingError:
        pass
    # #8 : l'échec LLM est tracké (etat=2)
    assert api.llm_logged and api.llm_logged[-1]["etat"] == 2


def test_dynamic_unreachable_is_processing_error():
    api = FakeApi(appr={})
    proposal = {"dimension": "mass", "pint_define": "quintal = 100 * kilogram", "confiance": 0.9}
    learner, _ = _learner(api, proposal, validate_raises=True)

    try:
        _run(learner.process_unit("quintal", "Poids", [3], _REFERENTIEL))
        assert False, "doit lever DynamicValidationError"
    except DynamicValidationError:
        pass
    assert not api.saves


def test_already_processed_unit_is_skipped():
    api = FakeApi(appr={"statut": STATUS_PENDING})
    learner, calls = _learner(api, proposal={"dimension": "mass"})

    outcome = _run(learner.process_unit("quintal", "Poids", [3], _REFERENTIEL))

    assert outcome.status == STATUS_SKIPPED
    assert calls["validate"] == 0          # ni LLM ni validation
    assert not api.saves


def test_no_values_marks_verification_error():
    api = FakeApi(appr={})
    proposal = {"dimension": "mass", "pint_define": "quintal = 100 * kilogram", "confiance": 0.9}
    learner, _ = _learner(api, proposal)

    outcome = _run(learner.process_unit("quintal", "Poids", [], _REFERENTIEL))

    assert outcome.status == STATUS_VERIF_ERROR
    assert not api.saves


def test_build_sections_emits_contract_keys():
    # CONTRAT (côté producteur) : les clés de sections doivent rester celles que le moteur
    # dynamique (from_payload) consomme. Si elles dérivent, la symbiose casse.
    api = FakeApi(appr={})
    learner, _ = _learner(api, proposal={"dimension": "mass"})
    proposal = {
        "dimension": "newdim", "unite_canonique": "kilogram",
        "pint_define": "x = 1 * kilogram", "reecriture": "x", "label_to_dimension": "Bidule",
    }
    sections = learner._build_sections(proposal, "x", current_canonicals={})
    assert set(sections.keys()) == {
        "unite_dimension", "dimension_canonique", "definitions", "reecriture", "label_dimension"
    }


def test_non_str_proposal_fields_do_not_crash():
    # Anti message-poison : un champ LLM non-str (dict/liste) ne doit PAS crasher (#2).
    api = FakeApi(appr={})
    learner, calls = _learner(api, proposal={"dimension": {"x": 1}, "pint_define": ["a", "b"]})

    outcome = _run(learner.process_unit("quintal", "Poids", [3], _REFERENTIEL))

    # pas d'exception : on a atteint la validation (et l'issue est terminale, pas processing_error)
    assert calls["validate"] == 1
    assert outcome.status in (STATUS_PENDING, STATUS_VERIF_ERROR)


def test_llm_no_proposal_is_processing_error():
    api = FakeApi(appr={})
    learner, _ = _learner(api, proposal={})  # pas de 'dimension'

    try:
        _run(learner.process_unit("quintal", "Poids", [3], _REFERENTIEL))
        assert False, "doit lever ProcessingError"
    except ProcessingError:
        pass
