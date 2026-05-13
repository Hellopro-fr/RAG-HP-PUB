import time
import logging
import asyncio
import re
from typing import Dict, List, Any, Optional, Union
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


class Question2aNGenerator:
    """Générateur de Questions 2 à N via LLM"""
    
    # IDs des prompts
    PROMPT_QUESTION2_ID = "98"
    # PROMPT_QUESTION2_ID = "102"
    ETAPE = "2"
    GEMINI_MODEL = "gemini-3.1-pro-preview"

    # ID process
    ID_PROCESS = "30"
    
    def __init__(self, api_client: Optional[HelloProAPIClient] = None):
        self.api_client = api_client or HelloProAPIClient()
        self.llm_provider = None
        self.tracking_file = None
        self.prompt_question2 = None  # Sera chargé lors du premier traitement
    
    def _log(self, message: str):
        """Écrit dans le fichier de tracking et les logs"""
        if self.tracking_file:
            utils.write_log(self.tracking_file, message)
        logger.info(message)

    async def _load_prompts(self, id_categorie: str):
        """Charge les prompts une seule fois au début du traitement"""
        if self.prompt_question2 is None:
            self.prompt_question2 = await utils.get_prompt(self.PROMPT_QUESTION2_ID)
            if not self.prompt_question2:
                self._log("ERREUR: Impossible de charger le prompt Question 2")
                await self.api_client.post(
                    "question",
                    "mail",
                    "error",
                    {
                        "id_categorie": id_categorie,
                        "etape": self.ETAPE,
                        "error_message": "Impossible de charger le prompt Question 2",
                        "tracking_file": self.tracking_file
                    }
                )
                raise Exception("Impossible de charger le prompt Question 2")
            self._log(f"Prompt Question2 chargé (ID: {self.PROMPT_QUESTION2_ID})")


    def _normalize_bulle_aide(self, raw: Any) -> Dict[str, Any]:
        """
        Normalise la bulle d'aide LLM vers la structure attendue par le PHP:
        {"libelle": str, "explication": List[str], "astuce": str}
        - Accepte dict (nouveau format) ou string (ancien format -> injectée comme explication unique)
        - Garantit que "explication" est toujours une liste de strings
        """
        if isinstance(raw, dict):
            explication = raw.get("explication", [])
            if isinstance(explication, str):
                explication = [explication]
            elif not isinstance(explication, list):
                explication = []
            return {
                "libelle": str(raw.get("libelle", "") or ""),
                "explication": [str(e) for e in explication],
                "astuce": str(raw.get("astuce", "") or ""),
            }
        if isinstance(raw, str) and raw.strip():
            return {"libelle": "", "explication": [raw], "astuce": ""}
        return {"libelle": "", "explication": [], "astuce": ""}

    def _normalize_question(self, q: Dict[str, Any], default_num: int = 1) -> Dict[str, Any]:
        numero, intitule, bulle_aide, type_question = None, None, None, None
        reponses = []

        for key, val in q.items():
            key_lower = key.lower()
            # Recherche insensitive des champs
            if "numero" in key_lower and numero is None:
                numero = val
            elif "intitule" in key_lower and intitule is None:
                intitule = val
            elif "bulle" in key_lower and bulle_aide is None:
                bulle_aide = val
            elif "justification" in key_lower and bulle_aide is None:
                # Rétrocompat: ancien format texte brut -> sera encapsulé en explication
                bulle_aide = val
            elif "type" in key_lower and type_question is None:
                type_question = val
            elif "reponse" in key_lower:
                # Cas 1: Liste d'objets avec 'numero' et 'reponse'
                if isinstance(val, list):
                    reponses = [(int(i['numero']), i['reponse']) for i in val]
                # Cas 2: Dictionnaire {numero: reponse}
                elif isinstance(val, dict):
                    for k, v in val.items():
                        try:
                            num = int(k)
                            reponses.append((num, v))
                        except (ValueError, TypeError):
                            # Si la clé n'est pas convertible en int, on l'ignore
                            pass
                # Cas 3: String avec numéro dans la clé (ex: "reponse1", "Reponse-2")
                else:
                    match = re.search(r'(\d+)', key)
                    if match:
                        reponses.append((int(match.group(1)), val))
        
        # Trier les réponses par numéro
        reponses.sort(key=lambda x: x[0])

        # Normaliser type_question
        normalized_type = 0
        if type_question is not None:
            if isinstance(type_question, int):
                normalized_type = type_question
            elif isinstance(type_question, str):
                # Chercher un chiffre dans le texte (ex: "Type = 1", "type=2", "choix 1")
                match = re.search(r'(\d+)', type_question)
                if match:
                    normalized_type = int(match.group(1))
        
        
        return {
            "Numero-question": numero if numero is not None else default_num,
            "Intitule-question": intitule or "",
            "Bulle-aide": self._normalize_bulle_aide(bulle_aide),
            "Type-question": normalized_type,
            "Reponses": [{"Numero-reponse": n, "Reponse": v} for n, v in reponses]
        }

    def _normalize_llm_response(self, json_data: Any) -> List[Dict[str, Any]]:
        """
        Normalise les résultats JSON du LLM en format uniforme.
        Sortie: [{"Numero-question", "Intitule-question", "Bulle-aide": {libelle, explication, astuce}, "Type-question", "Reponses"}]
        """
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
        """
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
            
            if strict and not validated:
                raise Exception(f"Aucune question valide dans {source}")
            
            self._log(f"{source}: {len(validated)}/{total} questions validées")
            return validated
        
        else:
            raise TypeError(f"Type non supporté: {type(data)}")
    
    
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
        if f"R{reponse_id}" in done_responses:
            self._log("Déjà traité, passage au suivant")
            return "already_done"
        
        # Récupérer le prompt (copie du prompt chargé au début)
        prompt_config = self.prompt_question2.copy()

        
        # Préparer le prompt
        prompt_text = prompt_config["contenu_prompt"]
        prompt_text = prompt_text.replace("{CATEGORIE_REPONSE}", category_response)
        
        self._log(f"Prompt: {prompt_text[:200]}...")
        
        # Appeler le LLM gemini
        gemini = GeminiProvider(
            model=self.GEMINI_MODEL,
            thinking_level="high",
            max_retries=10
        )
        result = await asyncio.to_thread(gemini.chat, prompt_text)
        
        # Enregistrer l'utilisation LLM (coûts et tokens)        
        usage_metadata = result.get("api_response", {}).get("usage_metadata", {})
        await self.api_client.log_llm_usage(
            type_ia=3,  # Gemini
            model=self.GEMINI_MODEL,
            input_token=usage_metadata.get("prompt_token_count", 0),
            output_token=usage_metadata.get("candidates_token_count", 0) + usage_metadata.get("thoughtsTokenCount", 0),
            id_process=self.ID_PROCESS,
            origine="qc-generation-question2aN",
            etat=1 if "code" not in result else 2,
            retour_erreur=str(result.get("error", "")) if "code" in result else ""
        )
        
        
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
        self._log(f"Réponse LLM: {response_text}...")
        
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
        id_questions = res_insert.get("id_question", [])
        if id_questions:
            self._log(f"✅ Question(s) créée(s) avec ID(s): {id_questions}")
        else:
            self._log("⚠️ Aucun ID de question retourné par l'API")

        return res_insert
    
    async def generate_all_questions(
        self,
        request: RequestProcessus
    ) -> QuestionGenerationResult:
        """
        Processus de génération de Questions 2 à N
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
        self._log("Génération de Questions 2 à N via LLM")
        self._log(f"Rubrique: {id_categorie} - {nom_rubrique}")
        self._log(f"Requête: {request}")
        self._log("=" * 50)
        
        # Charger le prompt une seule fois au début
        await self._load_prompts(id_categorie)
        
        # Récupérer ou initialiser le processus
        process_data = await self.api_client.post(
            "question",
            "process",
            "get",
            {"etape": self.ETAPE, "id_categorie": id_categorie}
        ) or {}
        
        # verification si on peut commencer le processus
        can_start = process_data.get("can_start", False)
        if not can_start:
            self._log("Processus peut pas commencer")
            await self.api_client.post(
                "question",
                "mail",
                "error",
                {
                    "id_categorie": id_categorie,
                    "etape": self.ETAPE,
                    "error_message": f"Processus peut pas commencer",
                    "tracking_file": self.tracking_file
                }
            )
            raise Exception("Processus peut pas commencer")
            
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

        self._log(f"Process data: {process_data}")

        # Charger les réponses de Question 1
        q1_data = await self.api_client.post(
            "question",
            "question1",
            "get",
            {"id_categorie": id_categorie}
        ) 

        # VALIDATION STRICTE
        self._log(f"\n--- Validation q1 récupérées ---")
        validated_q1 = self._validate_questions(q1_data, source="q1_data", strict=True)
        
        
        # Utiliser les données validées
        q1_data = validated_q1.dict()
        self._log(f"\n--- Q1 récupérées : \n {q1_data} ---")

        # Accès sécurisé aux réponses
        reponses = q1_data.get("reponses", [])

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
        
        for response_data in reponses:
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
            response_value = response_data.get("reponse", response_data.get("intitule", ""))
            reponse_id = response_data.get("id_reponse", "")
            self._log(f"\n--- Response récupérées : \n {reponse_id} - {response_value} ---")

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
            process_data["done"].append(f"R{reponse_id}")
            
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
            self._log(f"Progression: {processed_count}/{len(reponses)}")

        
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
