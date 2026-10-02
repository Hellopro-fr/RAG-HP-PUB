import httpx
from fastapi.testclient import TestClient

from app.core.api_v2 import ErreurApiV2
from app.core.dependances import get_dependances
from app.core.execution import Dependances
from main import app
from tests.fakes import FauxApiV2, ModeleScripte, reponse


def client_avec(api, *reponses):
    modele = ModeleScripte(*reponses)
    app.dependency_overrides[get_dependances] = lambda: Dependances(api_v2=api, fabrique_modele=lambda d, c: modele)
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_200_reponse_ok():
    r = client_avec(FauxApiV2(), reponse("12345678900012")).post(
        "/agents/get-siren/run", json={"input": "exemple.fr", "origine": "identification_prospects"})
    assert r.status_code == 200
    assert r.json()["output"] == "12345678900012" and r.json()["statut"] == "ok"


def test_422_format_invalide_garde_la_sortie():
    r = client_avec(FauxApiV2(), reponse("Le SIRET est 1")).post(
        "/agents/get-siren/run", json={"input": "exemple.fr"})
    assert r.status_code == 422
    assert r.json()["statut"] == "format_invalide" and r.json()["output"] == "Le SIRET est 1"


def test_502_erreur_fournisseur():
    r = client_avec(FauxApiV2(), RuntimeError("429 rate limit")).post(
        "/agents/get-siren/run", json={"input": "exemple.fr"})
    assert r.status_code == 502 and r.json()["statut"] == "erreur"


def test_504_delai_depasse():
    r = client_avec(FauxApiV2(), httpx.ReadTimeout("trop long")).post(
        "/agents/get-siren/run", json={"input": "exemple.fr"})
    assert r.status_code == 504 and r.json()["statut"] == "timeout"


def test_404_agent_introuvable():
    api = FauxApiV2(fiche={"trouve": False, "raison": "agent_inconnu"})
    r = client_avec(api).post("/agents/inconnu/run", json={"input": "exemple.fr"})
    assert r.status_code == 404 and r.json()["detail"] == "agent_inconnu"


def test_422_entree_vide_sans_lecture_de_fiche():
    api = FauxApiV2()
    r = client_avec(api).post("/agents/get-siren/run", json={"input": "   "})
    assert r.status_code == 422 and api.lectures == []


def test_503_api_v2_injoignable():
    api = FauxApiV2(erreur_lecture=ErreurApiV2("API v2 injoignable"))
    r = client_avec(api).post("/agents/get-siren/run", json={"input": "exemple.fr"})
    assert r.status_code == 503 and r.json()["detail"] == "api_v2_indisponible"


def test_get_fiche_publiee_et_404():
    assert client_avec(FauxApiV2()).get("/agents/get-siren").json()["code"] == "get-siren"
    api = FauxApiV2(fiche={"trouve": False, "raison": "agent_inconnu"})
    assert client_avec(api).get("/agents/inconnu").status_code == 404
