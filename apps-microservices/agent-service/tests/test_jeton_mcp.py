import httpx
import pytest

from app.core.jeton_mcp import ErreurJetonMcp, JetonMcp


class Horloge:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def client_jeton(appels, statut=200):
    def repondre(requete):
        appels.append(requete)
        return httpx.Response(statut, json={"access_token": f"jwt-{len(appels)}", "expires_in": 3600})
    return httpx.Client(transport=httpx.MockTransport(repondre))


def test_premier_appel_client_credentials():
    appels = []
    jeton = JetonMcp("https://mcp.test/", "agents-ia", "secret", client_jeton(appels), Horloge())
    assert jeton.obtenir() == "jwt-1"
    assert str(appels[0].url) == "https://mcp.test/token"
    assert b"grant_type=client_credentials" in appels[0].content
    assert b"client_id=agents-ia" in appels[0].content


def test_jeton_garde_en_cache_puis_renouvele_60s_avant_expiration():
    appels, horloge = [], Horloge()
    jeton = JetonMcp("https://mcp.test", "agents-ia", "secret", client_jeton(appels), horloge)
    jeton.obtenir()
    horloge.t += 3500
    assert jeton.obtenir() == "jwt-1" and len(appels) == 1
    horloge.t += 50
    assert jeton.obtenir() == "jwt-2" and len(appels) == 2


def test_refus_de_la_gateway_leve_erreur():
    jeton = JetonMcp("https://mcp.test", "agents-ia", "faux", client_jeton([], statut=401), Horloge())
    with pytest.raises(ErreurJetonMcp):
        jeton.obtenir()
