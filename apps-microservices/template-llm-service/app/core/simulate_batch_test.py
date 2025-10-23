# simulate_batch_test.py

import asyncio
import json
import re
import time
from typing import List, Dict

from common_utils.grpc_clients import llm_client
from common_utils.grpc_clients.schemas.chat import ChatRequest
from vllm.transformers_utils.tokenizer import get_tokenizer

# --- Configuration du Test ---
NUM_BATCHES = 10
BATCH_SIZE = 2 # Doit correspondre à la configuration du service
TOTAL_MESSAGES = NUM_BATCHES * BATCH_SIZE

print(f"Configuration du test de performance :")
print(f" - Nombre de lots (batches) : {NUM_BATCHES}")
print(f" - Taille d'un lot : {BATCH_SIZE}")
print(f" - Nombre total de messages à traiter : {TOTAL_MESSAGES}\n")


PROMPT_SUPPLIER_PROFILE = """
Contexte
    Tu es un identificateur de profil fournisseur pour la catégorie Container aménagé sur Hellopro.
    Objectif
    Analyser et vérifier systématiquement chaque élément du brief pour déterminer si le fournisseur maisons containers couvre ou ne couvre pas une fonctionnalité/thème. Il faut prendre en compte toutes les informations explicitement mentionnées ou logiquement déduites sans ambiguïté.
    Règles strictes :
    1- Critères de réponse :
    - "Couvre" : Si le brief indique explicitement ou permet une déduction parfaite que le fournisseur fait X.
    - "Ne couvre pas" : Si le brief indique explicitement ou permet une déduction parfaite que le fournisseur ne fait pas X.
    - Réponse vide ("") : Si aucune information (explicite ou déduite) n’existe sur X dans le brief ou si la question concerne le client, les contraintes, le budget, le délai, ou tout élément hors fournisseur.
    2- Exclusions :
    - Aucune supposition n’est autorisée. Seules les données du brief déterminent les réponses.
    - Les questions non liées au fournisseur (délais, budget, contraintes, avancement, etc.) ou non mentionnées dans le brief doivent être vides ("").
    - Si le brief ne parle pas du thème, la réponse est vide ("").
    3- Processus de vérification :
    - Pour chaque option de la question, scanner le brief ligne par ligne sans omettre aucune section.
    - Identifier les éléments correspondants ou contraires au thème.
    Format de sortie attendu en json strictement sans prose :
    {{
    "id_question": "<id>",
    "intitule": "<thème court et clair>",
    "couvre": ["<id1>", "<id3>"] | "",
    "ne couvre pas" : ["<id2>"] | ""
    }}
    Voici le brief fournisseur à prendre en compte (se baser uniquement sur ce contenu) :
    {brief_fournisseur}
    Voici la question :
    {question}
"""

TOKENIZER = get_tokenizer("Qwen/Qwen3-14B-AWQ", trust_remote_code=True)
MAX_MODEL_LEN = 32768
SAFE_MAX_LEN = MAX_MODEL_LEN - 512

async def _process_single_message(message: dict) -> dict:
    original_message = message
    try:
        data_payload = message.get("data", {})
        brief_fournisseur = data_payload.get("brief_fournisseur")
        question = data_payload.get("question")
        if not brief_fournisseur or not question:
            raise ValueError("Le 'brief_fournisseur' ou la 'question' est manquant.")

        brief_str = json.dumps(brief_fournisseur, indent=2, ensure_ascii=False)
        question_str = json.dumps(question, indent=2, ensure_ascii=False)

        user_prompt = PROMPT_SUPPLIER_PROFILE.format(
            brief_fournisseur=brief_str,
            question=question_str
        )
        
        prompt_tokens = TOKENIZER.encode(user_prompt)
        token_count = len(prompt_tokens)

        if token_count >= SAFE_MAX_LEN:
            truncated_tokens = prompt_tokens[:SAFE_MAX_LEN]
            user_prompt = TOKENIZER.decode(truncated_tokens, skip_special_tokens=True)

        chat_request = ChatRequest(
            prompt=user_prompt,
            temperature=0.1,
            max_tokens=512,
            enable_thinking=False
        )
        raw_text = await llm_client.get_llm_chat_response(chat_request)
        
        match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if match:
            json_string = match.group(0)
            parsed_json = json.loads(json_string)
            original_message["data"]["analysis_result"] = parsed_json
            return {"status": "success", "processed_message": original_message}
        else:
            raise ValueError(f"Aucun JSON trouvé dans la sortie du LLM: {raw_text}")

    except Exception as e:
        return {"status": "error", "original_message": original_message, "error_message": str(e)}

async def run_analysis_batch(messages: List[Dict]) -> List[Dict]:
    if not messages:
        return []
    tasks = [_process_single_message(msg) for msg in messages]
    processed_results = await asyncio.gather(*tasks)
    return processed_results


# --- Script principal de simulation ---

async def main():
    # 1. Préparer les données de test (les mêmes pour tous les messages)
    brief_data = {
        "type_entreprise": "Fabricant / Prestataire",
        "lieux_fabrication": ["Pluvigner, France"],
        "marques_distribuees": "Non renseigné",
        "chiffres_cles": {"annee_creation": 1999, "effectif": "Non renseigné", "nombre_clients": "Non renseigné"},
        "cibles_commerciales": ["Particuliers", "Professionnels", "Collectivités (écoles, micro-crèches)", "Projets de rénovation de patrimoine ancien (bâtisse ancienne, manoir, abbaye, moulin)"],
        "positionnement_marche": "La SARL DOUBLIER se positionne comme une entreprise innovante et respectueuse de l’environnement...",
        "resume_activite_100_mots": "Depuis 1999, la SARL DOUBLIER propose des services dans le neuf et la rénovation...",
        "engagements_rse": "La SARL DOUBLIER adopte une démarche RSE complète : tri des déchets...",
        "projets_realises": "L’entreprise a réalisé son propre bureau en container maritime...",
        "pays_activite": ["FR"],
        "france_metropolitaine": "certaines-regions",
        "regions_france": ["FR-BRE"],
        "caracteristique": "### Types de Containers aménagés proposés :\\n- **Maisons individuelles**..."
    }
    
    question_data = [{
        "id_question": "15",
        "intitule": "Quel type d'aménagement prévoyez-vous pour le container ?",
        "choix": [
            {"id": "72", "reponse": "Hébergement / logement"},
            {"id": "73", "reponse": "Bureau / espace de travail"},
            {"id": "75", "reponse": "Restauration (restaurant, snack, bar, etc)"},
            {"id": "76", "reponse": "Sanitaire / vestiaire"},
            {"id": "77", "reponse": "Atelier / laboratoire"},
            {"id": "78", "reponse": "Événementiel / stand"},
            {"id": "79", "reponse": "Local technique"},
            {"id": "118", "reponse": "Autre"}
        ]
    }]

    # Créer une liste de 20 messages identiques
    messages_to_process = [
        {"collection": "supplier_profile_analysis", "data": {"brief_fournisseur": brief_data, "question": question_data}}
        for _ in range(TOTAL_MESSAGES)
    ]

    batch_durations = []
    total_start_time = time.monotonic()

    print("--- Démarrage de la simulation ---")

    # 2. Boucler pour traiter les 10 lots
    for i in range(NUM_BATCHES):
        start_index = i * BATCH_SIZE
        end_index = start_index + BATCH_SIZE
        current_batch = messages_to_process[start_index:end_index]
        
        print(f"⚙️  Traitement du lot {i + 1}/{NUM_BATCHES}...")
        
        batch_start_time = time.monotonic()
        results = await run_analysis_batch(current_batch)
        batch_end_time = time.monotonic()
        
        duration = batch_end_time - batch_start_time
        batch_durations.append(duration)
        
        # Vérifier les succès et les échecs
        success_count = sum(1 for r in results if r['status'] == 'success')
        print(f"🏁 Lot {i + 1} terminé en {duration:.4f} secondes ({success_count}/{BATCH_SIZE} succès).")

    total_end_time = time.monotonic()
    total_duration = total_end_time - total_start_time

    print("\n--- Fin de la simulation ---")

    # 3. Afficher les résultats de performance
    avg_batch_time = sum(batch_durations) / len(batch_durations)
    avg_message_time = total_duration / TOTAL_MESSAGES
    messages_per_second = TOTAL_MESSAGES / total_duration

    print("\n📊 === Résultats de Performance === 📊")
    print(f"Temps total d'exécution : {total_duration:.4f} secondes")
    print(f"Temps moyen par lot de {BATCH_SIZE} messages : {avg_batch_time:.4f} secondes")
    print(f"Temps moyen par message individuel : {avg_message_time:.4f} secondes")
    print(f"Débit (Throughput) : {messages_per_second:.2f} messages/seconde")
    print("======================================\n")


if __name__ == '__main__':
    # Assurez-vous que la boucle d'événements asyncio est correctement gérée
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nSimulation interrompue par l'utilisateur.")