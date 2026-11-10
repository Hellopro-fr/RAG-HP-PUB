"""Tests A553 : branche SKIP de processor.py, écrire la correspondance BO-Milvus quand elle manque.

pymilvus, qdrant-client et common_utils ne sont pas installés sur les postes de dev : la surface
d'import est simulée dans sys.modules le temps de charger processor.py par son chemin (même
principe que embedding-service/tests/test_consumer_tunables.py). Aucun appel à Zilliz.
"""
import importlib.util
import logging
import sys
import types
from enum import Enum
from pathlib import Path

import pytest

PROCESSOR_PATH = Path(__file__).resolve().parents[1] / "app" / "core" / "processor.py"


def _load_processor():
    """Charge processor.py avec des modules common_utils simulés, puis rend sys.modules intact."""

    class CollectionName(str, Enum):
        PRODUIT = "produits"

    noms = [
        "common_utils",
        "common_utils.database",
        "common_utils.database.QdrantProduitCrud",
        "common_utils.database.MilvusProduitCrud",
        "common_utils.database.MilvusProduitInserer",
        "common_utils.autres",
        "common_utils.autres.CollectionName",
    ]
    fakes = {nom: types.ModuleType(nom) for nom in noms}
    fakes["common_utils.database.QdrantProduitCrud"].QdrantProduitsCrud = object
    fakes["common_utils.database.MilvusProduitCrud"].MilvusProduitsCrud = object
    fakes["common_utils.database.MilvusProduitInserer"].MilvusProduitInserer = object
    fakes["common_utils.autres.CollectionName"].CollectionName = CollectionName

    precedents = {nom: sys.modules.get(nom) for nom in noms}
    sys.modules.update(fakes)
    try:
        spec = importlib.util.spec_from_file_location("a553_processor", PROCESSOR_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        for nom, precedent in precedents.items():
            if precedent is None:
                sys.modules.pop(nom, None)
            else:
                sys.modules[nom] = precedent
    return module


processor = _load_processor()

ID_PRODUIT = "218873"
CHAMPS = {
    "nom_produit": "Pompe doseuse",
    "id_categorie": "1234",
    "prix_ht": "100.0",
    "prix_ttc": "120.0",
    "type_produit": "1",
    "text": "Pompe doseuse électromagnétique, débit 10 l/h.",
}


class FakeCollection:
    """Collection Milvus simulée : rend des lignes ou lève, et garde chaque requête."""

    def __init__(self, lignes=None, erreur=None):
        self.lignes = lignes or []
        self.erreur = erreur
        self.requetes = []

    def query(self, expr, output_fields, consistency_level):
        self.requetes.append(
            {"expr": expr, "output_fields": output_fields, "consistency_level": consistency_level}
        )
        if self.erreur:
            raise self.erreur
        return [dict(ligne) for ligne in self.lignes]


class FakeProduitsCrud:
    """Simule MilvusProduitsCrud (collection produits_3)."""

    def __init__(self, chunks, reponse_get=None):
        self.collection = FakeCollection(chunks)
        # get_produit() réel ne rend pas chunk_number
        self.reponse_get = reponse_get or {
            "status": "success",
            "data": [{k: v for k, v in c.items() if k != "chunk_number"} for c in chunks],
        }
        self.insertions = []
        self.mises_a_jour = []

    def _ensure_connected(self):
        pass

    def get_produit(self, id_produit):
        return self.reponse_get

    def insert_produits(self, produits):
        self.insertions.append(produits)
        return {"status": "success", "ids": "501,502"}

    def update_produits(self, produits, id_produit, correspondance_produit, origin):
        self.mises_a_jour.append((id_produit, correspondance_produit, origin))
        return {"status": "success", "data": {"ids": "601,602"}}


class FakeCorrespondance:
    """Simule MilvusProduitInserer (collection correspondance_produits_bo_milvus_3)."""

    def __init__(self, lignes=None, erreur=None):
        self.collection = FakeCollection(lignes, erreur)
        self.ecritures = []

    def _ensure_connected(self):
        pass

    def insert_correpondance_produit(self, datas):
        self.ecritures.append([dict(d) for d in datas])
        return {"status": "success", "ids": "1"}


def chunk(id_, numero, source="SITEWEB"):
    return {"id": id_, "chunk_number": numero, "source": source, **CHAMPS}


def message(mode=""):
    return {
        "data": [{"id_produit": ID_PRODUIT, **CHAMPS}],
        "collection": "produits",
        "database": "milvus",
        "origin": "siteweb",
        "mode": mode,
    }


@pytest.fixture
def brancher(monkeypatch):
    def _brancher(chunks, correspondances=None, erreur=None, reponse_get=None):
        crud = FakeProduitsCrud(chunks, reponse_get)
        correspondance = FakeCorrespondance(correspondances, erreur)
        monkeypatch.setattr(processor, "_milvus_produit_crud", crud)
        monkeypatch.setattr(processor, "_correspondance_produit", correspondance)
        return crud, correspondance

    return _brancher


def test_skip_sans_correspondance_ecrit_une_fois_les_cles_triees(brancher, caplog):
    # Clés volontairement dans un ordre différent de chunk_number, plus un chunk d'une autre source
    chunks = [chunk(202, 2), chunk(303, 0), chunk(101, 1), chunk(999, 0, source="BO")]
    crud, correspondance = brancher(chunks)
    caplog.set_level(logging.INFO)

    sortie = processor.insertion_data(message())

    assert sortie["already_in_bdd"] is True and sortie["updated"] is False
    assert len(correspondance.ecritures) == 1 and len(correspondance.ecritures[0]) == 1
    entree = correspondance.ecritures[0][0]
    # Réserve 4 : clés jointes par des virgules, comme à l'insertion (",".join), triées par chunk_number
    assert entree["id_produit_milvus"] == "303,101,202"
    assert entree["id_produit"] == ID_PRODUIT
    assert entree["origin"] == "siteweb"
    assert entree["embedding"] == [0.0] * 1024
    # Aucun chunk réinséré ni mis à jour
    assert crud.insertions == [] and crud.mises_a_jour == []
    # Les deux lectures se font en consistance forte
    requetes = correspondance.collection.requetes + crud.collection.requetes
    assert [r["consistency_level"] for r in requetes] == ["Strong", "Strong"]
    assert "chunk_number" in crud.collection.requetes[0]["output_fields"]
    # Réserve 3 : log de réparation (id_produit, nombre de clés)
    assert "SKIP id_produit=218873" in caplog.text and "3 clé(s)" in caplog.text


def test_skip_correspondance_presente_rien_ecrit(brancher):
    # Origine stockée en majuscules, message en minuscules : la casse ne compte pas
    crud, correspondance = brancher([chunk(101, 0)], correspondances=[{"id": 7, "origin": "SITEWEB"}])

    processor.insertion_data(message())

    assert correspondance.ecritures == []
    assert len(correspondance.collection.requetes) == 1
    assert crud.collection.requetes == []  # chunks non relus quand le lien existe


def test_skip_correspondance_d_une_autre_origine_seulement_repare(brancher):
    crud, correspondance = brancher([chunk(101, 0)], correspondances=[{"id": 7, "origin": "bo"}])

    processor.insertion_data(message())

    assert [[e["id_produit_milvus"] for e in lot] for lot in correspondance.ecritures] == [["101"]]


def test_skip_erreur_zilliz_leve_sans_ecrire(brancher):
    crud, correspondance = brancher([chunk(101, 0)], erreur=RuntimeError("Zilliz indisponible"))

    with pytest.raises(RuntimeError, match="Zilliz indisponible"):
        processor.insertion_data(message())

    assert correspondance.ecritures == []
    assert correspondance.collection is None  # reconnexion forcée au nouvel essai


def test_skip_chunk_number_en_double_ecrit_toutes_les_cles(brancher, caplog):
    crud, correspondance = brancher([chunk(102, 1), chunk(101, 0), chunk(103, 1)])
    caplog.set_level(logging.INFO)

    processor.insertion_data(message())

    assert correspondance.ecritures[0][0]["id_produit_milvus"] == "101,102,103"
    assert "chunk_number en double" in caplog.text


@pytest.mark.parametrize(
    "reponse_get",
    [
        {"status": "success", "data": []},  # get_produit réel : produit absent
        {"status": "error", "code": 404, "message": "absent"},  # CAS 1
    ],
)
def test_insertion_inchangee(brancher, reponse_get):
    crud, correspondance = brancher([], reponse_get=reponse_get)

    sortie = processor.insertion_data(message())

    assert len(crud.insertions) == 1
    assert [[e["id_produit_milvus"] for e in lot] for lot in correspondance.ecritures] == [["501,502"]]
    assert correspondance.collection.requetes == [] and crud.collection.requetes == []
    assert sortie["already_in_bdd"] is False


def test_update_inchange_aucune_ecriture_par_processor(brancher):
    crud, correspondance = brancher([chunk(101, 0)])

    sortie = processor.insertion_data(message(mode="update"))

    assert len(crud.mises_a_jour) == 1
    assert crud.mises_a_jour[0][1] is correspondance  # update_produits() gère sa correspondance
    assert correspondance.ecritures == []
    assert correspondance.collection.requetes == [] and crud.collection.requetes == []
    assert sortie["updated"] is True
