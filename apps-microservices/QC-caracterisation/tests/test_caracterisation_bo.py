"""
Tests unitaires — Caractérisation produit BO (tâche 2).

Vérifient le CONTRAT BO de CaracterisationProduitGenerator sans I/O réelle
(api_client HTTP et LLM mockés) :
- étape PSI 15 (ETAPE_BO),
- endpoints dédiés produits_bo / produit_bo,
- source="bo" propagée,
- aucun appel aux endpoints IA (produits / produit),
- schéma RequestProcessus.source par défaut "".

Exécution (depuis la racine du service) :
    PYTHONPATH=. pytest tests/test_caracterisation_bo.py
"""
import os
import sys
import asyncio
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.caracterisation_produit import CaracterisationProduitGenerator
from app.schemas.question_caracteristique import RequestProcessus


def _make_api_client():
    """AsyncMock d'HelloProAPIClient dont .post route selon (etape, field, action)."""
    calls = []

    async def fake_post(etape, field, action, data=None):
        calls.append((etape, field, action, data or {}))
        if (etape, field, action) == ("category", "info", "get"):
            return {"nom_rubrique": "Test Cat", "description": "desc cat"}
        if (etape, field, action) == ("caracterisation", "process", "get"):
            return {"can_start": True, "done": []}
        if (etape, field, action) == ("caracteristique", "final", "get"):
            return [{"id_caracteristique": "10", "nom": "État du matériel",
                     "type": "textuel", "valeurs": []}]
        if (etape, field, action) == ("caracterisation", "produits_bo", "get"):
            return [{"id_produit": "P1", "titre": "titre", "description": "desc"}]
        return True  # process/update, mail, etc.

    client = AsyncMock()
    client.post.side_effect = fake_post
    client.close = AsyncMock()
    client._calls = calls
    return client


def test_etape_bo_constant():
    assert CaracterisationProduitGenerator.ETAPE_BO == "15"
    # L'étape IA (step 7) reste inchangée
    assert CaracterisationProduitGenerator.ETAPE == "7"


def test_generate_all_caracterisations_bo_routing():
    async def _run():
        client = _make_api_client()
        gen = CaracterisationProduitGenerator(client)

        # Neutraliser les dépendances externes (prompt/LLM/nettoyage jeu)
        async def _noop_load(_cat):
            gen.prompt_caracterisation = {"contenu_prompt": "x"}
        gen._load_prompts = _noop_load                       # type: ignore
        gen._clean_caracteristiques_for_prompt = lambda j: j  # type: ignore

        captured = {}
        async def _fake_single(**kwargs):
            captured["field_produit"] = kwargs.get("field_produit")
            return True
        gen._process_single_product = _fake_single           # type: ignore

        with patch("app.core.caracterisation_produit.utils.get_tracking_filepath", return_value=None), \
             patch("app.core.caracterisation_produit.utils.check_stopper", return_value=False):
            result = await gen.generate_all_caracterisations_bo(
                RequestProcessus(id_categorie="123", is_reset=False)
            )

        calls = client._calls

        # 1. Produits récupérés via l'endpoint BO, source=bo
        prod = [c for c in calls if c[1] == "produits_bo" and c[2] == "get"]
        assert prod, "doit appeler caracterisation/produits_bo/get"
        assert prod[0][3].get("source") == "bo"

        # 2. process/get sur l'étape 15 + source=bo
        pget = [c for c in calls if c[:3] == ("caracterisation", "process", "get")]
        assert pget and pget[0][3].get("etape") == "15"
        assert pget[0][3].get("source") == "bo"

        # 3. La sauvegarde produit passe par le champ BO
        assert captured.get("field_produit") == "produit_bo"

        # 4. Mail de succès sur l'étape 15
        mail = [c for c in calls if c[:3] == ("caracterisation", "mail", "success")]
        assert mail and mail[0][3].get("etape") == "15"

        # 5. Aucun endpoint IA (produits / produit) touché
        assert not any(c[1] in ("produits", "produit") for c in calls), \
            "le flux BO ne doit pas toucher les endpoints IA"

        assert result.status == "completed"

    asyncio.run(_run())


def test_generate_all_caracterisations_bo_aucun_produit():
    """Sans produit BO : retour propre, pas d'appel _process_single_product."""
    async def _run():
        client = _make_api_client()

        async def fake_post(etape, field, action, data=None):
            client._calls.append((etape, field, action, data or {}))
            if (etape, field, action) == ("category", "info", "get"):
                return {"nom_rubrique": "Cat", "description": ""}
            if (etape, field, action) == ("caracterisation", "process", "get"):
                return {"can_start": True, "done": []}
            if (etape, field, action) == ("caracteristique", "final", "get"):
                return [{"id_caracteristique": "10", "nom": "x", "type": "textuel", "valeurs": []}]
            if (etape, field, action) == ("caracterisation", "produits_bo", "get"):
                return []  # aucun produit
            return True
        client.post.side_effect = fake_post

        gen = CaracterisationProduitGenerator(client)
        async def _noop_load(_c):
            gen.prompt_caracterisation = {"contenu_prompt": "x"}
        gen._load_prompts = _noop_load                        # type: ignore
        gen._clean_caracteristiques_for_prompt = lambda j: j   # type: ignore
        called = {"n": 0}
        async def _fake_single(**_k):
            called["n"] += 1
            return True
        gen._process_single_product = _fake_single            # type: ignore

        with patch("app.core.caracterisation_produit.utils.get_tracking_filepath", return_value=None), \
             patch("app.core.caracterisation_produit.utils.check_stopper", return_value=False):
            result = await gen.generate_all_caracterisations_bo(
                RequestProcessus(id_categorie="123")
            )

        assert result.total_processed == 0
        assert result.status == "completed"
        assert called["n"] == 0

    asyncio.run(_run())
