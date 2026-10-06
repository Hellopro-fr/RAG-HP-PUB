"""Tests des helpers du BatchRunner : parsing message + routage ack/nack (sans RabbitMQ réel)."""
import asyncio
import json
from types import SimpleNamespace

import pytest

from app.core.batch import BatchRunner, _parse_message
from app.core.dynamic_client import DynamicValidationError
from app.core.learner import (
    STATUS_PENDING,
    STATUS_PROCESSING_ERROR,
    STATUS_SKIPPED,
    STATUS_VERIF_ERROR,
    ProcessingError,
    UnitOutcome,
)


def _body(props):
    return json.dumps({"failed_node_entry": {"node": {"properties": props}}}).encode()


class FakeMessage:
    def __init__(self, body):
        self.body = body
        self.acked = False
        self.nacked_requeue = None

    async def ack(self):
        self.acked = True

    async def nack(self, requeue=False):
        self.nacked_requeue = requeue


# --------------------------------------------------------------------------- #
# _parse_message
# --------------------------------------------------------------------------- #
def test_parse_numeric():
    p = _parse_message(_body({"label": "Poids", "unite": "quintal", "type_donnee": "numeric", "valeur": 3}))
    assert p["unite_key"] == "quintal" and p["values"] == [3] and p["label"] == "Poids"


def test_parse_numeric_range_min_max():
    p = _parse_message(_body({"label": "T", "unite": "degC", "type_donnee": "numeric_range",
                              "valeur_min": 0, "valeur_max": 120}))
    assert p["values"] == [0, 120]


def test_parse_range_drops_none_bounds():
    p = _parse_message(_body({"label": "T", "unite": "degC", "type_donnee": "numeric_range",
                              "valeur_min": None, "valeur_max": 120}))
    assert p["values"] == [120]


def test_parse_missing_unit_returns_none():
    assert _parse_message(_body({"label": "X", "unite": None})) is None
    assert _parse_message(_body({"label": "X", "unite": "null"})) is None


def test_parse_bad_json_returns_none():
    assert _parse_message(b"not json") is None


def test_parse_unwrapped_payload():
    # message non enveloppé (failed_node_entry direct)
    body = json.dumps({"node": {"properties": {"unite": "kg", "type_donnee": "numeric", "valeur": 1}}}).encode()
    assert _parse_message(body)["unite_key"] == "kg"


# --------------------------------------------------------------------------- #
# _route : ack vs nack-requeue + rapport
# --------------------------------------------------------------------------- #
def _empty_report():
    return {"pending_activation": [], "verification_errors": [], "processing_errors": [], "skipped": []}


def _route(outcome, n_msgs=2):
    runner = BatchRunner(learner=None)
    msgs = [FakeMessage(b"{}") for _ in range(n_msgs)]
    group = {"unite_key": outcome.unite, "label": "L", "values": [1], "messages": msgs}
    report = _empty_report()
    asyncio.run(runner._route(group, outcome, report))
    return msgs, report


def test_route_pending_peeks_and_reports():
    # PEEK : message JAMAIS retiré du DLQ (nack requeue=True), même appris
    proposal = {"dimension": "mass", "pint_define": "quintal = 100 * kilogram", "confiance": 0.9}
    msgs, report = _route(UnitOutcome("quintal", STATUS_PENDING, "ok", proposal=proposal))
    assert all(m.nacked_requeue is True and not m.acked for m in msgs)
    # entrée enrichie pour le mail récap (unité + proposition)
    assert report["pending_activation"] == [
        {"unite": "quintal", "dimension": "mass", "pint_define": "quintal = 100 * kilogram",
         "reecriture": None, "confiance": 0.9}
    ]


def test_route_verification_error_peeks_and_reports():
    msgs, report = _route(UnitOutcome("zorglub", STATUS_VERIF_ERROR, "Gate 1 NOK"))
    assert all(m.nacked_requeue is True and not m.acked for m in msgs)
    assert report["verification_errors"] == [{"unite": "zorglub", "reason": "Gate 1 NOK"}]


def test_route_processing_error_peeks_and_reports():
    msgs, report = _route(UnitOutcome("quintal", STATUS_PROCESSING_ERROR, "LLM down"))
    assert all(m.nacked_requeue is True and not m.acked for m in msgs)
    assert report["processing_errors"] == [{"unite": "quintal", "error": "LLM down", "type": None}]


def test_route_skipped_peeks():
    msgs, report = _route(UnitOutcome("quintal", STATUS_SKIPPED, "déjà traité"))
    assert all(m.nacked_requeue is True and not m.acked for m in msgs)
    assert report["skipped"] == ["quintal"]


def test_route_processing_error_includes_type():
    # #3 : le type d'erreur (contract/transient/processing) remonte dans le rapport
    msgs, report = _route(UnitOutcome("quintal", STATUS_PROCESSING_ERROR, "HTTP 422", error_type="contract"))
    assert report["processing_errors"] == [{"unite": "quintal", "error": "HTTP 422", "type": "contract"}]


# --------------------------------------------------------------------------- #
# PEEK protégé (un échec isolé n'avorte pas le run)
# --------------------------------------------------------------------------- #
class _ExplodingMessage:
    async def nack(self, requeue=False):
        raise RuntimeError("canal fermé")


def test_peek_swallows_exceptions():
    runner = BatchRunner(learner=None)
    asyncio.run(runner._peek(_ExplodingMessage()))   # ne doit pas lever


# --------------------------------------------------------------------------- #
# #8 : garde santé du référentiel + #3 : classification dans _process_group
# --------------------------------------------------------------------------- #
class _FakeLearner:
    def __init__(self, referentiel_rows, process_raises=None):
        async def get_referentiel():
            return referentiel_rows
        self.api = SimpleNamespace(get_referentiel=get_referentiel)
        self._raises = process_raises

    async def process_unit(self, unite_key, label, values, referentiel):
        if self._raises:
            raise self._raises
        return UnitOutcome(unite_key, STATUS_PENDING, "ok")


def _runner(referentiel_rows=None, process_raises=None):
    rows = referentiel_rows if referentiel_rows is not None else {
        "dimension_canonique": [{"dimension": "mass", "unite_canonique": "kilogram"}]
    }
    return BatchRunner(_FakeLearner(rows, process_raises))


def test_fetch_referentiel_empty_canonicals_raises():
    runner = _runner(referentiel_rows={"dimension_canonique": []})
    with pytest.raises(ProcessingError):
        asyncio.run(runner._fetch_referentiel())


def test_fetch_referentiel_ok():
    canon = asyncio.run(_runner()._fetch_referentiel())
    assert canon["canonical_units"] == {"mass": "kilogram"}


def _group():
    return {"unite_key": "quintal", "label": "Poids", "values": [3], "messages": []}


def test_process_group_contract_error_type():
    runner = _runner(process_raises=DynamicValidationError("HTTP 422", permanent=True))
    outcome = asyncio.run(runner._process_group(_group(), {"canonical_units": {}}))
    assert outcome.status == STATUS_PROCESSING_ERROR and outcome.error_type == "contract"


def test_process_group_transient_error_type():
    runner = _runner(process_raises=DynamicValidationError("timeout", permanent=False))
    outcome = asyncio.run(runner._process_group(_group(), {"canonical_units": {}}))
    assert outcome.error_type == "transient"


def test_process_group_processing_error_type():
    runner = _runner(process_raises=ProcessingError("LLM down"))
    outcome = asyncio.run(runner._process_group(_group(), {"canonical_units": {}}))
    assert outcome.error_type == "processing"
