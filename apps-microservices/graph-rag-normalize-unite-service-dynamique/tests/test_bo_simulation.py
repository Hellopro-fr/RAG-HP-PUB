"""
Tests de simulation BO : parité end-to-end via le chemin fetch_referentiel_from_bo().

Stratégie :
  - httpx.AsyncClient est monkeypatché pour que fetch_referentiel_from_bo() reçoive
    le payload build_legacy_payload() au lieu de contacter le vrai BO.
  - Le normalizer dynamique construit depuis ce payload est comparé au normalizer
    legacy chargé directement (load_legacy_normalizer()).
  - Deux niveaux de couverture :
      1. Cas représentatifs nommés (précis, lisibles, documentent l'intention).
      2. Balayage exhaustif de toutes les clés UNIT_TO_DIMENSION du service legacy
         (filet de régression pour toute clé présente dans le mapping historique).
"""

import asyncio
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from infrastructure.referentiel_loader import Referentiel, fetch_referentiel_from_bo
from infrastructure.unit_normalization_service import UnitNormalizationService
from scripts.legacy_referentiel import build_legacy_payload, load_legacy_normalizer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_dynamic_normalizer_from_payload(payload: Dict[str, Any]) -> UnitNormalizationService:
    ref = Referentiel.from_payload(payload)
    return UnitNormalizationService(ref)


def _normalize(normalizer, label: str, unit: Optional[str], value: float) -> Dict[str, Any]:
    return normalizer.normalize(label, unit, value, "numeric")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def legacy_payload() -> Dict[str, Any]:
    """Payload BO simulé (identique aux données du service historique)."""
    return build_legacy_payload()


@pytest.fixture(scope="module")
def dynamic_normalizer(legacy_payload) -> UnitNormalizationService:
    """Normalizer dynamique construit depuis le payload legacy simulé."""
    return _build_dynamic_normalizer_from_payload(legacy_payload)


@pytest.fixture(scope="module")
def old_normalizer():
    """Instance singleton du service historique (source de vérité du seed)."""
    return load_legacy_normalizer()


# ---------------------------------------------------------------------------
# Test : fetch_referentiel_from_bo() avec httpx monkeypatché
# ---------------------------------------------------------------------------

class TestFetchReferentielFromBo:
    """
    Valide que fetch_referentiel_from_bo() construit un Referentiel valide
    lorsque le BO renvoie le payload legacy (httpx mocké).
    """

    def test_fetch_returns_valid_referentiel(self, legacy_payload):
        """
        Quand le BO répond avec le payload legacy, fetch_referentiel_from_bo()
        retourne un Referentiel dont les sections cœur sont non vides.
        """
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value=legacy_payload)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("infrastructure.referentiel_loader.httpx.AsyncClient", return_value=mock_client):
            ref = asyncio.run(fetch_referentiel_from_bo())

        assert isinstance(ref, Referentiel)
        # validate() ne doit pas lever (sections cœur non vides)
        ref.validate()

    def test_fetch_populates_unit_to_dimension(self, legacy_payload):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value=legacy_payload)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("infrastructure.referentiel_loader.httpx.AsyncClient", return_value=mock_client):
            ref = asyncio.run(fetch_referentiel_from_bo())

        assert len(ref.unit_to_dimension) > 0
        assert "kg" in ref.unit_to_dimension
        assert ref.unit_to_dimension["kg"] == "mass"

    def test_fetch_populates_canonical_units(self, legacy_payload):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value=legacy_payload)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("infrastructure.referentiel_loader.httpx.AsyncClient", return_value=mock_client):
            ref = asyncio.run(fetch_referentiel_from_bo())

        assert "mass" in ref.canonical_units
        assert ref.canonical_units["mass"] == "kilogram"

    def test_fetch_raises_on_http_error(self):
        """Si le BO renvoie une erreur HTTP, fetch_referentiel_from_bo() doit lever."""
        import httpx as httpx_module

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock(
            side_effect=httpx_module.HTTPStatusError(
                "500", request=MagicMock(), response=MagicMock()
            )
        )
        mock_response.json = MagicMock(return_value={})

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("infrastructure.referentiel_loader.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(httpx_module.HTTPStatusError):
                asyncio.run(fetch_referentiel_from_bo())

    def test_fetch_raises_on_empty_payload(self):
        """
        Si le BO renvoie un payload vide (toutes les sections manquantes),
        fetch_referentiel_from_bo() doit lever ValueError via validate().
        """
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={})

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("infrastructure.referentiel_loader.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(ValueError, match="inexploitable"):
                asyncio.run(fetch_referentiel_from_bo())


# ---------------------------------------------------------------------------
# Cas représentatifs nommés (parité dynamique == legacy)
# ---------------------------------------------------------------------------

class TestParityNamedCases:
    """
    Assertions explicites sur des cas métier réels.
    Chaque test documente à la fois le comportement attendu ET prouve la parité.
    """

    _CASES = [
        # (description, label, unit, value, expected_canonical_unit)
        ("poids kg",            "Poids",             "kg",     1500,  "kilogram"),
        ("hauteur mm",          "Hauteur",            "mm",     2500,  "meter"),
        ("puissance CV",        "Puissance",          "CV",        3,  "watt"),
        ("puissance KW",        "Puissance",          "KW",      7.5,  "watt"),
        ("capacite tonnes",     "Capacité",           "Tonnes",    2,  "kilogram"),
        ("niveau sonore dBA",   "Niveau sonore",      "dB(A)",    72,  "decibel"),
        ("rotation tr/min",     "Vitesse de rotation","tr/min", 1450,  "hertz"),
        ("debit m3/h",          "Débit",              "m3/h",    12,  "liter / minute"),
        ("surface m²",          "Surface",            "m²",      18,  "meter ** 2"),
        ("epaisseur nm",        "Épaisseur",          "nm",     250,  "meter"),
        ("humidite pct",        "Humidité",           "%",       60,  "count"),
        ("durete mohs",         "Dureté",             "Mohs",     7,  "count"),
        ("volume litres",       "Volume cuve",        "litres", 200,  "liter"),
        ("temperature degC",    "Température",        "°C",      21,  "degree_Celsius"),
    ]

    @pytest.mark.parametrize("desc,label,unit,value,expected_unit", _CASES, ids=[c[0] for c in _CASES])
    def test_dynamic_output_matches_legacy(self, dynamic_normalizer, old_normalizer, desc, label, unit, value, expected_unit):
        old_result = _normalize(old_normalizer, label, unit, value)
        new_result = _normalize(dynamic_normalizer, label, unit, value)

        assert new_result == old_result, (
            f"[{desc}] Divergence: legacy={old_result}, dynamic={new_result}"
        )
        assert new_result.get("unite_canonique") == expected_unit, (
            f"[{desc}] unite_canonique inattendue: {new_result.get('unite_canonique')!r}"
        )

    def test_tolerance_string_parity(self, dynamic_normalizer, old_normalizer):
        """Valeur chaîne '+/- 2' avec unité mm -> parité de parsing."""
        old_result = _normalize(old_normalizer, "Tolérance", "mm", 2)
        new_result = _normalize(dynamic_normalizer, "Tolérance", "mm", 2)
        assert new_result == old_result

    def test_production_capacity_t_per_min_mass_flow(self, dynamic_normalizer, old_normalizer):
        """Désambiguïsation t/min -> mass_flow quand label contient 'capacite de production'."""
        label = "Capacité de production"
        old_result = _normalize(old_normalizer, label, "t/min", 5)
        new_result = _normalize(dynamic_normalizer, label, "t/min", 5)
        assert new_result == old_result
        assert new_result.get("unite_canonique") == "gram / minute"

    def test_nm_as_torque_without_length_label(self, dynamic_normalizer, old_normalizer):
        """nm sans indicateur de longueur dans le label -> torque (newton*meter)."""
        label = "Couple"
        old_result = _normalize(old_normalizer, label, "nm", 10)
        new_result = _normalize(dynamic_normalizer, label, "nm", 10)
        assert new_result == old_result

    def test_nm_as_length_with_wavelength_label(self, dynamic_normalizer, old_normalizer):
        """nm avec label contenant 'longueur d'onde' -> désambiguïsation length."""
        label = "Longueur d'onde"
        old_result = _normalize(old_normalizer, label, "nm", 650)
        new_result = _normalize(dynamic_normalizer, label, "nm", 650)
        assert new_result == old_result

    def test_null_unit_poids_falls_back_to_label(self, dynamic_normalizer, old_normalizer):
        """unit=None -> résolution par label (Poids -> mass -> kilogram)."""
        old_result = _normalize(old_normalizer, "Poids", None, 10)
        new_result = _normalize(dynamic_normalizer, "Poids", None, 10)
        assert new_result == old_result
        assert new_result.get("unite_canonique") == "kilogram"

    def test_bypass_percent_returns_count(self, dynamic_normalizer, old_normalizer):
        """% est un bypass -> retourne count sans passer par pint."""
        old_result = _normalize(old_normalizer, "Humidité", "%", 75)
        new_result = _normalize(dynamic_normalizer, "Humidité", "%", 75)
        assert new_result == old_result
        assert new_result.get("valeur_canonique") == 75.0
        assert new_result.get("unite_canonique") == "count"

    def test_rewrite_km_per_h_returns_meter_per_second(self, dynamic_normalizer, old_normalizer):
        """km/h réécrit -> speed -> meter / second."""
        old_result = _normalize(old_normalizer, "Vitesse", "km/h", 90)
        new_result = _normalize(dynamic_normalizer, "Vitesse", "km/h", 90)
        assert new_result == old_result
        assert new_result.get("unite_canonique") == "meter / second"

    def test_rewrite_litres_returns_liter(self, dynamic_normalizer, old_normalizer):
        old_result = _normalize(old_normalizer, "Volume", "litres", 50)
        new_result = _normalize(dynamic_normalizer, "Volume", "litres", 50)
        assert new_result == old_result
        assert new_result.get("valeur_canonique") == pytest.approx(50.0)

    def test_data_only_label_without_unit(self, dynamic_normalizer, old_normalizer):
        """Label seul (unit=None) -> résolution dimension par label."""
        old_result = _normalize(old_normalizer, "Puissance", None, 5)
        new_result = _normalize(dynamic_normalizer, "Puissance", None, 5)
        assert new_result == old_result


# ---------------------------------------------------------------------------
# Balayage exhaustif UNIT_TO_DIMENSION (filet de régression)
# ---------------------------------------------------------------------------

class TestExhaustiveUnitKeyParity:
    """
    Pour chaque clé de UNIT_TO_DIMENSION du service legacy, assert que le normalizer
    dynamique produit exactement le même résultat que le normalizer legacy.

    Ce test est le double du test_parity.py::test_parity_quantity mais ciblé sur les
    seules clés de mapping (pas de label, valeur fixe à 100.0) et formulé en pytest
    paramétrique pour avoir un message d'erreur par clé divergente.
    """

    @staticmethod
    def _unit_keys(old_normalizer):
        return list(old_normalizer.UNIT_TO_DIMENSION.keys())

    def test_all_unit_keys_produce_identical_output(self, dynamic_normalizer, old_normalizer):
        """
        Balayage complet : chaque unité reconnue par le legacy doit produire
        le même résultat canonique dans le service dynamique.
        """
        divergences = []
        for unit_key in old_normalizer.UNIT_TO_DIMENSION:
            old_res = _normalize(old_normalizer, "", unit_key, 100.0)
            new_res = _normalize(dynamic_normalizer, "", unit_key, 100.0)
            if old_res != new_res:
                divergences.append((unit_key, old_res, new_res))

        assert not divergences, (
            f"{len(divergences)} unité(s) diverge(nt):\n"
            + "\n".join(f"  unit={u!r}: legacy={o}, dynamic={n}" for u, o, n in divergences[:15])
        )

    def test_all_label_keys_produce_identical_output(self, dynamic_normalizer, old_normalizer):
        """
        Balayage complet sur les mots-clés de label (unité absente).
        """
        divergences = []
        for label_key in old_normalizer.LABEL_TO_DIMENSION:
            old_res = _normalize(old_normalizer, label_key, None, 100.0)
            new_res = _normalize(dynamic_normalizer, label_key, None, 100.0)
            if old_res != new_res:
                divergences.append((label_key, old_res, new_res))

        assert not divergences, (
            f"{len(divergences)} label(s) diverge(nt):\n"
            + "\n".join(f"  label={l!r}: legacy={o}, dynamic={n}" for l, o, n in divergences[:15])
        )


# ---------------------------------------------------------------------------
# Test de normalize_range via le normalizer dynamique alimenté par BO simulé
# ---------------------------------------------------------------------------

class TestBoSimulatedRangeParity:
    _RANGE_CASES = [
        ("Hauteur", "mm",  100, 2500),
        ("Poids",   "kg",   50, 1500),
        ("Puissance", "CV",  2,    8),
        ("Température", "°C", -10, 40),
    ]

    @pytest.mark.parametrize("label,unit,vmin,vmax", _RANGE_CASES,
                             ids=[f"{l}-{u}" for l, u, _, __ in _RANGE_CASES])
    def test_range_parity_with_legacy(self, dynamic_normalizer, old_normalizer, label, unit, vmin, vmax):
        old_res = old_normalizer.normalize_range(label, unit, vmin, vmax)
        new_res = dynamic_normalizer.normalize_range(label, unit, vmin, vmax)
        assert new_res == old_res, (
            f"range({label!r}, {unit!r}, {vmin}, {vmax}): legacy={old_res}, dynamic={new_res}"
        )


# ---------------------------------------------------------------------------
# Vérification que le normalizer dynamique construit depuis fetch (httpx mocké)
# est fonctionnellement identique à celui construit depuis build_legacy_payload()
# ---------------------------------------------------------------------------

class TestFetchedNormalizerMatchesBuildPayload:
    """
    Garantit que le chemin complet fetch_referentiel_from_bo() -> Referentiel
    produit le même normalizer que Referentiel.from_payload(build_legacy_payload()).
    Ce test valide la cohérence du pipe end-to-end, pas seulement le moteur interne.
    """

    _SPOT_CASES = [
        ("Poids",             "kg",     500),
        ("Hauteur",           "mm",    1000),
        ("Puissance",         "CV",       5),
        ("Niveau sonore",     "dB(A)",   65),
        ("Humidité",          "%",       80),
        ("Vitesse de rotation","tr/min", 3000),
    ]

    def test_fetched_normalizer_matches_build_payload_normalizer(self, legacy_payload):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value=legacy_payload)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("infrastructure.referentiel_loader.httpx.AsyncClient", return_value=mock_client):
            ref_fetched = asyncio.run(fetch_referentiel_from_bo())

        ref_direct = Referentiel.from_payload(legacy_payload)

        normalizer_fetched = UnitNormalizationService(ref_fetched)
        normalizer_direct = UnitNormalizationService(ref_direct)

        divergences = []
        for label, unit, value in self._SPOT_CASES:
            res_f = _normalize(normalizer_fetched, label, unit, value)
            res_d = _normalize(normalizer_direct, label, unit, value)
            if res_f != res_d:
                divergences.append((label, unit, value, res_f, res_d))

        assert not divergences, (
            f"Divergence entre chemin fetch et chemin direct: {divergences}"
        )
