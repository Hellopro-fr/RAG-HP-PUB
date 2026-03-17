"""
Service métier pour l'extraction des caractéristiques influençant le prix.
Conversion de la logique PHP (api.php → run_identification) en Python.
"""
import time
import json
import logging
from typing import Dict, Any, Optional, List

from app.core.api_client import GeminiProvider, HelloProAPIClient
from app.core.utils import extract_json_from_text, get_prompt
from app.core.credentials import settings

logger = logging.getLogger(__name__)


def format_numeric_constraint(constraint: Any, unite: str = "") -> str:
    """
    Formate une contrainte numérique (min/max/exact) en string lisible.
    Conversion de la fonction PHP format_numeric_constraint.
    
    Args:
        constraint: dict avec clés min/max/exact ou valeur simple
        unite: unité à afficher
        
    Returns:
        String formatée de la contrainte
    """
    if not constraint:
        return ""

    u = f" {unite}" if unite else ""

    if isinstance(constraint, dict):
        parts = []
        if "min" in constraint:
            parts.append(f"≥ {constraint['min']}{u}")
        if "max" in constraint:
            parts.append(f"≤ {constraint['max']}{u}")
        if "exact" in constraint:
            parts.append(f" {constraint['exact']}{u}")
        return " & ".join(parts)

    return f"{constraint}{u}"


async def run_identification(id_categorie: str, id_prompt: Optional[str] = None) -> Dict[str, Any]:
    """
    Logique principale d'identification des caractéristiques influençant le prix.
    Conversion de la logique PHP run_identification en Python.
    
    Étapes :
    1. Récupère les données de la catégorie via l'API HelloPro
    2. Récupère le prompt configuré
    3. Construit le prompt final et appelle Gemini
    4. Parse la réponse JSON
    5. Retourne le résultat structuré
    
    Args:
        id_categorie: ID de la catégorie à analyser
        id_prompt: ID du prompt (utilise la config par défaut si None)
        
    Returns:
        Dict avec 'success', 'data', 'llm_response', 'message'
    """
    start_time = time.time()
    prompt_id = id_prompt or settings.PROMPT_ID
    
    api_client = HelloProAPIClient()
    
    try:
        # =====================================================================
        # ÉTAPE 0 : Récupérer les données de la catégorie : nom catégorie
        # =====================================================================
        logger.info(f"[{id_categorie}] Récupération des données de la catégorie...")
        
        category_info = await api_client.post(
            "category",
            "info",
            "get",
            {"id_categorie": id_categorie}
        )
        nom_categorie = category_info.get("nom_rubrique", "")
        
        if not category_info or not nom_categorie:
            elapsed = time.time() - start_time
            logger.error(f"[{id_categorie}] Impossible de récupérer les données de la catégorie")
            return {
                "success": False,
                "data": None,
                "llm_response": None,
                "time_elapsed": elapsed,
                "message": f"Impossible de récupérer les données de la catégorie {id_categorie}"
            }
        
        logger.info(f"[{id_categorie}] Données catégorie récupérées avec succès")
        
        # =====================================================================
        # ÉTAPE 1 : Récupérer les données de la catégorie : Q1 + jeu caractéristiques + caractéristiques prix existant 
        # =====================================================================
        logger.info(f"[{id_categorie}] Récupération des données de la catégorie...")

        # Charger les réponses de Question 1 + caractéristiques prix existant 
        reponses_q1_carac_prix = await api_client.post(
            "prix",
            "caracteristique",
            "get",
            {"id_categorie": id_categorie}
        )

        # Charger les caractéristiques finales 
        jeu_caracteristiques = await api_client.post(
            "caracteristique",
            "final",
            "get",
            {"id_categorie": id_categorie}
        )
        # Sérialiser les données de la catégorie en JSON pour le prompt
        jeu_caracteristiques_json = json.dumps(jeu_caracteristiques, ensure_ascii=False, indent=2)
        
        if not reponses_q1_carac_prix or not jeu_caracteristiques:
            elapsed = time.time() - start_time
            logger.error(f"[{id_categorie}] Impossible de récupérer les données de la catégorie")
            return {
                "success": False,
                "data": None,
                "llm_response": None,
                "time_elapsed": elapsed,
                "message": f"Impossible de récupérer les données de la catégorie {id_categorie} Q1 : {len(reponses_q1)} Caracteristiques : {len(jeu_caracteristiques)}"
            }
        
        logger.info(f"[{id_categorie}] Données catégorie récupérées avec succès")
        


        # =====================================================================
        # ÉTAPE 2 : Récupérer le prompt
        # =====================================================================
        logger.info(f"[{id_categorie}] Récupération du prompt (id={prompt_id})...")
        
        prompt_config = await get_prompt(prompt_id)
        
        if not prompt_config:
            elapsed = time.time() - start_time
            logger.error(f"[{id_categorie}] Impossible de récupérer le prompt id={prompt_id}")
            return {
                "success": False,
                "data": None,
                "llm_response": None,
                "time_elapsed": elapsed,
                "message": f"Impossible de récupérer le prompt id={prompt_id}"
            }
        
        # Extraire le contenu du prompt
        prompt_text = prompt_config.get("contenu_prompt", "")
        logger.info(f"[{id_categorie}] Prompt récupéré : {prompt_text[:100]}...")
        
        # =====================================================================
        # ÉTAPE 3 : Initialiser Gemini
        # =====================================================================
        gemini = GeminiProvider(
            model=settings.GEMINI_MODEL_NAME
        )
        
        # =====================================================================
        # ÉTAPE 4 : Pour chaque réponse Q1, appel LLM + sauvegarde
        # =====================================================================
        results_by_reponse = []
        skipped = []
        errors = []
        
        for rep in reponses_q1_carac_prix:
            id_reponse = rep.get("id_reponse", "")
            reponse = rep.get("reponse", "")
            has_data = rep.get("has_data", False)
            caracteristiques_prix_existant = rep.get("caracteristiques_prix", [])


            if has_data and caracteristiques_prix_existant:
                logger.warning(f"[{id_categorie}] - Caracteristiques prix existantes pour la reponse {id_reponse} - {reponse}")
                skipped.append({
                    "id_reponse": id_reponse,
                    "reponse": reponse,
                })
                continue
            
            # Récupérer les caractéristiques d'équivalence pour cette réponse
            list_carac_equiv = []
            equivalences = rep.get("equivalence", [])
            if equivalences and isinstance(equivalences, list):
                for equiv in equivalences:
                    if isinstance(equiv, dict):
                        id_c = equiv.get("id_caracteristique")
                        if id_c:
                            list_carac_equiv.append(str(id_c))
                    else:
                        logger.warning(f"[{id_categorie}] Équivalence non valide pour la réponse '{reponse}' (id={id_reponse}): {equivalences}")
            
            logger.info(f"[{id_categorie}] Traitement réponse Q1: '{reponse}' (id={id_reponse})")
            
            # --- Construction du prompt avec remplacement des variables dynamiques ---
            final_prompt = prompt_text
            final_prompt = final_prompt.replace("{nom_categorie}", nom_categorie)
            final_prompt = final_prompt.replace("{reponse_question_1}", reponse)
            final_prompt = final_prompt.replace("{jeu_caracteristiques}", jeu_caracteristiques_json)
            
            logger.info(f"[{id_categorie}] Appel Gemini pour réponse '{reponse}' ({len(final_prompt)} chars)...")
            
            # --- Appel Gemini ---
            llm_result = gemini.chat(final_prompt)
            
            # Vérifier si erreur LLM
            if "error" in llm_result:
                error_msg = f"Erreur Gemini pour la réponse '{reponse}' (code {llm_result.get('code', '?')})"
                logger.error(f"[{id_categorie}] {error_msg}")
                errors.append(error_msg)
                continue
            
            llm_text = llm_result.get("message", "")
            logger.info(f"[{id_categorie}] Réponse Gemini : {llm_text}")
            
            # --- Parser la réponse JSON du LLM ---
            parsed = extract_json_from_text(llm_text)
            
            caracteristiques_prix = []
            
            if not parsed or not isinstance(parsed, dict) or not parsed.get("caracteristiques_prix"):
                error_msg = f"Réponse JSON vide ou malformée pour réponse='{reponse}' (id={id_reponse})"
                logger.error(f"[{id_categorie}] {error_msg}")
                errors.append(error_msg)
                continue
            
            # --- Ajouter les caractéristiques d'équivalence ---
            if list_carac_equiv:
                for carac_equiv in list_carac_equiv:
                    caracteristiques_prix.append(str(carac_equiv))

            # Extraire les IDs des caractéristiques prix identifiées par le LLM
            for carac_prix in parsed["caracteristiques_prix"]:                
                id_carac = carac_prix.get("id", "")
                if id_carac:
                    caracteristiques_prix.append(str(id_carac))  
            
            # --- Dédupliquer ---
            caracteristiques_prix = list(dict.fromkeys(caracteristiques_prix))
            
            # --- Sauvegarde via API ---                
            save_result = await api_client.post(
                "prix",
                "caracteristique",
                "save",
                {
                    "id_categorie": id_categorie,
                    "id_reponse": id_reponse,
                    "caracteristiques_prix": caracteristiques_prix
                }
            )
            saved_ids = save_result.get("saved_ids", [])
            if save_result is not None and len(saved_ids) > 0:
                logger.info(f"[{id_categorie}] Sauvegardé: {len(saved_ids)} caractéristiques pour réponse='{reponse}' (id={id_reponse})")
            else:
                error_msg = f"Échec sauvegarde: {len(saved_ids)} caractéristiques pour réponse='{reponse}' (id={id_reponse})"
                logger.warning(f"[{id_categorie}] Échec sauvegarde: {len(saved_ids)} caractéristiques pour réponse='{reponse}' (id={id_reponse})")
                errors.append(error_msg)
                continue
            
            results_by_reponse.append({
                "id_reponse": id_reponse,
                "reponse": reponse,
                "sous_type": parsed.get("sous_type", ""),
                "caracteristiques_prix": parsed["caracteristiques_prix"],
                "ids_saved": saved_ids,
            })
            
            logger.info(f"[{id_categorie}] Réponse '{reponse}': {len(saved_ids)} caractéristiques sauvegardées")
        
        # =====================================================================
        # ÉTAPE 5 : Construction du résultat final
        # =====================================================================
        elapsed = time.time() - start_time
        
        # Cas : aucune réponse traitée et des erreurs
        if not results_by_reponse and errors:
            return {
                "success": False,
                "data": [],
                "raw": results_by_reponse,
                "errors": errors,
                "skipped": skipped,
                "time_elapsed": elapsed,
                "message": "; ".join(errors)
            }
        
        # Cas : aucune réponse traitée et pas d'erreurs (tout déjà traité)
        if not results_by_reponse and not errors:
            return {
                "success": False,
                "data": [],
                "raw": results_by_reponse,
                "errors": errors,
                "skipped": skipped,
                "time_elapsed": elapsed,
                "message": "Toutes les réponses Q1 ont déjà été traitées. Supprimez celles que vous souhaitez relancer."
            }
        
        # Construction du message récapitulatif
        msg = f"{len(results_by_reponse)} réponse(s) traitée(s)"
        if skipped:
            msg += f", {len(skipped)} ignorée(s) (déjà traitées)"
        if errors:
            msg += f", {len(errors)} erreur(s)"
        
        logger.info(f"[{id_categorie}] Identification terminée en {elapsed}s: {msg}")
        
        return {
            "success": True,
            "data": results_by_reponse,
            "raw": results_by_reponse,
            "errors": errors,
            "skipped": skipped,
            "time_elapsed": elapsed,
            "message": msg
        }
    
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"[{id_categorie}] Erreur inattendue dans run_identification: {e}", exc_info=True)
        return {
            "success": False,
            "data": None,
            "llm_response": None,
            "time_elapsed": elapsed,
            "message": f"Erreur inattendue: {str(e)}"
        }
    
    finally:
        await api_client.close()

