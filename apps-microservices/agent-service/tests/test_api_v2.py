import json

import httpx
import pytest

from app.core.api_v2 import ClientApiV2, ErreurApiV2

URL = "https://api.test/v2/index.php"  # httpx exige une URL absolue, même avec MockTransport
FICHE = {"trouve": True, "id_agent": 1, "code": "get-siren", "type": 1, "id_version": 7, "numero": 3,
         "statut": 2, "definition": {}, "capacites": {"recherche_web": 1, "mcp": 0}}


class Horloge:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def client(appels, corps=None, erreur=None):
    def repondre(requete):
        appels.append(requete)
        if erreur:
            raise erreur
        return httpx.Response(200, json=corps if corps is not None else {"code": 200, "response": FICHE})
    return httpx.Client(transport=httpx.MockTransport(repondre))


def test_lire_fiche_envoie_etape_agents_avec_jeton():
    appels = []
    api = ClientApiV2(URL, "hp-token", client_http=client(appels))
    assert api.lire_fiche("get-siren") == FICHE
    assert appels[0].headers["Authorization"] == "Bearer hp-token"
    assert json.loads(appels[0].content) == {"etape": "agents", "field": "config", "action": "get",
                                             "data": {"code": "get-siren", "version": "publiee"}}


def test_version_publiee_en_cache_jusqu_au_ttl():
    appels, horloge = [], Horloge()
    api = ClientApiV2(URL, "t", ttl_cache_s=60, client_http=client(appels), horloge=horloge)
    api.lire_fiche("get-siren")
    horloge.t = 59
    api.lire_fiche("get-siren")
    assert len(appels) == 1
    horloge.t = 61
    api.lire_fiche("get-siren")
    assert len(appels) == 2


def test_brouillon_jamais_en_cache():
    appels = []
    api = ClientApiV2(URL, "t", client_http=client(appels))
    api.lire_fiche("get-siren", "brouillon")
    api.lire_fiche("get-siren", "brouillon")
    assert len(appels) == 2


def test_agent_introuvable_non_mis_en_cache():
    appels = []
    corps = {"code": 200, "response": {"trouve": False, "raison": "aucune_version_publiee"}}
    api = ClientApiV2(URL, "t", client_http=client(appels, corps))
    assert api.lire_fiche("get-siren")["raison"] == "aucune_version_publiee"
    api.lire_fiche("get-siren")
    assert len(appels) == 2


def test_code_400_leve_erreur():
    api = ClientApiV2(URL, "t", client_http=client([], {"code": 400, "error": "Invalid action"}))
    with pytest.raises(ErreurApiV2):
        api.lire_fiche("get-siren")


def test_api_injoignable_leve_erreur_a_la_lecture():
    api = ClientApiV2(URL, "t", client_http=client([], erreur=httpx.ConnectError("refus")))
    with pytest.raises(ErreurApiV2):
        api.lire_fiche("get-siren")


def test_enregistrer_execution_renvoie_id_et_cout():
    corps = {"code": 200, "response": {"enregistre": True, "id_execution": 42, "cout": 0.04465}}
    api = ClientApiV2(URL, "t", client_http=client([], corps))
    assert api.enregistrer_execution({"id_agent": 1}) == {"id_execution": 42, "cout": 0.04465}


def test_journal_injoignable_ne_leve_pas():
    api = ClientApiV2(URL, "t", client_http=client([], erreur=httpx.ConnectError("refus")))
    assert api.enregistrer_execution({"id_agent": 1}) == {"id_execution": None, "cout": None}


def test_journal_refuse_ne_leve_pas():
    corps = {"code": 200, "response": {"enregistre": False, "erreur": "champ manquant : id_agent"}}
    api = ClientApiV2(URL, "t", client_http=client([], corps))
    assert api.enregistrer_execution({}) == {"id_execution": None, "cout": None}
