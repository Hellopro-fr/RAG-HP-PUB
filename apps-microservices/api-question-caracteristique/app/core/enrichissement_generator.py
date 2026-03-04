import time
import logging
import asyncio
import re
from typing import Dict, List, Any, Optional, Tuple

from app.core.api_client import HelloProAPIClient, GeminiProvider
from app.core import utils
from app.schemas.question_caracteristique import (
    RequestProcessus,
    EnrichissementGenerationResult,
    Caracteristique,
    Question
)
from app.core.credentials import settings


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class EnrichissementGenerator:
    """Générateur d'enrichissement des caractéristiques via questions"""
    
    # ID du prompt
    PROMPT_VERIFICATION_ID = "99"
    ETAPE = "5"
    
    def __init__(self, api_client: Optional[HelloProAPIClient] = None):
        self.api_client = api_client or HelloProAPIClient()
        self.tracking_file = None
        # Mapping entre ID incrémenté (pour LLM) et ID base de données
        self.id_mapping = {}  # {id_incremente: id_base}
        self.reverse_mapping = {}  # {id_base: id_incremente}
    
    def _log(self, message: str):
        """Écrit dans le fichier de tracking et les logs"""
        if self.tracking_file:
            utils.write_log(self.tracking_file, message)
        logger.info(message)

    def _create_id_mapping(
        self, 
        caracteristiques: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], Dict[int, Any], Dict[Any, int]]:
        """
        Crée un mapping entre ID incrémenté (1, 2, 3...) et ID base de données
        Transforme les caractéristiques pour utiliser l'ID incrémenté
        
        Args:
            caracteristiques: Liste des caractéristiques avec ID base
            
        Returns:
            Tuple (caracteristiques_avec_id_incremente, id_mapping, reverse_mapping)
        """
        id_mapping = {}  # {id_incremente: id_base}
        reverse_mapping = {}  # {id_base: id_incremente}
        caracteristiques_transformed = []
        
        index = 0
        for idx, carac in enumerate(caracteristiques, 1):
            index += 1
            id_base = carac.get('id')
            
            # Créer le mapping
            id_mapping[index] = id_base
            reverse_mapping[id_base] = index
            
            # Créer une copie avec l'ID incrémenté
            carac_copy = carac.copy()
            carac_copy['id'] = index
            # carac_copy['_id_base'] = id_base  # Garder l'ID base en interne
            
            caracteristiques_transformed.append(carac_copy)
        
        self._log(f"Mapping créé: {len(id_mapping)} caractéristiques")
        self._log(f"Exemple mapping: {dict(list(id_mapping.items())[:3])}")
        
        return caracteristiques_transformed, id_mapping, reverse_mapping

    def _normalize_string(self, text: str) -> str:
        """
        Normalise une chaîne: garde uniquement lettres/chiffres Unicode et met en minuscule
        """
        return re.sub(r'[^\p{L}\p{N}]', '', text.lower())

    async def _apply_caracteristique_action(
        self,
        action: Dict[str, Any],
        id_categorie: str
    ) -> Optional[Dict[str, Any]]:
        """
        Applique une action (CREATE ou UPDATE) sur une caractéristique
        via l'API et retourne la caractéristique mise à jour avec son ID base
        
        Args:
            action: Action à appliquer (contient type, target_id, full_definition)
            id_categorie: ID de la catégorie
            
        Returns:
            Caractéristique mise à jour avec ID base, ou None si échec
        """
        type_action = action.get('action_type', '')
        new_definition = action.get('full_definition_json', {})
        
        # Fallback si les clés ne matchent pas
        if not type_action or not new_definition:
            for key, value in action.items():
                if re.search(r'.*(action|type).*', key, re.IGNORECASE):
                    type_action = value
                if re.search(r'.*(full|definition|json).*', key, re.IGNORECASE):
                    new_definition = value
        
        if not type_action or not new_definition:
            self._log("ERREUR: Action invalide (type ou définition manquante)")
            return None
        
        # CAS 1: CRÉATION
        if re.search(r'.*CREATE.*', type_action, re.IGNORECASE):
            self._log("Action: CREATE")
            
            # Créer la caractéristique via API
            result = await self.api_client.post(
                "caracteristique",
                "create",
                "save",
                {
                    "id_categorie": id_categorie,
                    "data": new_definition
                }
            )
            
            if not result:
                self._log("ERREUR: Échec de la création de caractéristique")
                return None
            
            self._log(f"Caractéristique créée avec ID base: {result.get('id')}")
            return result
        
        # CAS 2: MISE À JOUR
        elif re.search(r'.*UPDATE.*', type_action, re.IGNORECASE):
            target_id_incremente = action.get('target_characteristic_id')
            
            if not target_id_incremente:
                for key, value in action.items():
                    if re.search(r'.*target.*id.*', key, re.IGNORECASE):
                        target_id_incremente = value
                        break
            
            if not target_id_incremente:
                self._log("ERREUR: target_characteristic_id manquant pour UPDATE")
                return None
            
            # Convertir l'ID incrémenté en ID base
            target_id_base = self.id_mapping.get(int(target_id_incremente))

            if not target_id_base:
                for id_incremente, id_base in self.id_mapping.items():
                    if str(target_id_incremente).strip() == str(id_incremente).strip():
                        target_id_base = id_base
                        break
            
            if not target_id_base:
                self._log(f"ERREUR: ID incrémenté {target_id_incremente} non trouvé dans le mapping")
                return None
            
            self._log(f"Action: UPDATE (ID incrémenté: {target_id_incremente} -> ID base: {target_id_base})")
            
            # Mettre à jour la caractéristique via API
            result = await self.api_client.post(
                "caracteristique",
                "update",
                "save",
                {
                    "id_categorie": id_categorie,
                    "id_caracteristique": target_id_base,
                    "data": new_definition
                }
            )
            
            if not result:
                self._log("ERREUR: Échec de la mise à jour de caractéristique")
                return None
            
            self._log(f"Caractéristique mise à jour (ID base: {result.get('id')})")
            return result
        
        else:
            self._log(f"ERREUR: Type d'action non reconnu: {type_action}")
            return None

    async def _update_caracteristiques_list(
        self,
        caracteristiques: List[Dict[str, Any]],
        updated_carac: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Met à jour la liste des caractéristiques avec une caractéristique modifiée/créée
        
        Args:
            caracteristiques: Liste actuelle des caractéristiques
            updated_carac: Caractéristique mise à jour (avec ID base)
            
        Returns:
            Liste mise à jour
        """
        id_base = updated_carac.get('id')
        
        # Vérifier si c'est une mise à jour ou une création
        found_index = None
        for idx, carac in enumerate(caracteristiques):
            if carac.get('id') == id_base:
                found_index = idx
                break
        
        if found_index is not None:
            # Mise à jour
            caracteristiques[found_index] = updated_carac
            self._log(f"Caractéristique mise à jour dans la liste (index: {found_index})")
        else:
            # Création: ajouter à la fin
            caracteristiques.append(updated_carac)
            
            # Mettre à jour les mappings
            new_id_incremente = len(self.id_mapping) + 1
            self.id_mapping[new_id_incremente] = id_base
            self.reverse_mapping[id_base] = new_id_incremente
            
            self._log(f"Nouvelle caractéristique ajoutée (ID base: {id_base}, ID incrémenté: {new_id_incremente})")
        
        return caracteristiques

    async def _insert_questionnaire_llm(
        self,
        question_data: Dict[str, Any],
        id_categorie: str
    ) -> Dict[str, Any]:
        """
        Insère la question 1 dans la base de données
        """
        self._log("Insertion de la Question 1 dans la base")
        
        result = await self.api_client.post(
            "question",
            "question1",
            "insert",
            {
                "id_categorie": id_categorie,
                "question_data": question_data
            }
        )
        
        if not result:
            raise Exception("Échec de l'insertion Question 1")
        
        self._log(f"Question 1 insérée: {result}")
        return result

    async def verify_question(
        self,
        id_categorie: str,
        nom_rubrique: str,
        question_data: Dict[str, Any],
        caracteristiques: List[Dict[str, Any]],
        question_identifier: str,
        process_data: Dict[str, Any]
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Vérifie une question et enrichit le jeu de caractéristiques si nécessaire
        
        Args:
            id_categorie: ID de la catégorie
            nom_rubrique: Nom de la rubrique
            question_data: Données de la question
            caracteristiques: Liste actuelle des caractéristiques (avec ID base)
            question_identifier: Identifiant unique de la question
            process_data: Données du processus
            
        Returns:
            Liste mise à jour des caractéristiques, ou None si aucun changement
        """
        self._log(f"\n--- Vérification question: {question_identifier} ---")
        
        # Vérifier si déjà traité
        done_verifications = process_data.get("verification", {}).get("done", [])
        if question_identifier in done_verifications:
            self._log("Déjà traité")
            return "already_done"
        
        # Récupérer le prompt
        prompt_config = await utils.get_prompt(self.PROMPT_VERIFICATION_ID)
        
        if not prompt_config:
            self._log("ERREUR: Impossible de récupérer le prompt Vérification")
            await self.api_client.post(
                "enrichissement",
                "mail",
                "error",
                {
                    "id_categorie": id_categorie,
                    "question": question_identifier,
                    "error_message": "Impossible de récupérer le prompt",
                    "tracking_file": self.tracking_file
                }
            )
            raise Exception("Impossible de récupérer le prompt Vérification")
        
        # Créer le mapping des IDs et transformer les caractéristiques
        caracteristiques_for_llm, id_mapping, reverse_mapping = self._create_id_mapping(caracteristiques)
        
        # Sauvegarder les mappings
        self.id_mapping = id_mapping
        self.reverse_mapping = reverse_mapping

        # NETTOYAGE DES IDS POUR GEMINI
        # On crée une copie pour ne pas altérer les données originales qui contiennent les IDs BDD
        clean_question_for_llm = question_data.copy()
        if 'id' in clean_question_for_llm:
            del clean_question_for_llm['id']
        
        if 'reponses' in clean_question_for_llm:
            clean_reponses = []
            for rep in clean_question_for_llm['reponses']:
                rep_copy = rep.copy()
                if 'id' in rep_copy:
                    del rep_copy['id']
                clean_reponses.append(rep_copy)
            clean_question_for_llm['reponses'] = clean_reponses
        
        # Préparer le prompt
        json_question = utils.to_json_string(clean_question_for_llm)
        json_caracteristique = utils.to_json_string(caracteristiques_for_llm)
        
        prompt_text = prompt_config["contenu_prompt_apc"]
        prompt_text = prompt_text.replace("{CATEGORIE}", nom_rubrique)
        prompt_text = prompt_text.replace("{INFO_QUESTION_REPONSE}", json_question)
        prompt_text = prompt_text.replace("{JEU_CARACTERISTIQUE}", json_caracteristique)
        
        self._log(f"Prompt: {prompt_text[:200]}...")
        self._log(f"Nombre de caractéristiques envoyées au LLM: {len(caracteristiques_for_llm)}")
        
        # Appeler le LLM gemini
        gemini = GeminiProvider(
            model="gemini-3.1-pro-preview",
            thinking_level="high",
            max_retries=10
        )
        result = await asyncio.to_thread(gemini.chat, prompt_text)
        
        if "code" in result:
            self._log(f"ERREUR API: {result}")
            await self.api_client.post(
                "enrichissement",
                "mail",
                "error",
                {
                    "id_categorie": id_categorie,
                    "question": question_identifier,
                    "error_message": f"Erreur API: {result}",
                    "tracking_file": self.tracking_file
                }
            )
            raise Exception(f"Erreur API Gemini: {result.get('error')}")
        
        # Extraire le JSON
        response_text = result.get("message", "").strip()
        self._log(f"Réponse LLM: {response_text[:500]}...")
        
        # Vérifier si "aucun changement"
        if re.search(r'aucun([^a-zA-Z]+)changement', response_text, re.IGNORECASE):
            self._log("Aucun changement détecté") 
            return None
        
        # Extraire le JSON de vérification
        json_data = utils.extract_json_from_text(response_text)
        if not json_data:
            self._log("ERREUR: Impossible d'extraire le JSON")
            await self.api_client.post(
                "enrichissement",
                "mail",
                "error",
                {
                    "id_categorie": id_categorie,
                    "question": question_identifier,
                    "error_message": "Erreur extraction JSON",
                    "error_detail": result,
                    "tracking_file": self.tracking_file
                }
            )
            raise Exception("Impossible d'extraire le JSON de la réponse")
        
        # Vérifier schema_actions
        schema_actions = json_data.get('schema_actions', [])
        if not isinstance(schema_actions, list) or len(schema_actions) == 0:
            self._log("Aucune action à appliquer")
            return None
        
        self._log(f"Actions à appliquer: {len(schema_actions)}")
        
        # Appliquer chaque action une par une
        caracteristiques_updated = caracteristiques.copy()
        
        for idx, action in enumerate(schema_actions, 1):
            self._log(f"\n--- Application action {idx}/{len(schema_actions)} ---")
            
            # Appliquer l'action via API
            updated_carac = await self._apply_caracteristique_action(action, id_categorie)
            
            if updated_carac:
                # Mettre à jour la liste locale
                caracteristiques_updated = await self._update_caracteristiques_list(
                    caracteristiques_updated,
                    updated_carac
                )
            else:
                self._log(f"AVERTISSEMENT: Action {idx} n'a pas pu être appliquée")
        
        self._log(f"Mise à jour terminée: {len(caracteristiques_updated)} caractéristiques")
        
        return caracteristiques_updated

    async def generate_enrichissement(
        self,
        request: RequestProcessus
    ) -> EnrichissementGenerationResult:
        """
        Processus d'enrichissement des caractéristiques via les questions
        """
        id_categorie = request.id_categorie

        # Récupérer les infos de la catégorie
        category_info = await self.api_client.post(
            "category",
            "info",
            "get",
            {"id_categorie": id_categorie}
        )
        
        if not category_info:
            await self.api_client.post(
                "enrichissement",
                "mail",
                "error",
                {
                    "id_categorie": id_categorie,
                    "error_message": f"Catégorie {id_categorie} non trouvée",
                    "tracking_file": self.tracking_file
                }
            )
            raise ValueError(f"Catégorie {id_categorie} non trouvée")
                    
        nom_rubrique = category_info.get("nom_rubrique", "")
        
        # Initialiser le fichier de tracking
        self.tracking_file = utils.get_tracking_filepath(
            id_categorie, 
            prefix="enrichissement"
        )
        
        # Vérifier le stopper manuel
        if utils.check_stopper(id_categorie):
            self._log("ARRÊT MANUEL DÉTECTÉ")
            await self.api_client.post(
                "enrichissement",
                "mail",
                "error",
                {
                    "id_categorie": id_categorie,
                    "error_message": "Le processus a été arrêté manuellement",
                    "tracking_file": self.tracking_file
                }
            )
            raise Exception("Processus arrêté manuellement")
        
        self._log("=" * 50)
        self._log("Enrichissement des caractéristiques via questions")
        self._log(f"Rubrique: {id_categorie} - {nom_rubrique}")
        self._log("=" * 50)
        
        # Récupérer ou initialiser le processus
        process_data = await self.api_client.post(
            "enrichissement",
            "process",
            "get",
            {"id_categorie": id_categorie}
        ) or {}
        
        # Reset si demandé
        if request.is_reset:
            self._log("RESET DU PROCESSUS")
            await self.api_client.post(
                "enrichissement",
                "process",
                "reset",
                {"id_categorie": id_categorie}
            )
            process_data = {}
        
        # Charger les questions (déjà normalisées)
        questions_data = await self.api_client.post(
            "question",
            "all",
            "get",
            {"id_categorie": id_categorie}
        )
        
        question_1 = questions_data.get("question_1", {})
        question_2_an = questions_data.get("question_2_an", {})
        
        # Charger les caractéristiques finales (déjà normalisées avec ID base)
        caracteristiques = await self.api_client.post(
            "caracteristique",
            "final",
            "get",
            {"id_categorie": id_categorie}
        )
        
        if not question_1 or not question_2_an or not caracteristiques:
            raise Exception("Données d'entrée manquantes (questions ou caractéristiques)")

        # EXTRACTION DES IDS DEPUIS QUESTION_1
        id_question_1 = question_1.get('id')
        
        self._log(f"Question 1 chargée")
        self._log(f"Questions 2aN: {len(question_2_an)} réponses")
        self._log(f"Caractéristiques: {len(caracteristiques)} (avec ID base)")
        
        processed_count = 0
        
        # Vérifier Question 1
        result = await self.verify_question(
            id_categorie,
            nom_rubrique,
            question_1,
            caracteristiques,
            "Q1",
            process_data
        )
        
        if result == "already_done":
            self._log("Question 1 déjà vérifiée")
        elif result is not None:
            caracteristiques = result
            processed_count += 1
        
        # Marquer comme traité        
        if "done" not in process_data:
            process_data["done"] = []
        
        if "Q1" not in process_data["done"]:
            process_data["done"].append("Q1")
        
        await self.api_client.post(
            "enrichissement",
            "process",
            "update",
            {
                "id_categorie": id_categorie,
                "etape": self.ETAPE,
                "process_data": process_data
            }
        )
        
        # Récupérer les IDs des réponses Q1
        id_reponse_map = {int(rep.get('id')): rep.get('reponse') for rep in question_1.get('reponses', [])}

        # Vérifier Questions 2aN
        for id_reponse, liste_questions in question_2_an.items():
            
            # Vérifier le stopper
            if utils.check_stopper(id_categorie):
                raise Exception("Processus arrêté manuellement")
            
            # Trouver le nom  de la réponse
            nom_reponse = id_reponse_map.get(int(id_reponse))
            self._log(f"\n--- Réponse: {id_reponse} - {nom_reponse} ---")
            
            if not nom_reponse:
                # Recherche nom_reponse dans id_reponse_map
                for id_base, nom_base in id_reponse_map.items():
                    if str(id_reponse).strip() == str(id_base).strip():
                        nom_reponse = nom_base
                        break
            
            if not nom_reponse:
                self._log(f"ERREUR: réponse non trouvé pour {id_reponse}")
                continue

            
            # Vérifier chaque question suivante
            for question_suivante in liste_questions:
                # Vérifier le stopper
                if utils.check_stopper(id_categorie):
                    raise Exception("Processus arrêté manuellement")
                
                id_question_suivante = question_suivante.get('id', '')
                
                question_unique_id = f"{id_reponse}_{id_question_suivante}"
                
                result = await self.verify_question(
                    id_categorie,
                    nom_rubrique,
                    question_suivante,
                    caracteristiques,
                    question_unique_id,
                    process_data
                )
                
                if result == "already_done":
                    self._log(f"Question {question_unique_id} déjà vérifiée")
                elif result is not None:
                    caracteristiques = result
                    processed_count += 1
                
                # Marquer comme traité
                if question_unique_id not in process_data["done"]:
                    process_data["done"].append(question_unique_id)
                
                await self.api_client.post(
                    "enrichissement",
                    "process",
                    "update",
                    {
                        "id_categorie": id_categorie,
                        "etape": self.ETAPE,
                        "process_data": process_data
                    }
                )
            
        
        self._log("\n" + "=" * 50)
        self._log("ENRICHISSEMENT TERMINÉ")
        self._log(f"Total caractéristiques finales: {len(caracteristiques)}")
        self._log("=" * 50)

        await self.api_client.post(
            "enrichissement",
            "mail",
            "success",
            {
                "id_categorie": id_categorie,
                "tracking_file": self.tracking_file,
                "total_caracteristiques": len(caracteristiques)
            }
        )
        
        return EnrichissementGenerationResult(
            id_categorie=id_categorie,
            nom_rubrique=nom_rubrique,
            total_processed=processed_count,
            status="completed"
        )
    
    async def close(self):
        """Ferme les connexions"""
        await self.api_client.close()