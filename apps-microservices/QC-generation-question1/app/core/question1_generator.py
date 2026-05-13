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


class Question1Generator:
    """Générateur de Question 1 via LLM"""
    
    # IDs des prompts
    PROMPT_QUESTION1_ID = "97"
    # PROMPT_QUESTION1_ID = "101"
    ETAPE = "1"
    GEMINI_MODEL = "gemini-3.1-pro-preview"

    # ID process
    ID_PROCESS = "30"
    
    def __init__(self, api_client: Optional[HelloProAPIClient] = None):
        self.api_client = api_client or HelloProAPIClient()
        self.llm_provider = None
        self.tracking_file = None
        self.prompt_question1 = None  # Sera chargé lors du premier traitement

    
    def _log(self, message: str):
        """Écrit dans le fichier de tracking et les logs"""
        if self.tracking_file:
            utils.write_log(self.tracking_file, message)
        logger.info(message)

    async def _load_prompts(self, id_categorie: str):
        """Charge les prompts une seule fois au début du traitement"""
        if self.prompt_question1 is None:
            self.prompt_question1 = await utils.get_prompt(self.PROMPT_QUESTION1_ID)
            if not self.prompt_question1:
                self._log("ERREUR: Impossible de charger le prompt Question 1")
                await self.api_client.post(
                    "question",
                    "mail",
                    "error",
                    {
                        "id_categorie": id_categorie,
                        "etape": self.ETAPE,
                        "error_message": "Impossible de charger le prompt Question 1",
                        "tracking_file": self.tracking_file
                    }
                )
                raise Exception("Impossible de charger le prompt Question 1")
            self._log(f"Prompt Question1 chargé (ID: {self.PROMPT_QUESTION1_ID})")


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

        # Pour Q1 normalized_type = 2 unique
        normalized_type = 2
        
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

        Entrée: dict (Q1) ou list (Q2aN)
        Sortie: [{"Numero-question": 1, "Intitule-question": "...", "Bulle-aide": {libelle, explication, astuce}, "Reponses": [...]}]
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
        fil_d_ariane: str,
        descriptif_rubrique: str,
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
        
        #récupération du prompt (copie du prompt chargé au début)
        prompt_config = self.prompt_question1.copy()

        # Préparer le prompt
        prompt_text = prompt_config["contenu_prompt"]
        prompt_text = prompt_text.replace("{CATEGORIE}", nom_rubrique)
        prompt_text = prompt_text.replace("{FIL_D_ARIANE}", fil_d_ariane)
        prompt_text = prompt_text.replace("{DESCRIPTIF_CATEGORIE}", descriptif_rubrique)
        
        self._log(f"Prompt: {prompt_text}")
        
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
            origine="qc-generation-question1",
            etat=1 if "code" not in result else 2,
            retour_erreur=str(result.get("error", "")) if "code" in result else ""
        )
        
        
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

        #VALIDATION - Vérifier que l'API a retourné des IDs
        self._log("\n--- Validation res_insert Q1 ---")
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
        Processus de génération de Question 1
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
        fil_d_ariane = category_info.get("barre_chainage", "")
        descriptif_rubrique = category_info.get("description", "")
        
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
        self._log("Génération de Question 1 via LLM")
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

        self._log(f"Process data: {process_data}")
        
        processed_count = 0

        # Générer Question 1
        res_insert = await self.generate_question1(id_categorie, nom_rubrique, fil_d_ariane, descriptif_rubrique, process_data)
        
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
