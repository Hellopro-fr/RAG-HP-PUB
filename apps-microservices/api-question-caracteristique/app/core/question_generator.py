import time
import logging
import asyncio
import re
from typing import Dict, List, Any, Optional
from pydantic import ValidationError

from app.core.api_client import HelloProAPIClient, GeminiProvider
from app.core import utils
from app.schemas.question_caracteristique import (
    RequestProcessus, 
    QuestionGenerationResult,
    Question,
    ReponseQuestion
)
from app.core.credentials import settings



logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class QuestionGenerator:
    """Générateur de questions via LLM"""
    
    # IDs des prompts
    PROMPT_QUESTION1_ID = "97"
    PROMPT_QUESTION2_ID = "98"
    
    def __init__(self, api_client: Optional[HelloProAPIClient] = None , etape: Optional[str] = None):
        self.api_client = api_client or HelloProAPIClient()
        self.llm_provider = None
        self.tracking_file = None
        self.ETAPE = etape or "1"
    
    def _log(self, message: str):
        """Écrit dans le fichier de tracking et les logs"""
        if self.tracking_file:
            utils.write_log(self.tracking_file, message)
        logger.info(message)

    def _normalize_question(self, q: Dict[str, Any], default_num: int = 1) -> Dict[str, Any]:
        numero, intitule, justification = None, None, None
        reponses = []
        
        for key, val in q.items():
            key_lower = key.lower()
            # Recherche insensitive des champs
            if "numero" in key_lower and numero is None:
                numero = val
            elif "intitule" in key_lower and intitule is None:
                intitule = val
            elif "justification" in key_lower and justification is None:
                justification = val
            elif "reponse" in key_lower:
                match = re.search(r'(\d+)', key)
                if match:
                    reponses.append((int(match.group(1)), val))
        
        # Trier les réponses par numéro
        reponses.sort(key=lambda x: x[0])
        
        return {
            "Numero-question": numero if numero is not None else default_num,
            "Intitule-question": intitule or "",
            "Justification-question": justification or "",
            "Reponses": [{"Numero-reponse": n, "Reponse": v} for n, v in reponses]
        }
    
    def _normalize_llm_response(self, json_data: Any) -> List[Dict[str, Any]]:
        """
        Normalise les résultats JSON du LLM en format uniforme.
        
        Entrée: dict (Q1) ou list (Q2aN)
        Sortie: [{"Numero-question": 1, "Intitule-question": "...", "Justification-question": "...", "Reponses": [...]}]
        """
        
        # Traiter dict (Q1) ou list (Q2aN)
        if isinstance(json_data, dict):
            return [self._normalize_question(json_data, 1)]
        elif isinstance(json_data, list):
            return [self._normalize_question(q, i) for i, q in enumerate(json_data, 1) if isinstance(q, dict)]
        return json_data

    def _validate_questions(
        self, 
        data: Union[Dict[str, Any], List[Dict[str, Any]]], 
        source: str = "données",
        strict: bool = False
    ) -> Union[Question, List[Question]]:
        """
        Valide une ou plusieurs questions avec le schéma Pydantic
        
        Args:
            data: Dict (1 question) ou List[Dict] (plusieurs questions)
            source: Nom de la source pour les logs (ex: "Question1", "Question2aN")
            strict: Si True, raise Exception dès qu'une question est invalide
            
        Returns:
            Question validée ou List[Question] validées
            
        Raises:
            Exception: Si strict=True et qu'une question est invalide
        """
        # Cas 1: Une seule question (Dict)
        if isinstance(data, dict):
            try:
                question = Question(**data)
                self._log(f"{source} validé")
                return question
            except ValidationError as e:
                error_msg = f"{source} invalide"
                self._log(error_msg)
                for error in e.errors():
                    self._log(f"  - {error['loc']}: {error['msg']}")
                
                if strict:
                    raise Exception(f"{error_msg}: {e}")
                return None
        
        # Cas 2: Liste de questions (List[Dict])
        elif isinstance(data, list):
            validated = []
            total = len(data)
            
            for idx, q_data in enumerate(data, 1):
                try:
                    question = Question(**q_data)
                    validated.append(question)
                    self._log(f"Question {idx}/{total} de {source} validée")
                except ValidationError as e:
                    error_msg = f"Question {idx}/{total} de {source} invalide"
                    self._log(error_msg)
                    for error in e.errors():
                        self._log(f"  - {error['loc']}: {error['msg']}")
                    
                    if strict:
                        raise Exception(f"{error_msg}: {e}")
                    continue
            
            # Si strict et aucune question validée
            if strict and not validated:
                raise Exception(f"Aucune question valide dans {source}")
            
            self._log(f"{source}: {len(validated)}/{total} questions validées")
            return validated
        
        else:
            raise TypeError(f"Type non supporté: {type(data)}")
    
    
    async def generate_question1(
        self, 
        id_categorie: str, 
        nom_rubrique: str,
        process_data: Dict[str, Any]
    ) -> Optional[str]:
        """
        Génère la question initiale (Question 1)        
        """
        self._log("\n" + "=" * 50)
        self._log("GÉNÉRATION QUESTION 1")
        self._log("=" * 50)
        
        # Vérifier si déjà généré
        done_responses = process_data.get("done", [])
        if "Q1" in done_responses:
            self._log("Déjà traité")
            return "already_done"
        
        #récupération du prompt
        prompt_config = await utils.get_prompt(self.PROMPT_QUESTION1_ID)
        
        if not prompt_config:
            self._log("ERREUR: Impossible de récupérer le prompt Question 1")
            await self.api_client.post(
                "question",
                "mail",
                "error",
                {
                    "id_categorie": id_categorie,
                    "etape": self.ETAPE,
                    "error_message": "Impossible de récupérer le prompt",
                    "tracking_file": self.tracking_file
                }
            )
            raise Exception("Impossible de récupérer le prompt Question 1")
        
        # Préparer le prompt
        prompt_text = prompt_config["contenu_prompt"]
        prompt_text = prompt_text.replace("{CATEGORIE}", nom_rubrique)
        
        self._log(f"Prompt: {prompt_text[:200]}...")
        
        # Appeler le LLM gemini
        gemini = GeminiProvider(
            model="gemini-3.1-pro-preview",
            thinking_level="high",
            max_retries=10
        )
        result = await asyncio.to_thread(gemini.chat, prompt_text)
        
        # Si "code" existe dans result, c'est une erreur
        if "code" in result:
            self._log(f"ERREUR API: {result}")
            await self.api_client.post(
                "question",
                "mail",
                "error",
                {
                    "id_categorie": id_categorie,
                    "etape": self.ETAPE,
                    "error_message": f"Erreur API: {result}",
                    "tracking_file": self.tracking_file
                }
            )
            raise Exception(f"Erreur API Gemini: {result.get('error')}")
        
        # Extraire le JSON
        response_text = result.get("message", "")
        self._log(f"Réponse LLM: {response_text[:500]}...")
        
        json_data = utils.extract_json_from_text(response_text)
        if not json_data:
            self._log("ERREUR: Impossible d'extraire le JSON")
            await self.api_client.post(
                "question",
                "mail",
                "error",
                {
                    "id_categorie": id_categorie,
                    "etape": self.ETAPE,
                    "error_message": "Erreur extraction JSON",                    
                    "error_detail": result,
                    "tracking_file": self.tracking_file
                }
            )
            raise Exception("Impossible d'extraire le JSON de la réponse")
        
        # Sauvegarder le résultat        
        res_insert = await self.api_client.post(
            "question",
            "question1",
            "save",
            {
                "id_categorie": id_categorie,
                "etape": self.ETAPE,
                "data": self._normalize_llm_response(json_data)
            }
        )

        if not res_insert:
            raise Exception("Échec de la sauvegarde Question 1")

        self._log(f"Résultat sauvegardé: {res_insert}")

        #VALIDATION 
        self._log("\n--- Validation res_insert Q1 ---")
        self._validate_questions(res_insert, source="Insertion Q1", strict=True)

        return res_insert
        
    
    async def generate_question2(
        self,
        id_categorie: str,
        nom_rubrique: str,
        reponse_id: str,
        response_value: str,
        process_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Génère les questions 2 à n
        """
        self._log(f"\n--- Génération question 2 à n: {reponse_id} {response_value} ---")
        
        category_response = f"{nom_rubrique} {response_value}"
        
        # Vérifier si déjà traité
        done_responses = process_data.get("done", [])
        if reponse_id in done_responses:
            self._log("Déjà traité, passage au suivant")
            return "already_done"
        
        # Récupérer le prompt
        prompt_config = await utils.get_prompt(self.PROMPT_QUESTION2_ID)        
        
        if not prompt_config:
            self._log("ERREUR: Impossible de récupérer le prompt Question 2")
            await self.api_client.post(
                "question",
                "mail",
                "error",
                {
                    "id_categorie": id_categorie,
                    "etape": self.ETAPE,
                    "reponse_id": reponse_id,
                    "error_message": "Impossible de récupérer le prompt",
                    "tracking_file": self.tracking_file
                }
            )
            raise Exception(f"Impossible de récupérer le prompt Question 2 pour {category_response}")
        
        # Préparer le prompt
        prompt_text = prompt_config["contenu_prompt"]
        prompt_text = prompt_text.replace("{CATEGORIE_REPONSE}", category_response)
        
        self._log(f"Prompt: {prompt_text[:200]}...")
        
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
                "question",
                "mail",
                "error",
                {
                    "id_categorie": id_categorie,
                    "etape": self.ETAPE,
                    "reponse_id": reponse_id,
                    "error_message": f"Erreur API: {result}",
                    "tracking_file": self.tracking_file
                }
            )
            raise Exception(f"Erreur API Gemini pour réponse {category_response}: {result.get('error')}")
        
        # Extraire le JSON
        response_text = result.get("message", "")
        self._log(f"Réponse LLM: {response_text[:500]}...")
        
        json_data = utils.extract_json_from_text(response_text)
        
        if not json_data:
            self._log("ERREUR: Impossible d'extraire le JSON")
            await self.api_client.post(
                "question",
                "mail",
                "error",
                {
                    "id_categorie": id_categorie,
                    "etape": self.ETAPE,
                    "reponse_id": reponse_id,
                    "error_message": "Erreur extraction JSON",
                    "error_detail": result,
                    "tracking_file": self.tracking_file
                }
            )
            raise Exception(f"Impossible d'extraire le JSON pour réponse {category_response}")
        
        # Sauvegarder le résultat        
        res_insert = await self.api_client.post(
            "question",
            "question2aN",
            "save",
            {
                "id_categorie": id_categorie,
                "etape": self.ETAPE,
                "id_reponse_parent": reponse_id,
                "data": self._normalize_llm_response(json_data)
            }
        )

        if not res_insert:
            raise Exception(f"Échec de la sauvegarde Question 2aN pour {category_response}")

        self._log(f"Résultat sauvegardé: {res_insert}")

        #VALIDATION
        self._log("\n--- Validation res_insert Q2aN ---")
        self._validate_questions(res_insert, source="Insertion Q2aN", strict=True)

        return res_insert
    
    async def generate_all_questions(
        self,
        request: RequestProcessus
    ) -> QuestionGenerationResult:
        """
        Processus de génération de questions
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
                "question",
                "mail",
                "error",
                {
                    "id_categorie": id_categorie,
                    "etape": self.ETAPE,
                    "error_message": f"Catégorie {id_categorie} non trouvée",
                    "tracking_file": self.tracking_file
                }
            )
            raise ValueError(f"Catégorie {id_categorie} non trouvée")
                    
        nom_rubrique = category_info.get("nom_rubrique", "")
        
        # Initialiser le fichier de tracking
        self.tracking_file = utils.get_tracking_filepath(id_categorie)
        
        # Vérifier le stopper manuel
        if utils.check_stopper(id_categorie):
            self._log("ARRÊT MANUEL DÉTECTÉ")
            await self.api_client.post(
                "question",
                "mail",
                "error",
                {
                    "id_categorie": id_categorie,
                    "etape": self.ETAPE,
                    "error_message": "Le processus a été arrêté manuellement",
                    "tracking_file": self.tracking_file
                }
            )
            raise Exception("Processus arrêté manuellement")
        
        
        self._log("=" * 50)
        self._log("Génération de questions via LLM")
        self._log(f"Rubrique: {id_categorie} - {nom_rubrique}")
        self._log("=" * 50)
        
        # Récupérer ou initialiser le processus
        process_data = await self.api_client.post(
            "question",
            "process",
            "get",
            {"etape": self.ETAPE, "id_categorie": id_categorie}
        ) or {}
        
        # Reset si demandé
        if request.is_reset:
            self._log("RESET DU PROCESSUS")
            await self.api_client.post(
                "question",
                "process",
                "reset",
                {"etape": self.ETAPE, "id_categorie": id_categorie}
            )
            process_data = {}
        
        processed_count = 0

        # Générer Question 1
        if self.ETAPE == "1":
            res_insert = await self.generate_question1(id_categorie, nom_rubrique, process_data)
            
            if res_insert == "already_done":
                self._log("Question 1 déjà générée")
            elif not res_insert:
                raise Exception("Erreur lors de la génération de Question 1")
            else:
                # Mettre à jour le processus
                if "done" not in process_data:
                    process_data["done"] = []
                process_data["done"].append("Q1")
                
                await self.api_client.post(
                    "question",
                    "process",
                    "update",
                    {
                        "id_categorie": id_categorie,
                        "etape": self.ETAPE,
                        "process_data": process_data
                    }
                )
                
                processed_count += 1
        
        # Générer Question 2 pour chaque réponse
        if self.ETAPE == "2":

            # Charger les réponses de Question 1
            q1_data = await self.api_client.post(
                "question",
                "question1",
                "get",
                {"id_categorie": id_categorie}
            ) 

            # VALIDATION STRICTE
            self._log("\n--- Validation q1 récupérées ---")
            validated_q1 = self._validate_questions(q1_data, source="q1_data", strict=True)
            
            # Utiliser les données validées
            q1_data = validated_q1.dict()
            
            # Accès sécurisé aux réponses
            reponses = q1_data.get("reponses", {})

            # Vérifier que q1_data et reponses existent
            if not q1_data or not reponses:
                self._log("ERREUR: Impossible de récupérer les données Question 1")
                await self.api_client.post(
                    "question",
                    "mail",
                    "error",
                    {
                        "id_categorie": id_categorie,
                        "etape": self.ETAPE,
                        "error_message": "Impossible de récupérer les données Question 1",
                        "tracking_file": self.tracking_file
                    }
                )
                raise Exception("Impossible de récupérer les données Question 1") 
            
            for key, response_data in reponses.items():

                # Vérifier le stopper à chaque itération
                if utils.check_stopper(id_categorie):
                    await self.api_client.post(
                        "question",
                        "mail",
                        "error",
                        {
                            "id_categorie": id_categorie,
                            "etape": self.ETAPE,
                            "error_message": "Le processus a été arrêté manuellement",
                            "tracking_file": self.tracking_file
                        }
                    )
                    raise Exception("Processus arrêté manuellement")

                # Récupérer les valeurs
                response_value = response_data.get("value", response_data.get("intitule", ""))
                reponse_id = response_data.get("id", key)
                

                q2_data = await self.generate_question2(
                    id_categorie,
                    nom_rubrique,
                    reponse_id,
                    response_value,
                    process_data
                )

                # Gérer le cas "déjà traité"
                if q2_data == "already_done":
                    self._log(f"Réponse {reponse_id} déjà traitée")
                    continue

                if not q2_data:
                    self._log(f"Erreur lors de la génération de Question 2 pour la réponse {reponse_id}")
                    raise Exception("Erreur lors de la génération de Question 2")
                
                
                # Marquer comme traité
                if "done" not in process_data:
                    process_data["done"] = []
                process_data["done"].append(reponse_id)
                
                await self.api_client.post(
                    "question",
                    "process",
                    "update",
                    {
                        "id_categorie": id_categorie,
                        "etape": self.ETAPE,
                        "process_data": process_data
                    }
                )
                
                processed_count += 1
                self._log(f"Progression: {processed_count}/{len(responses)}")

        
        self._log("\n" + "=" * 50)
        self._log("GÉNÉRATION TERMINÉE")
        self._log("=" * 50)

        await self.api_client.post(
            "question",
            "mail",
            "success",
            {
                "id_categorie": id_categorie,
                "etape": self.ETAPE,
                "tracking_file": self.tracking_file
            }
        )
        
        return QuestionGenerationResult(
            id_categorie=id_categorie,
            nom_rubrique=nom_rubrique,
            total_processed=processed_count,
            status="completed"
        )
    
    async def close(self):
        """Ferme les connexions"""
        await self.api_client.close()