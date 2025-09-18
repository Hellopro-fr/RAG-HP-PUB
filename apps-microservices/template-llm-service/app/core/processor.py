import json
import re
import asyncio
from transformers import AutoTokenizer
from common_utils.grpc_clients import llm_client

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
{{ "page_type": "autre", "commentaire_si_autre": "explication en 15 mots max" }}
Critère clé : ne te base pas uniquement sur les balises Markdown.
Analyse le but de la page pour l’utilisateur final : s’informer, comparer, acheter, demander un devis, découvrir une offre locale, etc.
Voici les types de pages possibles :
"home" : page d’accueil du site.
"listing_produit" : page présentant une **gamme de produits** ou une **catégorie de produits**, listant plusieurs modèles ou variantes, avec navigation possible vers des fiches détaillées. Peut contenir des descriptions générales, comparatifs, avantages, caractéristiques et prix de plusieurs modèles.
"fiche_produit" : page présentant en détail un seul produit spécifique.
"fiche_realisation" : page montrant un projet ou cas client réalisé.
"Presentation-societe" : présentation institutionnelle de l’entreprise (histoire, équipe, mission), sans mention produit.
"contact" : prise de contact (formulaire, téléphone, carte, email), ou liste des points de vente.
"cgv_mentions_legales_cgu" : page juridique : CGV, CGU, mentions légales, droits, responsabilités, propriété intellectuelle.
"article" : contenu éditorial (blog, guide, actualité) visant à informer, conseiller ou expliquer un sujet.
"Savoir_faire" : page valorisant une expertise technique ou métier liée au matériel ou service proposé.
"Page_local" : page SEO dédiée à une localisation précise, avec une offre ou un savoir-faire ciblé localement.
"demande_devis" : page pour obtenir un devis sur un ou plusieurs produits.
"compte_client" : espace personnel de connexion ou gestion client (commandes, devis, infos personnelles, etc).
"recrutement" : page de recrutement avec un ou plusieurs offres d’emploi.
"references_clients" : logos, témoignages ou avis clients valorisant l’entreprise.
"faq" : questions fréquentes.
"plan_du_site" : liste structurée de liens vers les pages du site.
"politique_confidentialite" : politique de confidentialité ou cookies, RGPD, gestion des données personnelles.
"autre" : si aucun de ces types ne correspond.
Rappels :
Si "page_type" ≠ "autre", ne génère pas de champ "commentaire_si_autre".
Génère seulement le JSON, sans autre texte.
Ne pas se laisser influencer par les premières balises Markdown (ex : une page “containers à Lyon” n’est ni une fiche produit ni un article, mais une offre localisée = "offre_segment").
Analyse le but marketing ou fonctionnel de la page.
Voici l'url de la page : {url}
Contenu en entrée (Markdown) :
{content}
"""

# Le tokenizer est chargé une seule fois pour la validation de la longueur du prompt.
# C'est une opération légère qui ne nécessite pas de GPU.
TOKENIZER = AutoTokenizer.from_pretrained("Qwen/Qwen3-14B-AWQ", trust_remote_code=True)
MAX_MODEL_LEN = 4096 # Correspond à la configuration du modèle servi par vLLM

async def classify_page_template_batch(messages: list[dict]) -> list[dict]:
    """
    Prend un BATCH (une liste) de messages, les classifie tous avec un seul appel au LLM
    pour une efficacité maximale, et retourne une liste de messages enrichis.

    Args:
        llm_instance (LLM): L'instance du modèle vLLM chargé.
        tokenizer: Le tokenizer associé au modèle.
        llm_config (dict): La configuration du LLM (ex: max_model_len).
        messages (list[dict]): La liste des messages originaux à traiter.

    Returns:
        list[dict]: La liste des messages, chacun enrichi avec le "page_type".
    """
    prompts = []
    
    # --- Étape 1: Préparation des prompts pour le batch ---
    for message in messages:
        data_payload = message.get("data", {})
        url = data_payload.get("url", "URL non fournie")
        content = data_payload.get("text")
        
        # Formatage du prompt final avec l'URL et le contenu tronqué.
        user_prompt = PROMPT_TEMPLATE_FR.format(url=url, content=content)
        conversation = [{"role": "user", "content": user_prompt}]
        
        # apply_chat_template est la méthode recommandée pour formater le prompt
        # pour les modèles de type "chat".
        formatted_prompt = TOKENIZER.apply_chat_template(
            conversation, tokenize=False, add_generation_prompt=True, enable_thinking=False
        )
        
        # Validation de la longueur du prompt avant de l'envoyer
        if len(TOKENIZER.encode(formatted_prompt)) >= MAX_MODEL_LEN:
            print(f"   -> ⚠️  Prompt trop long pour l'URL {url}. Marqué comme erreur.")
            # On met un marqueur pour savoir que ce prompt ne doit pas être envoyé.
            prompts.append("PROMPT_TOO_LONG")
        else:
            prompts.append(formatted_prompt)

    # --- Étape 2: Appel gRPC par lots au service LLM ---
    # On filtre les prompts qui sont trop longs pour ne pas les envoyer.
    valid_prompts = [p for p in prompts if p != "PROMPT_TOO_LONG"]
    batch_outputs = []
    if valid_prompts:
        batch_outputs = await llm_client.get_llm_chat_batch_response(valid_prompts)
        
    # --- Étape 3: Traitement des résultats ---
    processed_messages = []
    output_index = 0
    for i, original_prompt in enumerate(prompts):
        original_message = messages[i]

        if original_prompt == "PROMPT_TOO_LONG":
            raise ValueError(f"   -> ⚠️  Le prompt pour le message {i} est trop long et n'a pas été envoyé.")
        else:
            if output_index < len(batch_outputs):
                raw_text = batch_outputs[output_index]
                output_index += 1
                try:
                    match = re.search(r'\{.*\}', raw_text, re.DOTALL)
                    if match:
                        json_string = match.group(0)
                        result = json.loads(json_string)
                        page_type = result.get("page_type")
                        if not page_type:
                            raise ValueError("Le champ 'page_type' est manquant ou vide.")
                    else:
                        raise ValueError("Aucun bloc JSON trouvé dans la sortie du LLM.")
                except Exception as e:
                    raise ValueError(f"   -> ⚠️  Erreur de parsing JSON pour un message. Sortie brute: '{raw_text}'. Erreur: {e}")
            else:
                raise ValueError(f"   -> ⚠️  Aucune réponse du service LLM pour le prompt {i}.")
        
        original_message["data"]["page_type"] = page_type
        processed_messages.append(original_message)
    
    print(f"   -> Classification en batch terminée pour {len(processed_messages)} messages.")
    # Afficher les types de pages détectés pour chaque message
    for msg in processed_messages:
        print(f"      • URL: {msg['data'].get('url', 'N/A')} => Type de page: {msg['data'].get('page_type', 'N/A')}")
        
    return processed_messages