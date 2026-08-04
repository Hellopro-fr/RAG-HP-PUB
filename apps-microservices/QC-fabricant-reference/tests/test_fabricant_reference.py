"""
Tests unitaires — extraction fabricant / reference (etape PSI 16, prompt 133).

Verifient le contrat du generateur sans I/O reelle (API HelloPro et LLM mockes) :
- l'independance des sources : le prompt ne recoit JAMAIS de donnee fournisseur,
- l'alignement du batch sur id_produit (jamais sur l'ordre),
- les garde-fous deterministes post-LLM (abstention plutot que valeur fausse),
- le routage des endpoints fabricant_reference et l'etape 16,
- la tolerance aux echecs de batch (un batch perdu n'arrete pas un run de 746k produits).

Execution (depuis la racine du service) :
    PYTHONPATH=. pytest tests/
"""
import os
import sys
import asyncio
from unittest.mock import AsyncMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.fabricant_reference import (
    BATCH_PRODUITS,
    FabricantReferenceGenerator,
)
from app.schemas.fabricant_reference import RequestFabricantReference


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

PROMPT = {
    "contenu_prompt": "Extrais marque et reference.\nINPUT:\n{PRODUITS}",
    "temperature": 0,
}


def _make_api_client(produits=None, sorties_llm=None):
    """Mock d'HelloProAPIClient routant selon (etape, field, action)."""
    calls = []
    produits = produits if produits is not None else [
        {"id_produit": "1", "titre": "Pont elevateur NOVARA T450", "categorie": "Pont elevateur",
         "description": "", "id_fournisseur": "900", "nom_fournisseur": "NOVARA France"},
    ]

    async def fake_post(etape, field, action, data=None):
        calls.append((etape, field, action, data or {}))
        if (etape, field, action) == ("category", "info", "get"):
            return {"nom_rubrique": "Pont elevateur", "description": "desc cat"}
        if (etape, field, action) == ("prompt", "info", "get"):
            return dict(PROMPT)
        if (etape, field, action) == ("fabricant_reference", "process", "get"):
            return {"can_start": True}
        if (etape, field, action) == ("fabricant_reference", "produits", "get"):
            return produits
        return True

    client = AsyncMock()
    client.post.side_effect = fake_post
    client.close = AsyncMock()
    client.log_llm_usage = AsyncMock(return_value=True)
    client._calls = calls
    return client


def _make_generator(client=None, sorties_llm=None, erreur_llm=False):
    """Generateur avec _call_llm mocke : renvoie sorties_llm, ou leve si erreur_llm.

    Le prompt n'est PAS preinjecte : _load_prompt passe par le mock d'API, donc le
    run exerce le vrai chargement du prompt 133.
    """
    gen = FabricantReferenceGenerator(client or _make_api_client())

    async def fake_call(prompt_text, id_categorie, nb_produits):
        gen._prompts_envoyes.append(prompt_text)
        if erreur_llm:
            raise Exception("Erreur API DeepSeek: 500")
        return sorties_llm if sorties_llm is not None else []

    gen._prompts_envoyes = []
    gen._call_llm = fake_call
    return gen


# ─────────────────────────────────────────────────────────────────────────────
# Constantes de contrat
# ─────────────────────────────────────────────────────────────────────────────

def test_constantes_de_contrat():
    assert FabricantReferenceGenerator.ETAPE == "16"
    assert FabricantReferenceGenerator.PROMPT_EXTRACTION_ID == "133"
    assert BATCH_PRODUITS == 10


# ─────────────────────────────────────────────────────────────────────────────
# Independance des sources : aucune donnee fournisseur dans le prompt
# ─────────────────────────────────────────────────────────────────────────────

class TestIndependanceFournisseur:
    """Le statut fabricant/revendeur n'est demontrable que si le modele ignore
    le fournisseur. Un nom de fournisseur qui fuite dans le prompt serait
    recopie en marque et fabriquerait une fausse concordance."""

    def test_payload_ne_contient_que_les_champs_produit(self):
        gen = _make_generator()
        produit = {
            "id_produit": "1", "titre": "Pont NOVARA T450", "description": "desc",
            "categorie": "Pont elevateur",
            "id_fournisseur": "900", "nom_fournisseur": "NOVARA France",
            "site_web": "novara.fr", "email": "contact@novara.fr",
        }

        payload = gen._build_batch_payload([produit])

        assert set(payload[0].keys()) == {"id_produit", "categorie", "titre", "description"}

    def test_description_absente_non_transmise(self):
        gen = _make_generator()
        payload = gen._build_batch_payload(
            [{"id_produit": "1", "titre": "Pont NOVARA", "categorie": "Pont", "description": ""}]
        )
        assert "description" not in payload[0]

    def test_garde_fou_leve_si_donnee_fournisseur_presente(self):
        gen = _make_generator()
        payload_corrompu = [{"id_produit": "1", "titre": "Pont", "nom_fournisseur": "NOVARA France"}]

        try:
            gen._assert_no_supplier_data(payload_corrompu)
        except ValueError as exc:
            assert "fournisseur" in str(exc).lower()
        else:
            raise AssertionError("Le garde-fou doit lever sur une donnee fournisseur")

    def test_prompt_envoye_sans_nom_fournisseur(self):
        client = _make_api_client()
        gen = _make_generator(client, sorties_llm=[{"id_produit": "1", "marque": "NOVARA"}])

        asyncio.run(gen.run(RequestFabricantReference(id_categorie="42", source="bo")))

        assert gen._prompts_envoyes, "aucun prompt envoye"
        for prompt in gen._prompts_envoyes:
            assert "NOVARA France" not in prompt
            assert "nom_fournisseur" not in prompt


# ─────────────────────────────────────────────────────────────────────────────
# Alignement du batch
# ─────────────────────────────────────────────────────────────────────────────

class TestReconcileBatch:
    produits = [
        {"id_produit": "1", "titre": "Pont NOVARA T450", "categorie": "Pont elevateur"},
        {"id_produit": "2", "titre": "Pont ORTIS ZR12", "categorie": "Pont elevateur"},
    ]

    def test_ordre_inverse_reindexe_par_id(self):
        gen = _make_generator()
        sorties = [
            {"id_produit": "2", "marque": "ORTIS", "reference": "ZR12"},
            {"id_produit": "1", "marque": "NOVARA", "reference": "T450"},
        ]

        resultat = gen._reconcile_batch(self.produits, sorties)

        assert [r.id_produit for r in resultat] == ["1", "2"]
        assert [r.marque for r in resultat] == ["NOVARA", "ORTIS"]

    def test_id_manquant_devient_abstention_alertee(self):
        gen = _make_generator()
        sorties = [{"id_produit": "1", "marque": "NOVARA", "reference": "T450"}]

        resultat = gen._reconcile_batch(self.produits, sorties)

        assert len(resultat) == 2
        manquant = resultat[1]
        assert manquant.id_produit == "2"
        assert manquant.marque is None
        assert "absent_reponse_llm" in manquant.alertes

    def test_id_inconnu_ignore(self):
        """Un id_produit hallucine ne doit jamais creer de ligne."""
        gen = _make_generator()
        sorties = [
            {"id_produit": "1", "marque": "NOVARA"},
            {"id_produit": "999", "marque": "FANTOME"},
            {"id_produit": "2", "marque": "ORTIS"},
        ]

        resultat = gen._reconcile_batch(self.produits, sorties)

        assert [r.id_produit for r in resultat] == ["1", "2"]

    def test_sortie_non_liste_traitee_comme_vide(self):
        gen = _make_generator()
        resultat = gen._reconcile_batch(self.produits, {"marque": "NOVARA"})
        assert all(r.marque is None for r in resultat)
        assert all("absent_reponse_llm" in r.alertes for r in resultat)


# ─────────────────────────────────────────────────────────────────────────────
# Normalisation de la forme de reponse
#
# Regression vecue : le modele a enveloppe le tableau dans un objet, _reconcile_batch
# n'a rien reconnu et TOUT le batch a ete enregistre en `absent_reponse_llm` — sans
# marque, alors que la reponse etait bonne (et facturee).
# ─────────────────────────────────────────────────────────────────────────────

class TestNormaliserSorties:
    produits = [
        {"id_produit": "1", "titre": "Pont NOVARA T450", "categorie": "Pont elevateur"},
        {"id_produit": "2", "titre": "Pont ORTIS ZR12", "categorie": "Pont elevateur"},
    ]

    def test_tableau_racine_inchange(self):
        gen = _make_generator()
        sorties = [{"id_produit": "1", "marque": "NOVARA"}]
        assert gen._normaliser_sorties(sorties) == sorties

    def test_liste_enveloppee_dans_un_objet(self):
        """{"produits": [...]} : la liste est retrouvee quelle que soit la cle."""
        gen = _make_generator()
        attendu = [
            {"id_produit": "1", "marque": "NOVARA"},
            {"id_produit": "2", "marque": "ORTIS"},
        ]

        for cle in ("produits", "resultats", "data", "extractions", "n_importe_quoi"):
            assert gen._normaliser_sorties({cle: attendu}) == attendu

    def test_liste_enveloppee_alignee_de_bout_en_bout(self):
        """Le vrai scenario : reponse enveloppee -> marques bien extraites."""
        gen = _make_generator()
        brut = {"produits": [
            {"id_produit": "2", "marque": "ORTIS", "reference": "ZR12"},
            {"id_produit": "1", "marque": "NOVARA", "reference": "T450"},
        ]}

        resultat = gen._reconcile_batch(self.produits, gen._normaliser_sorties(brut))

        assert [r.marque for r in resultat] == ["NOVARA", "ORTIS"]
        assert not any("absent_reponse_llm" in r.alertes for r in resultat)

    def test_objet_unique_devient_liste_de_un(self):
        gen = _make_generator()
        assert gen._normaliser_sorties({"id_produit": "1", "marque": "NOVARA"}) == [
            {"id_produit": "1", "marque": "NOVARA"}
        ]

    def test_liste_vide_enveloppee(self):
        gen = _make_generator()
        assert gen._normaliser_sorties({"produits": []}) == []

    def test_forme_inexploitable(self):
        gen = _make_generator()
        assert gen._normaliser_sorties({"message": "aucun produit"}) == []
        assert gen._normaliser_sorties("texte") == []
        assert gen._normaliser_sorties(None) == []


# ─────────────────────────────────────────────────────────────────────────────
# Garde-fous deterministes : le cout d'erreur n'est pas symetrique
# ─────────────────────────────────────────────────────────────────────────────

class TestValidateExtraction:
    def _valider(self, item, titre="Pont elevateur NOVARA T450 4 colonnes",
                categorie="Pont elevateur", description=""):
        gen = _make_generator()
        produit = {"id_produit": "1", "titre": titre,
                   "categorie": categorie, "description": description}
        return gen._validate_extraction(item, produit)

    def test_cas_nominal_conserve(self):
        res = self._valider({"id_produit": "1", "marque": "NOVARA", "reference": "T450",
                             "provenance": "titre", "extrait_marque": "NOVARA T450"})
        assert res.marque == "NOVARA"
        assert res.reference == "T450"
        assert res.provenance == "titre"

    def test_marque_absente_du_texte_rejetee(self):
        """Verbatim signifie present dans le texte : sinon c'est une invention."""
        res = self._valider({"id_produit": "1", "marque": "CATERPILLAR"})
        assert res.marque is None
        assert "marque_absente_du_texte" in res.alertes

    def test_marque_egale_au_libelle_categorie_rejetee(self):
        res = self._valider({"id_produit": "1", "marque": "Pont elevateur"})
        assert res.marque is None
        assert "marque_generique" in res.alertes

    def test_valeur_mesuree_rejetee(self):
        res = self._valider({"id_produit": "1", "marque": "12 kW"},
                            titre="Pont elevateur 12 kW NOVARA")
        assert res.marque is None

    def test_forme_juridique_rejetee(self):
        res = self._valider({"id_produit": "1", "marque": "SARL"},
                            titre="Pont elevateur SARL NOVARA")
        assert res.marque is None

    def test_norme_rejetee(self):
        res = self._valider({"id_produit": "1", "marque": "ISO 9001"},
                            titre="Pont elevateur ISO 9001 certifie")
        assert res.marque is None

    def test_etat_transaction_rejete(self):
        res = self._valider({"id_produit": "1", "marque": "occasion"},
                            titre="Pont elevateur d'occasion NOVARA")
        assert res.marque is None

    def test_marque_courte_conservee_mais_alertee(self):
        res = self._valider({"id_produit": "1", "marque": "JLG"},
                            titre="Pont elevateur JLG 450 tonnes")
        assert res.marque == "JLG"
        assert "marque_courte" in res.alertes

    def test_reference_absente_du_texte_rejetee(self):
        res = self._valider({"id_produit": "1", "marque": "NOVARA", "reference": "ZZ-999"})
        assert res.marque == "NOVARA"
        assert res.reference is None
        assert "reference_absente_du_texte" in res.alertes

    def test_reference_avec_tirets_et_espaces_acceptee(self):
        """La comparaison est alphanumerique : 'AB 120-XR' == 'AB120XR'."""
        res = self._valider({"id_produit": "1", "reference": "AB 120-XR"},
                            titre="Pont elevateur ref AB120XR")
        assert res.reference == "AB 120-XR"

    def test_marque_trouvee_dans_la_description(self):
        res = self._valider({"id_produit": "1", "marque": "KROEMER", "provenance": "description"},
                            titre="Pont elevateur double ciseaux",
                            description="Fabricant : KROEMER, capacite 4000 kg")
        assert res.marque == "KROEMER"

    def test_provenance_invalide_ramenee_a_absente(self):
        res = self._valider({"id_produit": "1", "marque": "NOVARA", "provenance": "inventee"})
        assert res.provenance == "absente"

    def test_provenance_absente_si_aucune_marque(self):
        res = self._valider({"id_produit": "1", "marque": None, "provenance": "titre"})
        assert res.provenance == "absente"

    def test_alertes_inconnues_filtrees(self):
        res = self._valider({"id_produit": "1", "marque": "NOVARA",
                             "alertes": ["marque_composant", "alerte_inventee"]})
        assert "marque_composant" in res.alertes
        assert "alerte_inventee" not in res.alertes

    def test_alertes_non_liste_toleree(self):
        res = self._valider({"id_produit": "1", "marque": "NOVARA", "alertes": "marque_composant"})
        assert res.alertes == ["marque_composant"]

    def test_chaines_vides_normalisees_en_none(self):
        res = self._valider({"id_produit": "1", "marque": "", "reference": "  "})
        assert res.marque is None
        assert res.reference is None


# ─────────────────────────────────────────────────────────────────────────────
# Routage des endpoints et deroulement du run
# ─────────────────────────────────────────────────────────────────────────────

class TestRun:
    def test_endpoints_et_etape_16(self):
        client = _make_api_client()
        gen = _make_generator(client, sorties_llm=[
            {"id_produit": "1", "marque": "NOVARA", "reference": "T450"}
        ])

        resultat = asyncio.run(gen.run(RequestFabricantReference(id_categorie="42", source="bo")))

        appels = {(e, f, a) for e, f, a, _ in client._calls}
        assert ("fabricant_reference", "produits", "get") in appels
        assert ("fabricant_reference", "extraction", "save") in appels
        assert ("prompt", "info", "get") in appels
        # aucun endpoint d'un autre service
        assert not [c for c in appels if c[0] == "caracterisation"]

        etapes = [d.get("etape") for _, f, _, d in client._calls if f in ("process", "mail")]
        assert etapes and all(e == "16" for e in etapes)
        assert resultat.total_processed == 1
        assert resultat.status == "completed"

    def test_prompt_133_demande(self):
        client = _make_api_client()
        gen = FabricantReferenceGenerator(client)
        asyncio.run(gen._load_prompt("42"))
        ids = [d.get("id_prompt") for e, f, a, d in client._calls if e == "prompt"]
        assert ids == ["133"]

    def test_save_recoit_les_extractions_du_batch(self):
        client = _make_api_client()
        gen = _make_generator(client, sorties_llm=[
            {"id_produit": "1", "marque": "NOVARA", "reference": "T450",
             "provenance": "titre", "extrait_marque": "NOVARA T450", "alertes": []}
        ])

        asyncio.run(gen.run(RequestFabricantReference(id_categorie="42", source="bo")))

        saves = [d for e, f, a, d in client._calls
                 if (e, f, a) == ("fabricant_reference", "extraction", "save")]
        assert len(saves) == 1
        assert saves[0]["id_categorie"] == "42"
        assert saves[0]["source"] == "bo"
        extraction = saves[0]["extractions"][0]
        assert extraction["id_produit"] == "1"
        assert extraction["marque"] == "NOVARA"
        assert set(extraction.keys()) == {
            "id_produit", "marque", "reference", "modele",
            "provenance", "extrait_marque", "alertes",
        }

    def test_batchs_de_dix_produits(self):
        produits = [
            {"id_produit": str(i), "titre": f"Pont NOVARA T{i}", "categorie": "Pont", "description": ""}
            for i in range(1, 26)
        ]
        client = _make_api_client(produits=produits)
        gen = _make_generator(client, sorties_llm=[])

        asyncio.run(gen.run(RequestFabricantReference(id_categorie="42", source="bo")))

        saves = [d for e, f, a, d in client._calls
                 if (e, f, a) == ("fabricant_reference", "extraction", "save")]
        assert [len(s["extractions"]) for s in saves] == [10, 10, 5]

    def test_aucun_produit_termine_sans_appel_llm(self):
        client = _make_api_client(produits=[])
        gen = _make_generator(client)

        resultat = asyncio.run(gen.run(RequestFabricantReference(id_categorie="42", source="bo")))

        assert resultat.total_processed == 0
        assert resultat.status == "completed"
        assert gen._prompts_envoyes == []

    def test_process_ne_peut_pas_demarrer(self):
        client = _make_api_client()

        async def fake_post(etape, field, action, data=None):
            client._calls.append((etape, field, action, data or {}))
            if (etape, field, action) == ("category", "info", "get"):
                return {"nom_rubrique": "Pont", "description": ""}
            if (etape, field, action) == ("prompt", "info", "get"):
                return dict(PROMPT)
            if (etape, field, action) == ("fabricant_reference", "process", "get"):
                return {"can_start": False}
            return True

        client.post.side_effect = fake_post
        gen = _make_generator(client)

        try:
            asyncio.run(gen.run(RequestFabricantReference(id_categorie="42", source="bo")))
        except Exception as exc:
            assert "commencer" in str(exc).lower()
        else:
            raise AssertionError("Le run doit s'arreter si can_start est faux")

    def test_sauvegardes_jamais_concurrentes(self):
        """Les appels LLM sont paralleles, les sauvegardes non.

        Cote BO, extraction/save alimente aussi le referentiel des marques de la
        categorie. Deux batchs simultanes portant deux graphies d'une meme marque
        ("Wacker-Neuson" / "Wacker Neuson") ne la trouveraient ni l'un ni l'autre et
        creeraient deux lignes, scindant nb_occurrences_fmr.
        """
        produits = [
            {"id_produit": str(i), "titre": f"Pont NOVARA T{i}", "categorie": "Pont", "description": ""}
            for i in range(1, 31)
        ]
        client = _make_api_client(produits=produits)
        routage = client.post.side_effect
        etat = {"en_cours": False, "chevauchements": 0, "saves": 0}

        async def fake_post(etape, field, action, data=None):
            if (etape, field, action) != ("fabricant_reference", "extraction", "save"):
                return await routage(etape, field, action, data)

            etat["saves"] += 1
            if etat["en_cours"]:
                etat["chevauchements"] += 1
            etat["en_cours"] = True
            await asyncio.sleep(0)  # cede la main : une autre tache peut s'intercaler
            resultat = await routage(etape, field, action, data)
            etat["en_cours"] = False
            return resultat

        client.post.side_effect = fake_post
        gen = _make_generator(client, sorties_llm=[])

        asyncio.run(gen.run(RequestFabricantReference(id_categorie="42", source="bo")))

        assert etat["saves"] == 3, "3 batchs de 10 produits attendus"
        assert etat["chevauchements"] == 0

    def test_batch_en_echec_ne_stoppe_pas_le_run(self):
        """Un batch perdu = 10 produits sans ligne, repris au run suivant.
        Interrompre un run de 746k produits sur un 500 transitoire serait pire."""
        produits = [
            {"id_produit": str(i), "titre": f"Pont NOVARA T{i}", "categorie": "Pont", "description": ""}
            for i in range(1, 16)
        ]
        client = _make_api_client(produits=produits)
        gen = _make_generator(client, erreur_llm=True)

        resultat = asyncio.run(gen.run(RequestFabricantReference(id_categorie="42", source="bo")))

        assert resultat.total_processed == 0
        assert resultat.total_echecs == 2
        assert resultat.status == "completed_with_errors"
        mails = [d for e, f, a, d in client._calls if f == "mail"]
        assert mails, "un mail de compte rendu doit partir"
