import json
import re
from vllm import LLM, SamplingParams

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

def classify_page_template_batch(llm_instance: LLM, tokenizer, llm_config: dict, messages: list[dict]) -> list[dict]:
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
    
    # --- Étape 1: Préparation de tous les prompts pour le batch ---
    # Nous parcourons chaque message pour en extraire le contenu et construire
    # le prompt formaté qui sera envoyé au modèle.
    for message in messages:
        data_payload = message.get("data", {})
        url = data_payload.get("url", "URL non fournie")
        content = data_payload.get("text")
        
        if not content:
            raise ValueError("Le champ 'text' est vide ou manquant dans les données d'entrées.")

        # Sécurité : Tronquer le contenu si trop long pour éviter les erreurs du modèle.
        # On garde une marge de sécurité (1024 tokens) pour le template du prompt lui-même.
        max_model_len = llm_config.get("max_model_len", 4096)
        max_content_tokens = max_model_len - 1024
        content_tokens = tokenizer.encode(content)
        if len(content_tokens) > max_content_tokens:
            truncated_tokens = content_tokens[:max_content_tokens]
            truncated_content = tokenizer.decode(truncated_tokens)
        else:
            truncated_content = content
        
        # Formatage du prompt final avec l'URL et le contenu tronqué.
        user_prompt = PROMPT_TEMPLATE_FR.format(url=url, content=truncated_content)
        conversation = [{"role": "user", "content": user_prompt}]
        
        # apply_chat_template est la méthode recommandée pour formater le prompt
        # pour les modèles de type "chat".
        formatted_prompt = tokenizer.apply_chat_template(
            conversation, tokenize=False, add_generation_prompt=True
        )
        prompts.append(formatted_prompt)

    # --- Étape 2: Appel unique et puissant au LLM avec tout le batch de prompts ---
    # C'est ici que réside le gain de performance. vLLM va traiter tous ces prompts
    # en parallèle sur le GPU.
    sampling_params = SamplingParams(max_tokens=250, temperature=0.1)
    batch_outputs = llm_instance.generate(prompts, sampling_params)

    # --- Étape 3: Traitement des résultats pour chaque message ---
    processed_messages = []
    for i, output in enumerate(batch_outputs):
        # On récupère le message original correspondant à ce résultat
        original_message = messages[i]
        raw_text = output.outputs[0].text.strip()
        
        # Le parsing du JSON doit être robuste car le LLM peut parfois échouer.
        # On utilise une expression régulière pour extraire le bloc JSON, même s'il est
        # entouré d'autre texte.
        try:
            match = re.search(r'\{.*\}', raw_text, re.DOTALL)
            if match:
                json_string = match.group(0)
                result = json.loads(json_string)
                page_type = result.get("page_type")
                # Vérification de sécurité : si le champ est vide ou manquant.
                if not page_type:
                    raise ValueError("Le champ 'page_type' est manquant ou vide dans le JSON.")
            else:
                 raise ValueError("Aucun bloc JSON trouvé dans la sortie du LLM.")
        except Exception as e:
            # Si le parsing échoue, on assigne un type d'erreur pour ne pas bloquer le flux.
            print(f"   -> ⚠️  Erreur de parsing JSON pour un message. Sortie brute: '{raw_text}'. Erreur: {e}")
            page_type = "erreur_parsing"

        # On enrichit le message original avec le résultat de la classification
        # et on l'ajoute à notre liste de résultats.
        original_message["data"]["page_type"] = page_type
        processed_messages.append(original_message)
    
    print(f"   -> Classification en batch terminée pour {len(processed_messages)} messages.")
    return processed_messages