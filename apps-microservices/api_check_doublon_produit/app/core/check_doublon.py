from app.schemas.check_doublon_shemas import SearchRequest
from pymilvus import connections, Collection, utility

from app.core.credentials import settings

from common_utils.database.MilvusProduitCrud import MilvusProduitsCrud
from common_utils.database.MilvusFournisseursCrud import MilvusFournisseursCrud

import logging
import requests
import httpx


logger = logging.getLogger(__name__)

async def search_in_milvus(request: SearchRequest):
    logger.info(f"[MILVUS] Recherche: nom_produit='{request.nom_produit}...', domaine={request.domaine[:50]}")

    bv_produit = MilvusProduitsCrud()
    bv_fournisseurs = MilvusFournisseursCrud()

    # === Vérification produit ===
    res_p = bv_produit.get_produit_by_field("nom_produit", request.nom_produit)
    nom_produit_existe = (res_p.get("status") == "success" and len(res_p.get("data", [])) > 0)

    # === Vérification domaine (multi champs) ===
    domaine_existe = False
    champs_domaine = ["domaine"] + [f"domaine{i}" for i in range(2, 7)]

    for field in champs_domaine:
        res_f = bv_fournisseurs.get_fournisseur_by_field(field, request.domaine)
        if res_f.get("status") == "success" and len(res_f.get("data", [])) > 0:
            domaine_existe = True
            break
        elif res_f.get("status") == "error":
            logger.warning(f"[MILVUS] Erreur lors de la vérification {field}='{request.domaine}' → {res_f.get('message')}")

    # === Cas doublon exact ===
    if nom_produit_existe and domaine_existe:
        return {
            "id_produit": request.id_produit,
            "is_doublon": True,
            "from_similarity": False,
            "score": 1.0  # score max si doublon exact
        }

    # === Sinon, recherche vectorielle ===
    IS_DOUBLON = False
    FROM_SIMILARITY = False
    SCORE = 0.0

    seuil_score_doublon = settings.SEUIL_SCORE_DOUBLON
    payload = {
        "prompt": request.nom_produit,
        "source": [settings.COLLECTION_PRODUIT_NAME],
        "nombre_resultat": "10"
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(settings.URL_QUERY_API_RECHERCHE, json=payload)

        if response.status_code != 200:
            logger.error(f"[MILVUS] Erreur API recherche: {response.status_code} - {response.text}")
        else:
            data = response.json()
            produits = data.get("results", {}).get("matches", {}).get(settings.COLLECTION_PRODUIT_NAME, [])

            for produit in produits:
                score = produit.get("score", 0.0)
                if score >= seuil_score_doublon:
                    FROM_SIMILARITY = True
                    SCORE = score
                    IS_DOUBLON = True
                    break

    except httpx.RequestError as e:
        logger.error(f"[MILVUS] Erreur requête API recherche: {e}")

    return {
        "id_produit": request.id_produit,
        "is_doublon": IS_DOUBLON,
        "from_similarity": FROM_SIMILARITY,
        "score": SCORE
    }

async def search_in_milvus_me(request: SearchRequest):
    logger.info(f"[MILVUS] Recherche: nom_produit='{request.nom_produit}...', domaine={request.domaine[:50]}")
    
    bv_produit      = MilvusProduitsCrud()
    bv_fournisseurs = MilvusFournisseursCrud()
    
    res_p = bv_produit.get_produit_by_field(field_name="nom_produit", search_value= request.nom_produit)
    
    status  = res_p.get("status")
    data    = res_p.get("data", [])    
    message = res_p.get("message", "")
    
    nom_produit_existe = False
    if status == "error":
        logger.info(f"[MILVUS] Erreur lors de la vérification du produit ='{request.nom_produit}...', message={message}")    
    elif status == "success":
        if len(data) > 0:
            nom_produit_existe = True
            
    domaine_existe = False
    res_f = bv_fournisseurs.get_fournisseur_by_field(field_name= "domaine", search_value= request.domaine)
    
    status  = res_f.get("status")
    data    = res_f.get("data", [])
    message = res_f.get("message", "")
    
    if status == "error":
        logger.info(f"[MILVUS] Erreur lors de la vérification fournisseur(domaine) ='{request.nom_produit}...', message={message}")    
    elif status == "success":
        if len(data) > 0:
            domaine_existe = True
            
    if not domaine_existe:
        for i in range(2, 7):
            domaine_field = f"domaine{i}"
            res_f = bv_fournisseurs.get_fournisseur_by_field(field_name= domaine_field, search_value= request.domaine)
            
            status  = res_f.get("status")
            data    = res_f.get("data", [])
            message = res_f.get("message", "")
            
            if status == "error":
                logger.info(f"[MILVUS] Erreur lors de la vérification fournisseur({domaine_field}) ='{request.nom_produit}...', message={message}")    
            elif status == "success":
                if len(data) > 0:
                    domaine_existe = True
                    break
    
    # =================================================
    IS_DOUBLON      = False
    FROM_SIMILARTIY = False
    SCORE           = 0.0
    # =================================================
    
    if nom_produit_existe and domaine_existe:
        IS_DOUBLON = True
    
    if not IS_DOUBLON :
        # to do query api recherche
        seuil_score_doublon = settings.SEUIL_SCORE_DOUBLON
                
        # url_query           = f"{settings.ADRESSE_VM}:{settings.PORT_API_RECHERCHE}/milvus/search"
        # url_query           = "http://34.90.162.9:8500/search-service/milvus/search"
        # url_query           = "http://34.67.7.126:8500/search-service/milvus/search" #vm2        
        
        payload = {
            "prompt": request.nom_produit,
            "source": [
                settings.COLLECTION_PRODUIT_NAME
            ],
            "nombre_resultat": "10"
        }        
        response = requests.post(settings.URL_QUERY_API_RECHERCHE, json=payload)        
        
        if response.status_code != 200:
            logger.info(f"[MILVUS] Erreur API recherche: {response.status_code} - {response.text}")
        else:
            data = response.json()
            
            produits = data.get("results", {}).get("matches", {}).get(settings.COLLECTION_PRODUIT_NAME, [])                
            for produit in produits:
                if produit["score"] >= seuil_score_doublon:
                    FROM_SIMILARTIY = True
                    SCORE           = produit["score"]
                    break
        
    return {
        "id_produit"     : request.id_produit,
        "is_doublon"     : IS_DOUBLON,
        "from_similarity": FROM_SIMILARTIY,
        "score"          : SCORE
    }
    

def get_milvus_connection():
    alias = "default"
    try:
        if not connections.has_connection(alias):
            logger.info("Connexion à Milvus...")
            # connections.connect(alias, uri=settings.MILVUS_URI, token=settings.MILVUS_TOKEN)
            connections.connect("default", uri=settings.ZILLIZ_URI, token=settings.ZILLIZ_API_KEY)
            # connections.connect(alias, host=settings.ZILLIZ_URI, port=settings.ZILLIZ_PORT)
            logger.info(f"Connecté à Milvus.")
    except Exception as e:
        logger.error(f"❌ Erreur de connexion à Milvus: {e}")
        raise e
