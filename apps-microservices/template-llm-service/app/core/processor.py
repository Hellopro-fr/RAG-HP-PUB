import os
import json
import re
import asyncio
from transformers import AutoTokenizer
from common_utils.grpc_clients import llm_client
from common_utils.grpc_clients.schemas.chat import ChatRequest
from common_utils.metrics.prometheus import measure_processing_time

# Liste des pages types autorisées
page_types_siteweb = [
    "home",
    "listing_produit",
    "fiche_produit",
    "fiche_realisation",
    "presentation_societe",
    "contact",
    "cgv_mentions_legales_cgu",
    "article",
    "savoir_faire",
    "page_local",
    "demande_devis",
    "compte_client",
    "recrutement",
    "references_clients",
    "faq",
    "plan_du_site",
    "politique_confidentialite",
    "autre"
]

page_types_ocr = [
    "devis",
    "fiche_technique",
    "catalogue",
    "plaquette_prix",
    "savoir-faire",
    "autre"
]

# Le prompt est défini ici, avec la logique métier
PROMPT_TEMPLATE_FR = """
Tu es un classifieur de type de pages pour sites de fournisseurs de matériel professionnel.
En entrée, tu reçois le contenu texte présent dans le code source HTML d’une page. Attention, il faut donc identifier le contenu principal de la page et en identifier le sens. Ne pas se laisser influencer par le contenu présent dans le header ou le footer par exemple.
Ta tâche est de déterminer quelle est la fonction principale de cette page pour l’utilisateur final, pas simplement sa structure HTML.
En sortie, tu dois produire un objet JSON :
Si la page correspond à un des types listés → retourne uniquement :
json
{{ "page_type": "valeur" }}
Si la page ne correspond à aucun type → retourne :
json
{{ "page_type": "autre" }}
Critère clé : ne te base pas uniquement sur les balises Markdown.
Analyse le but de la page pour l’utilisateur final : s’informer, comparer, acheter, demander un devis, découvrir une offre locale, etc.
Voici les types de pages possibles :
"home" : page d’accueil du site.
"listing_produit" : page présentant une **gamme de produits** ou une **catégorie de produits**, listant plusieurs modèles ou variantes, avec navigation possible vers des fiches détaillées. Peut contenir des descriptions générales, comparatifs, avantages, caractéristiques et prix de plusieurs modèles.
"fiche_produit" : page présentant en détail un seul produit spécifique.
"fiche_realisation" : page montrant un projet ou cas client réalisé.
"presentation_societe" : présentation institutionnelle de l’entreprise (histoire, équipe, mission), sans mention produit.
"contact" : prise de contact (formulaire, téléphone, carte, email), ou liste des points de vente.
"cgv_mentions_legales_cgu" : page juridique : CGV, CGU, mentions légales, droits, responsabilités, propriété intellectuelle.
"article" : contenu éditorial (blog, guide, actualité) visant à informer, conseiller ou expliquer un sujet.
"savoir_faire" : page valorisant une expertise technique ou métier liée au matériel ou service proposé.
"page_local" : page SEO dédiée à une localisation précise, avec une offre ou un savoir-faire ciblé localement.
"demande_devis" : page pour obtenir un devis sur un ou plusieurs produits.
"compte_client" : espace personnel de connexion ou gestion client (commandes, devis, infos personnelles, etc).
"recrutement" : page de recrutement avec un ou plusieurs offres d’emploi.
"references_clients" : logos, témoignages ou avis clients valorisant l’entreprise.
"faq" : questions fréquentes.
"plan_du_site" : liste structurée de liens vers les pages du site.
"politique_confidentialite" : politique de confidentialité ou cookies, RGPD, gestion des données personnelles.
"autre" : si aucun de ces types ne correspond.
Rappels :
Génère seulement le JSON, sans autre texte.
Ne pas se laisser influencer par les premières balises Markdown (ex : une page “containers à Lyon” n’est ni une fiche produit ni un article, mais une offre localisée = "offre_segment").
Analyse le but marketing ou fonctionnel de la page.
Voici l'url de la page : {url}
Contenu en entrée (Markdown) :
{content}
"""
PROMPT_OCR_FR = """
Tu es un classifieur de type de document.
En entrée, tu reçois le contenu texte présent dans le document. Attention, il faut donc identifier le contenu principal du document et en identifier le sens. Ne pas se laisser influencer par le contenu présent dans le header ou le footer par exemple.
Ta tâche est de déterminer quelle est la fonction principale de ce document pour l’utilisateur final, pas simplement sa structure.
En sortie, tu dois produire un objet JSON :
Si la page correspond à un des types listés → retourne uniquement :
json
{{ "page_type": "valeur" }}
Si la page ne correspond à aucun type ou la page n'est pas en français → retourne :
json
{{ "page_type": "autre", "commentaire_si_autre": "explication en 15 mots max" }}
Critère clé : ne te base pas uniquement sur les balises Markdown.
Analyse le but du document pour l’utilisateur final : décider d’un achat (devis), s’informer en détail (fiche technique), découvrir et comparer l’offre (catalogue), évaluer rapidement les tarifs (plaquette prix),etc.
Voici les types de pages possibles :
"devis" : document commercial qui détaille une offre (produit ou service), ses conditions, son prix et qui engage le fournisseur si accepté.
"fiche_technique" : document décrivant les caractéristiques, fonctionnalités et spécifications d’un produit ou service.
"catalogue" : recueil structuré présentant l’ensemble ou une partie des produits/services proposés par une entreprise.
"plaquette_prix" : support listant les tarifs des produits ou services, généralement sous forme simplifiée et claire pour les clients.
"savoir-faire" : page mettant en avant les compétences, expertises, méthodes ou réalisations spécifiques d’une entreprise, illustrant sa maîtrise dans un domaine spécifique.
"autre" : si aucun de ces types ne correspond.
Rappels :
Si "page_type" ≠ "autre", ne génère pas de champ "commentaire_si_autre".
Génère seulement le JSON, sans autre texte.
Analyse le but marketing ou fonctionnel du document.
Contenu en entrée (Markdown) :
{content}
"""

TOKENIZER = AutoTokenizer.from_pretrained("deepseek-ai/DeepSeek-R1", trust_remote_code=True)
MAX_MODEL_LEN = 128000 # Correspond à la limite théorique du modèle DeepSeek-R1
# On définit une limite de sécurité un peu en dessous du max pour éviter les erreurs "off-by-one"
SAFE_MAX_LEN = MAX_MODEL_LEN - 512

async def _process_single_message(message: dict) -> dict:
    """
    Traite un seul message en appelant le LLM. Conçu pour être exécuté en parallèle.
    """
    original_message = message
    metric_payload = {}
    try:
        data_payload = message.get("data", {})
        collection = message.get("collection", {})
        url = data_payload.get("url", "URL non fournie")
        content = data_payload.get("text")
        
        if collection == "document":
            user_prompt = PROMPT_OCR_FR.format(content=content)
            process_id = 32
        else:
            user_prompt = PROMPT_TEMPLATE_FR.format(url=url, content=content)
            process_id = 31
        
        # Encodage pour vérifier la longueur
        prompt_tokens = TOKENIZER.encode(user_prompt)
        token_count = len(prompt_tokens)

        # --- NOUVEAU: Logique de troncature ---
        if token_count >= SAFE_MAX_LEN:
            print(f"   -> ⚠️  AVERTISSEMENT: Le prompt pour l'URL {url} ({token_count} tokens) dépasse la limite de sécurité. Troncature en cours...")
            # On tronque la liste de tokens et on la décode à nouveau
            truncated_tokens = prompt_tokens[:SAFE_MAX_LEN]
            user_prompt = TOKENIZER.decode(truncated_tokens, skip_special_tokens=True)
            # On met à jour le compte de tokens pour le log
            token_count = len(truncated_tokens)
            print(f"   -> Prompt tronqué à {token_count} tokens.")

        # Ajout des métriques de diagnostic au message
        original_message["_diag_content_length"] = len(content) if content else 0
        original_message["_diag_token_count"] = token_count

        # Appel gRPC pour un seul prompt
        chat_request = ChatRequest(
            prompt=user_prompt,
            temperature=0.7,
            max_tokens=256,
            enable_thinking=False
        )
        raw_response_dict = await llm_client.get_llm_chat_response(chat_request)
        
        # Construction du payload de métriques
        response_details = raw_response_dict.get('response', {})
        usage_details = response_details.get('usage', {})
        error_details = response_details.get('error', {})
        state_llm = 1 if not error_details else 2

        metric_payload = {
            "source_service": "template-llm-service",
            "url": url,
            "state_llm": state_llm,
            "prompt_tokens": usage_details.get('prompt_tokens'),
            "completion_tokens": usage_details.get('completion_tokens'),
            "total_tokens": usage_details.get('total_tokens'),
            "model": response_details.get('model'),
            "raw_response_on_error": raw_response_dict if state_llm == 2 else None,
            "process_id": process_id
        }
        
        if state_llm == 2:
            raise ValueError(f"Erreur du LLM: {raw_response_dict}")

        # Parsing de la réponse
        raw_text = raw_response_dict.get('full_message', '')
        match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if match:
            json_string = match.group(0)
            parsed_json = json.loads(json_string)
            page_type = parsed_json.get("page_type")
            if not page_type:
                raise ValueError(f"Le champ 'page_type' est manquant ou vide dans la réponse JSON: {raw_text}")
            
            page_type = page_type.strip().lower()

            if collection == "document":
                allowed_types = page_types_ocr
                source_type = "OCR"
            else:
                allowed_types = page_types_siteweb
                source_type = "site web"
            if page_type not in allowed_types:
                # Type hors liste : on force "autre" au lieu de lever une erreur
                # (sinon le message part en retry/DLQ pour un simple écart de label du LLM).
                print(f"   -> ⚠️  Type de page inconnu pour {source_type}: '{page_type}' pour l'URL {url}. Forçage à 'autre'.")
                original_message["data"]["commentaire_si_autre"] = f"Type non listé retourné par le LLM : '{page_type}'"
                page_type = "autre"
            elif page_type == "autre" and parsed_json.get("commentaire_si_autre"):
                original_message["data"]["commentaire_si_autre"] = parsed_json["commentaire_si_autre"]

            original_message["data"]["page_type"] = page_type
            return {
                "status": "success",
                "processed_message": original_message,
                "metric_payload": metric_payload
            }
        else:
            raise ValueError(f"Aucun bloc JSON trouvé dans la sortie du LLM: {raw_text}")

    except Exception as e:
        error_str = f"Erreur de traitement individuel. Erreur: {e}"
        # S'assurer qu'on a un payload de métrique même en cas d'erreur
        if not metric_payload:
             metric_payload = {
                "source_service": "template-llm-service",
                "url": original_message.get("data", {}).get("url", "URL non fournie"),
                "state_llm": 2, # Erreur
                "error_message": error_str
             }
        return {
            "status": "error",
            "original_message": original_message,
            "error_message": error_str,
            "metric_payload": metric_payload
        }

@measure_processing_time(service_name="template-llm-service", payload_arg_name="messages")
async def classify_page_template_batch(messages: list[dict]) -> list[dict]:
    """
    Traite un BATCH de messages en créant des tâches concurrentes pour chaque message,
    permettant au serveur vLLM de faire du 'continuous batching'.
    """
    if not messages:
        return []

    # --- Étape 1: Créer une tâche asyncio pour chaque message ---
    tasks = [_process_single_message(msg) for msg in messages]
    
    # --- Étape 2: Exécuter toutes les tâches en parallèle ---
    processed_results = await asyncio.gather(*tasks)
        
    # --- Étape 3: Journalisation des résultats ---
    print(f"   -> Classification en batch terminée pour {len(processed_results)} messages.")
    for res in processed_results:
        msg = res.get('processed_message') or res.get('original_message')
        url = msg['data'].get('url', 'N/A')
        
        if res['status'] == 'success':
            page_type = msg['data'].get('page_type', 'N/A')
            content_len = msg.get('_diag_content_length', 'N/A')
            metric = res.get('metric_payload', {})
            model = metric.get('model', 'N/A')
            prompt_tokens = metric.get('prompt_tokens', 'N/A')
            completion_tokens = metric.get('completion_tokens', 'N/A')
            print(f"      • [SUCCESS] URL: {url} => Type: {page_type} [Model: {model}, PromptTokens: {prompt_tokens}, CompletionTokens: {completion_tokens}, ContentLen: {content_len}]")
        else:
            print(f"      • [FAILURE] URL: {url} => Erreur: {res.get('error_message', 'Inconnue')}")
            
    return processed_results