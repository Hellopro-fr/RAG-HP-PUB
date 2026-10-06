"""
Tests de l'API REST FastAPI (infrastructure/rest_api.py).

Stratégie de construction :
  - `infrastructure.rest_api.settings` est monkeypatché avec un objet SimpleNamespace
    portant REFERENTIEL_TTL_SECONDS=0 et RELOAD_AUTH_TOKEN=<token>.
    Pourquoi ce module et pas app.config ? rest_api.py fait
    `from app.config import settings`, ce qui lie le nom `settings` dans le namespace
    de rest_api — c'est donc ce binding qu'il faut remplacer, pas la source en app.config.
  - Le référentiel est alimenté par build_legacy_payload() (données du service historique)
    -> données stables et déterministes, aucun appel réseau.
  - reload_fn est un coroutine fictif retournant un dict de compteurs.
  - TestClient est utilisé comme context manager pour déclencher le lifespan proprement.
"""

import types
import pytest

from fastapi.testclient import TestClient

from application.normalization_use_case import NormalizationUseCase
from infrastructure.referentiel_loader import Referentiel
import infrastructure.rest_api as rest_api_module
from infrastructure.rest_api import create_app
from infrastructure.unit_normalization_service import UnitNormalizationService
from scripts.legacy_referentiel import build_legacy_payload


# ---------------------------------------------------------------------------
# Helper : construit un objet settings de substitution (SimpleNamespace).
# SimpleNamespace est mutable et ne subit pas la validation Pydantic, ce qui
# évite toute friction avec le freeze / validation de BaseSettings v2.
# ---------------------------------------------------------------------------

def _make_settings(*, ttl: int, token: str) -> types.SimpleNamespace:
    """Objet settings minimal suffisant pour create_app / lifespan."""
    return types.SimpleNamespace(
        REFERENTIEL_TTL_SECONDS=ttl,
        RELOAD_AUTH_TOKEN=token,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def _referentiel() -> Referentiel:
    return Referentiel.from_payload(build_legacy_payload())


@pytest.fixture(scope="module")
def _use_case(_referentiel: Referentiel) -> NormalizationUseCase:
    return NormalizationUseCase(UnitNormalizationService(_referentiel))


@pytest.fixture()
def client(_use_case: NormalizationUseCase, monkeypatch):
    """
    TestClient avec TTL=0 (pas de boucle de refresh) et sans token d'auth.
    On patche `infrastructure.rest_api.settings` — c'est le nom bindé par
    `from app.config import settings` dans rest_api.py.
    """
    monkeypatch.setattr(rest_api_module, "settings", _make_settings(ttl=0, token=""))

    async def _dummy_reload_fn():
        return {"definitions": 78, "unit_to_dimension": 120}

    application = create_app(_use_case, _dummy_reload_fn)
    with TestClient(application) as c:
        yield c


@pytest.fixture()
def client_with_token(_use_case: NormalizationUseCase, monkeypatch):
    """Client dont le token de rechargement est fixé à 'secret-token'."""
    monkeypatch.setattr(
        rest_api_module, "settings", _make_settings(ttl=0, token="secret-token")
    )

    async def _dummy_reload_fn():
        return {"definitions": 78}

    application = create_app(_use_case, _dummy_reload_fn)
    with TestClient(application) as c:
        yield c


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_returns_200(self, client):
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_body_is_ok(self, client):
        response = client.get("/health")
        assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# /normalize/quantity
# ---------------------------------------------------------------------------

class TestNormalizeQuantity:
    def test_mass_kg_1500_returns_kilogram(self, client):
        response = client.post(
            "/normalize/quantity",
            json={"label": "Poids", "unit": "kg", "value": 1500},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["valeur_canonique"] == pytest.approx(1500.0)
        assert body["unite_canonique"] == "kilogram"

    def test_length_mm_2500_converts_to_meter(self, client):
        response = client.post(
            "/normalize/quantity",
            json={"label": "Hauteur", "unit": "mm", "value": 2500},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["valeur_canonique"] == pytest.approx(2.5)
        assert body["unite_canonique"] == "meter"

    def test_power_cv_converts_to_watt(self, client):
        response = client.post(
            "/normalize/quantity",
            json={"label": "Puissance", "unit": "CV", "value": 1},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        # 1 CV = 735.49875 W
        assert body["valeur_canonique"] == pytest.approx(735.49875, rel=1e-4)
        assert body["unite_canonique"] == "watt"

    def test_sound_level_dba_returns_decibel(self, client):
        response = client.post(
            "/normalize/quantity",
            json={"label": "Niveau sonore", "unit": "dB(A)", "value": 72},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["valeur_canonique"] == pytest.approx(72.0)
        assert body["unite_canonique"] == "decibel"

    def test_humidity_percent_bypass_returns_count(self, client):
        """% est un bypass -> valeur inchangée, unité canonique 'count'."""
        response = client.post(
            "/normalize/quantity",
            json={"label": "Humidité", "unit": "%", "value": 60},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["valeur_canonique"] == pytest.approx(60.0)
        assert body["unite_canonique"] == "count"

    def test_tolerance_string_value_parsed(self, client):
        """Valeur sous forme de chaîne '+/- 2' doit être parsée en 2.0, puis convertie."""
        response = client.post(
            "/normalize/quantity",
            json={"label": "Tolérance", "unit": "mm", "value": "+/- 2"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        # 2 mm = 0.002 m
        assert body["valeur_canonique"] == pytest.approx(0.002, rel=1e-4)
        assert body["unite_canonique"] == "meter"

    def test_unknown_unit_without_matching_label_returns_success_false(self, client):
        """Unité totalement inconnue -> success False, pas d'erreur 500."""
        response = client.post(
            "/normalize/quantity",
            json={"label": "Caractéristique", "unit": "ZZZUNIT_INCONNU", "value": 42},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is False
        assert body["valeur_canonique"] is None
        assert body["unite_canonique"] is None
        assert "error_message" in body

    def test_unit_none_falls_back_to_label_resolution(self, client):
        """unit=null -> None -> résolution par label (Poids -> mass -> kilogram)."""
        response = client.post(
            "/normalize/quantity",
            json={"label": "Poids", "unit": None, "value": 10},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["unite_canonique"] == "kilogram"

    def test_data_type_non_numeric_returns_success_false(self, client):
        """data_type non reconnu -> normalizer retourne {} -> success False."""
        response = client.post(
            "/normalize/quantity",
            json={"label": "Poids", "unit": "kg", "value": 10, "data_type": "text"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is False

    def test_volume_litres_rewrite_returns_liter(self, client):
        """'litres' est réécrit en 'liter' via les règles de réécriture."""
        response = client.post(
            "/normalize/quantity",
            json={"label": "Volume cuve", "unit": "litres", "value": 200},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["valeur_canonique"] == pytest.approx(200.0)
        assert body["unite_canonique"] == "liter"

    def test_rotation_speed_tr_per_min_returns_hertz(self, client):
        """tr/min réécrit en rpm -> dimension [frequency] -> hertz."""
        response = client.post(
            "/normalize/quantity",
            json={"label": "Vitesse de rotation", "unit": "tr/min", "value": 1450},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["unite_canonique"] == "hertz"

    def test_flow_rate_m3_per_h_returns_liter_per_minute(self, client):
        """m3/h -> volume/time -> liter / minute."""
        response = client.post(
            "/normalize/quantity",
            json={"label": "Débit", "unit": "m3/h", "value": 12},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["unite_canonique"] == "liter / minute"

    def test_temperature_celsius_returns_celsius(self, client):
        """°C -> temperature ; pint rend l'unité 'degree_Celsius' (pas de conversion de magnitude)."""
        response = client.post(
            "/normalize/quantity",
            json={"label": "Température", "unit": "°C", "value": 21},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["unite_canonique"] == "degree_Celsius"
        assert body["valeur_canonique"] == 21


# ---------------------------------------------------------------------------
# /normalize/range
# ---------------------------------------------------------------------------

class TestNormalizeRange:
    def test_length_mm_range_converts_to_meter(self, client):
        """100 mm – 2500 mm -> 0.1 m – 2.5 m."""
        response = client.post(
            "/normalize/range",
            json={"label": "Hauteur", "unit": "mm", "min_value": 100, "max_value": 2500},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["valeur_min_canonique"] == pytest.approx(0.1)
        assert body["valeur_max_canonique"] == pytest.approx(2.5)
        assert body["unite_canonique"] == "meter"

    def test_mass_kg_range_preserves_kilogram(self, client):
        response = client.post(
            "/normalize/range",
            json={"label": "Poids", "unit": "kg", "min_value": 50, "max_value": 1500},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["valeur_min_canonique"] == pytest.approx(50.0)
        assert body["valeur_max_canonique"] == pytest.approx(1500.0)
        assert body["unite_canonique"] == "kilogram"

    def test_range_unknown_unit_returns_success_false(self, client):
        response = client.post(
            "/normalize/range",
            json={"label": "Inconnue", "unit": "ZZZUNIT", "min_value": 1, "max_value": 10},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is False

    def test_range_only_min_value_provided(self, client):
        """max_value absent (None) -> seule la valeur min est normalisée."""
        response = client.post(
            "/normalize/range",
            json={"label": "Poids", "unit": "kg", "min_value": 5},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["valeur_min_canonique"] == pytest.approx(5.0)
        assert body["valeur_max_canonique"] is None

    def test_range_only_max_value_provided(self, client):
        """min_value absent (None) -> seule la valeur max est normalisée."""
        response = client.post(
            "/normalize/range",
            json={"label": "Poids", "unit": "kg", "max_value": 100},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["valeur_max_canonique"] == pytest.approx(100.0)
        assert body["valeur_min_canonique"] is None


# ---------------------------------------------------------------------------
# /normalize/batch
# ---------------------------------------------------------------------------

class TestNormalizeBatch:
    def test_batch_two_valid_items(self, client):
        response = client.post(
            "/normalize/batch",
            json={
                "items": [
                    {"label": "Poids", "unit": "kg", "value": 10},
                    {"label": "Hauteur", "unit": "mm", "value": 500},
                ]
            },
        )
        assert response.status_code == 200
        results = response.json()
        assert len(results) == 2
        assert results[0]["success"] is True
        assert results[0]["unite_canonique"] == "kilogram"
        assert results[1]["success"] is True
        assert results[1]["unite_canonique"] == "meter"

    def test_batch_mixed_valid_and_invalid(self, client):
        """Le batch retourne autant d'entrées que d'items, chacun avec son propre succès."""
        response = client.post(
            "/normalize/batch",
            json={
                "items": [
                    {"label": "Poids", "unit": "kg", "value": 5},
                    {"label": "Inconnue", "unit": "ZZZUNIT", "value": 99},
                    {"label": "Puissance", "unit": "KW", "value": 7.5},
                ]
            },
        )
        assert response.status_code == 200
        results = response.json()
        assert len(results) == 3
        assert results[0]["success"] is True
        assert results[1]["success"] is False
        assert results[2]["success"] is True

    def test_batch_empty_list_returns_empty_list(self, client):
        response = client.post("/normalize/batch", json={"items": []})
        assert response.status_code == 200
        assert response.json() == []

    def test_batch_cm_and_m_produce_same_canonical_value(self, client):
        """100 cm et 1 m normalisent tous les deux à 1.0 meter."""
        response = client.post(
            "/normalize/batch",
            json={
                "items": [
                    {"label": "Hauteur", "unit": "cm", "value": 100},
                    {"label": "Hauteur", "unit": "m", "value": 1},
                ]
            },
        )
        assert response.status_code == 200
        results = response.json()
        assert results[0]["valeur_canonique"] == pytest.approx(1.0)
        assert results[1]["valeur_canonique"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# /normalize/compare
# ---------------------------------------------------------------------------

class TestNormalizeCompare:
    def test_compare_gte_true_when_a_greater(self, client):
        """250 cm >= 2 m  =>  2.5 m >= 2.0 m  =>  match True."""
        response = client.post(
            "/normalize/compare",
            json={
                "label": "Hauteur",
                "value_a": 250, "unit_a": "cm",
                "value_b": 2,   "unit_b": "m",
                "operator": "gte",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["comparable"] is True
        assert body["match"] is True
        assert body["canonical_a"] == pytest.approx(2.5)
        assert body["canonical_b"] == pytest.approx(2.0)
        assert body["unite_canonique"] == "meter"

    def test_compare_gte_false_when_a_less(self, client):
        """150 cm >= 2 m  =>  1.5 m >= 2.0 m  =>  match False."""
        response = client.post(
            "/normalize/compare",
            json={
                "label": "Hauteur",
                "value_a": 150, "unit_a": "cm",
                "value_b": 2,   "unit_b": "m",
                "operator": "gte",
            },
        )
        body = response.json()
        assert body["comparable"] is True
        assert body["match"] is False

    def test_compare_lte_true_when_a_less(self, client):
        """2 m <= 250 cm  =>  2.0 m <= 2.5 m  =>  match True."""
        response = client.post(
            "/normalize/compare",
            json={
                "label": "Hauteur",
                "value_a": 2,   "unit_a": "m",
                "value_b": 250, "unit_b": "cm",
                "operator": "lte",
            },
        )
        body = response.json()
        assert body["comparable"] is True
        assert body["match"] is True

    def test_compare_lte_false_when_a_greater(self, client):
        """300 cm <= 2 m  =>  3.0 m <= 2.0 m  =>  match False."""
        response = client.post(
            "/normalize/compare",
            json={
                "label": "Hauteur",
                "value_a": 300, "unit_a": "cm",
                "value_b": 2,   "unit_b": "m",
                "operator": "lte",
            },
        )
        body = response.json()
        assert body["comparable"] is True
        assert body["match"] is False

    def test_compare_eq_within_default_tolerance(self, client):
        """1000 g == 1 kg avec tolérance 1% => match True (écart nul)."""
        response = client.post(
            "/normalize/compare",
            json={
                "label": "Poids",
                "value_a": 1000, "unit_a": "g",
                "value_b": 1,    "unit_b": "kg",
                "operator": "eq",
                "tolerance": 0.01,
            },
        )
        body = response.json()
        assert body["comparable"] is True
        assert body["match"] is True

    def test_compare_eq_outside_tolerance_returns_false(self, client):
        """1200 g vs 1 kg -> écart 20% > tolérance 1% => match False."""
        response = client.post(
            "/normalize/compare",
            json={
                "label": "Poids",
                "value_a": 1200, "unit_a": "g",
                "value_b": 1,    "unit_b": "kg",
                "operator": "eq",
                "tolerance": 0.01,
            },
        )
        body = response.json()
        assert body["comparable"] is True
        assert body["match"] is False

    def test_compare_incompatible_dimensions_returns_not_comparable(self, client):
        """kg vs m : dimensions incompatibles -> comparable False, match False."""
        response = client.post(
            "/normalize/compare",
            json={
                "label": "Mesure",
                "value_a": 5, "unit_a": "kg",
                "value_b": 5, "unit_b": "m",
                "operator": "eq",
            },
        )
        body = response.json()
        assert body["comparable"] is False
        assert body["match"] is False
        # La raison doit mentionner l'incompatibilité
        assert body["raison"] != ""

    def test_compare_unknown_operator_returns_not_comparable(self, client):
        """Opérateur inconnu -> comparable False avec raison explicite."""
        response = client.post(
            "/normalize/compare",
            json={
                "label": "Hauteur",
                "value_a": 1, "unit_a": "m",
                "value_b": 1, "unit_b": "m",
                "operator": "contains",
            },
        )
        body = response.json()
        assert body["comparable"] is False
        assert body["match"] is False
        assert body["raison"] != ""

    def test_compare_same_unit_eq_exact_match(self, client):
        """5 kg == 5 kg : même valeur, tolérance 0 -> match True."""
        response = client.post(
            "/normalize/compare",
            json={
                "label": "Poids",
                "value_a": 5, "unit_a": "kg",
                "value_b": 5, "unit_b": "kg",
                "operator": "eq",
                "tolerance": 0.0,
            },
        )
        body = response.json()
        assert body["comparable"] is True
        assert body["match"] is True


# ---------------------------------------------------------------------------
# /admin/reload
# ---------------------------------------------------------------------------

class TestAdminReload:
    def test_reload_without_token_configured_returns_success(self, client):
        """Sans RELOAD_AUTH_TOKEN configuré, l'endpoint est ouvert."""
        response = client.post("/admin/reload")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert isinstance(body["counts"], dict)

    def test_reload_returns_counts_from_reload_fn(self, client):
        """Les compteurs retournés viennent du reload_fn fictif du fixture."""
        response = client.post("/admin/reload")
        body = response.json()
        assert body["success"] is True
        assert "definitions" in body["counts"]

    def test_reload_wrong_token_returns_401(self, client_with_token):
        response = client_with_token.post(
            "/admin/reload",
            headers={"x-reload-token": "wrong-token"},
        )
        assert response.status_code == 401

    def test_reload_missing_token_header_returns_401(self, client_with_token):
        """Absence totale du header x-reload-token quand un token est configuré -> 401."""
        response = client_with_token.post("/admin/reload")
        assert response.status_code == 401

    def test_reload_correct_token_returns_200(self, client_with_token):
        response = client_with_token.post(
            "/admin/reload",
            headers={"x-reload-token": "secret-token"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True

    def test_reload_fn_failure_returns_success_false(self, _use_case, monkeypatch):
        """Si reload_fn lève une exception, l'endpoint renvoie success=False sans 500."""
        monkeypatch.setattr(
            rest_api_module, "settings", _make_settings(ttl=0, token="")
        )

        async def _failing_reload_fn():
            raise RuntimeError("BO indisponible")

        application = create_app(_use_case, _failing_reload_fn)
        with TestClient(application) as c:
            response = c.post("/admin/reload")

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is False
        assert "BO indisponible" in body["error_message"]


# ---------------------------------------------------------------------------
# Validation des schémas Pydantic (requêtes mal formées)
# ---------------------------------------------------------------------------

class TestSchemaValidation:
    def test_quantity_missing_required_value_returns_422(self, client):
        """Le champ 'value' est obligatoire dans QuantityRequest."""
        response = client.post(
            "/normalize/quantity",
            json={"label": "Poids", "unit": "kg"},
        )
        assert response.status_code == 422

    def test_compare_missing_value_a_returns_422(self, client):
        response = client.post(
            "/normalize/compare",
            json={"value_b": 1.0, "unit_b": "kg"},
        )
        assert response.status_code == 422

    def test_batch_missing_items_field_returns_422(self, client):
        response = client.post("/normalize/batch", json={"wrong_key": []})
        assert response.status_code == 422

    def test_range_non_numeric_min_value_returns_422(self, client):
        response = client.post(
            "/normalize/range",
            json={"label": "Hauteur", "unit": "mm", "min_value": "abc", "max_value": 100},
        )
        assert response.status_code == 422
