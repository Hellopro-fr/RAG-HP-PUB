import json
import re
from vllm import LLM, SamplingParams
from bs4 import BeautifulSoup

# Le prompt est défini ici, avec la logique métier
PROMPT_TEMPLATE_FR = """
Tu es un classifieur expert de pages web. Ta seule et unique tâche est de retourner un objet JSON valide.

**Instructions Strictes:**
- Ta sortie doit commencer par `{` et se terminer par `}`.
- Ne fournis AUCUN texte, commentaire, ou explication avant ou après l'objet JSON.
- Si la page correspond à un type, retourne `{"type_page": "valeur"}`.
- Si aucun type ne correspond, retourne `{"type_page": "autre", "commentaire_si_autre": "Ton explication ici."}`.

**Exemple de Tâche:**
[ENTRÉE]
URL: https://www.example.com/produits/marteau-piqueur
Contenu: Marteau Piqueur PRO-X2000. Le marteau piqueur PRO-X2000 est l'outil ultime pour tous vos travaux de démolition.

[SORTIE JSON ATTENDUE]
{"type_page": "fiche_produit"}

**Liste des types de pages possibles:**
"home", "listing_produit", "fiche_produit", "fiche_realisation", "Presentation-societe", "contact", "cgv_mentions_legales_cgu", "article", "Savoir_faire", "Page_local", "demande_devis", "compte_client", "recrutement", "references_clients", "faq", "plan_du_site", "politique_confidentialite", "autre".

---
**TACHE ACTUELLE :**
[ENTRÉE]
URL: {url}
Contenu: {content}

[SORTIE JSON ATTENDUE]
"""

def classify_page_template(llm_instance: LLM, tokenizer, llm_config: dict, message: dict) -> dict:
    """
    Prend un message, nettoie son contenu, le classifie avec le LLM,
    et retourne le message enrichi.
    """
    data_payload = message.get("data", {})
    url = data_payload.get("url", "URL non fournie")
    content = data_payload.get("text", "")

    if not content:
        print("   -> Contenu vide, message ignoré.")
        message["data"]["type_page"] = "contenu_vide"
        return message

    # On suppose que le contenu est déjà nettoyé, mais on garde BeautifulSoup par sécurité.
    soup = BeautifulSoup(content, 'html.parser')
    for tag in soup(["script", "style", "header", "footer", "nav", "aside"]):
        tag.decompose()
    cleaned_text = soup.get_text(separator='\n', strip=True)

    # Troncature par Tokens pour éviter les erreurs de dépassement
    max_model_len = llm_config.get("max_model_len", 4096)
    max_content_tokens = max_model_len - 1024 # Marge de sécurité pour le prompt
    content_tokens = tokenizer.encode(cleaned_text)
    if len(content_tokens) > max_content_tokens:
        truncated_tokens = content_tokens[:max_content_tokens]
        truncated_content = tokenizer.decode(truncated_tokens)
    else:
        truncated_content = cleaned_text

    # Génération avec le LLM
    sampling_params = SamplingParams(max_tokens=250, temperature=0.1)
    user_prompt = PROMPT_TEMPLATE_FR.format(url=url, content=truncated_content)
    conversation = [{"role": "user", "content": user_prompt}]
    
    formatted_prompt = tokenizer.apply_chat_template(
        conversation, 
        tokenize=False, 
        add_generation_prompt=True,
        enable_thinking=False
    )
    
    outputs = llm_instance.generate([formatted_prompt], sampling_params)
    raw_text = outputs[0].outputs[0].text.strip()

    # Parsing robuste du résultat
    page_type = "erreur_parsing"
    try:
        match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if match:
            json_string = match.group(0)
            result = json.loads(json_string)
            page_type = result.get("type_page", "erreur_parsing")
        else:
            raise ValueError("Aucun bloc JSON trouvé dans la sortie du LLM.")
    except Exception as e:
        print(f"--- ERREUR DE PARSING JSON --- \nErreur: {e} \nSortie brute: '{raw_text}'")

    print(f"   -> Classification terminée : {page_type}")
    
    # Enrichissement du message original
    message["data"]["type_page"] = page_type
    return message
