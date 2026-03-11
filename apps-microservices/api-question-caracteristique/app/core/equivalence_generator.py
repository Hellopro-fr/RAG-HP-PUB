import time
import logging
import asyncio
import re
from typing import Dict, List, Any, Optional

from app.core.api_client import HelloProAPIClient, GeminiProvider
from app.core import utils
from app.schemas.question_caracteristique import (
    RequestProcessus,
    EquivalenceGenerationResult
)
from app.core.credentials import settings


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class EquivalenceGenerator:
    """Générateur d'équivalences entre réponses et caractéristiques"""
    
    # ID du prompt
    PROMPT_EQUIVALENCE_ID = "101"
    ETAPE = "7"
    
    def __init__(self, api_client: Optional[HelloProAPIClient] = None):
        self.api_client = api_client or HelloProAPIClient()
        self.tracking_file = None
    
    def _log(self, message: str):
        """Écrit dans le fichier de tracking et les logs"""
        if self.tracking_file:
            utils.write_log(self.tracking_file, message)
        logger.info(message)
    
    def _normalize_string(self, text: str) -> str:
        """
        Normalise une chaîne: garde uniquement lettres/chiffres Unicode et met en minuscule
        """
        return re.sub(r'[^\p{L}\p{N}]', '', text.lower())

    def _create_json_question_prompt(
        self,
        question_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Transforme les données de question pour le prompt
        
        Args:
            question_data: Données normalisées de la question
            
        Returns:
            Dict avec json_question et corres_reponse
        """
        data_final = {
            # "numero-question": question_data.get("id", ""),
            "intitule-question": question_data.get("intitule", ""),
            "justification-question": question_data.get("justification", ""),
        }
        
        corres_reponse = {}
        reponses_possibles = question_data.get("reponses", [])
        
        index = 0
        for reponse in reponses_possibles:
            index += 1
            num_reponse = str(reponse.get("id", "")).strip()
            valeur_reponse = reponse.get("reponse", "")
            
            key = f"reponse-{index}"
            data_final[key] = valeur_reponse
            corres_reponse[num_reponse] = key
        
        return {
            "json_question": utils.to_json_string(data_final),
            "corres_reponse": corres_reponse
        }

    def _clean_jeu_caracteristique(
        self,
        jeu_caracteristique: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Nettoie le jeu de caractéristiques en enlevant micro-explication et autres-formulations
        
        Args:
            jeu_caracteristique: Jeu de caractéristiques à nettoyer
            
        Returns:
            Jeu de caractéristiques nettoyé
        """
        jeu_carac_clean = []
        for carac in jeu_caracteristique:
            carac_copy = carac.copy()
            if "valeurs" in carac_copy:
                valeurs_clean = []
                for valeur in carac_copy["valeurs"]:
                    valeur_copy = valeur.copy()
                    valeur_copy.pop("micro-explication", None)
                    valeur_copy.pop("autres-formulations", None)
                    valeurs_clean.append(valeur_copy)
                carac_copy["valeurs"] = valeurs_clean
            jeu_carac_clean.append(carac_copy)
        return jeu_carac_clean

    async def _generate_equivalence(
        self,
        id_categorie: str,
        nom_rubrique: str,
        question_data: Dict[str, Any],
        jeu_caracteristique: List[Dict[str, Any]],
        question_identifier: str,
        process_data: Dict[str, Any],
        use_transform: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Génère les équivalences pour une question (factorisée)
        
        Args:
            id_categorie: ID de la catégorie
            nom_rubrique: Nom de la rubrique
            question_data: Données de la question
            jeu_caracteristique: Jeu de caractéristiques
            question_identifier: Identifiant unique de la question (ex: "Q1", "123_Q2")
            process_data: Données du processus
            use_transform: Si True, transforme pour créer mapping (toujours True maintenant)
            
        Returns:
            Résultat des équivalences ou "already_done"
        """
        self._log(f"\n--- Génération équivalences: {question_identifier} ---")
        
        # Vérifier si déjà traité
        done_equivalences = process_data.get("done", [])
        if question_identifier in done_equivalences:
            self._log("Déjà traité")
            return "already_done"
        
        # Récupérer le prompt
        prompt_config = await utils.get_prompt(self.PROMPT_EQUIVALENCE_ID)
        
        if not prompt_config:
            self._log("ERREUR: Impossible de récupérer le prompt Équivalence")
            await self.api_client.post(
                "equivalence",
                "mail",
                "error",
                {
                    "id_categorie": id_categorie,
                    "error_message": "Impossible de récupérer le prompt",
                    "tracking_file": self.tracking_file
                }
            )
            raise Exception("Impossible de récupérer le prompt Équivalence")
        
        # Préparer le jeu de caractéristiques (nettoyer micro-explication, etc.)
        jeu_carac_clean = self._clean_jeu_caracteristique(jeu_caracteristique)
        
        # Préparer le prompt
        corres_reponse = None
        if use_transform:
            #  transformer la question
            json_prompt_data = self._create_json_question_prompt(question_data)
            json_question = json_prompt_data["json_question"]
            corres_reponse = json_prompt_data["corres_reponse"]
        else:
            # utiliser directement
            json_question = utils.to_json_string(question_data)
        
        json_caracteristique = utils.to_json_string(jeu_carac_clean)
        
        prompt_text = prompt_config["contenu_prompt"]
        prompt_text = prompt_text.replace("{CATEGORIE}", nom_rubrique)
        prompt_text = prompt_text.replace("{INFO_QUESTION_REPONSE}", json_question)
        prompt_text = prompt_text.replace("{JEU_CARACTERISTIQUE}", json_caracteristique)
        
        self._log(f"Prompt: {prompt_text[:200]}...")
        
        # Appeler le LLM Gemini
        gemini = GeminiProvider(
            model="gemini-3.1-pro-preview",
            thinking_level="high",
            max_retries=10
        )
        result = await asyncio.to_thread(gemini.chat, prompt_text)
        
        if "code" in result:
            self._log(f"ERREUR API: {result}")
            await self.api_client.post(
                "equivalence",
                "mail",
                "error",
                {
                    "id_categorie": id_categorie,
                    "error_message": f"Erreur API: {result}",
                    "tracking_file": self.tracking_file
                }
            )
            raise Exception(f"Erreur API Gemini: {result.get('error')}")
        
        # Extraire le JSON
        response_text = result.get("message", "").strip()
        self._log(f"Réponse LLM: {response_text[:500]}...")
        
        json_data = utils.extract_json_from_text(response_text)
        if not json_data:
            self._log("ERREUR: Impossible d'extraire le JSON")
            await self.api_client.post(
                "equivalence",
                "mail",
                "error",
                {
                    "id_categorie": id_categorie,
                    "error_message": "Erreur extraction JSON",
                    "error_detail": result,
                    "tracking_file": self.tracking_file
                }
            )
            raise Exception("Impossible d'extraire le JSON de la réponse")
        
        self._log(f"Équivalences extraites: {len(json_data)} réponses")
        
        # Reverse mapping: transformer les clés "reponse-1", "reponse-2", etc. 
        # en vrais IDs de réponses à partir de corres_reponse
        if corres_reponse:
            equivalences_mapped = {}
            for key, value in json_data.items():
                # Récupérer le vrai ID de réponse à partir de la clé "reponse-X"
                real_id = corres_reponse.get(key)

                if not real_id:
                    # Recherche key dans corres_reponse
                    for key_mapped, id_reponse in corres_reponse.items():
                        if self._normalize_string(key) == self._normalize_string(key_mapped):
                            real_id = id_reponse
                            break

                if real_id:
                    equivalences_mapped[real_id] = value
                else:
                    # Si pas de mapping trouvé, garder la clé originale
                    equivalences_mapped[key] = value
            
            self._log(f"Reverse mapping appliqué: {list(equivalences_mapped.keys())}")
            return equivalences_mapped
        
        # Si pas de corres_reponse, retourner json_data tel quel
        return json_data
    
    async def generate_all_equivalences(
        self,
        request: RequestProcessus
    ) -> EquivalenceGenerationResult:
        """
        Processus complet de génération des équivalences
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
                "equivalence",
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
            prefix="equivalence"
        )
        
        # Vérifier le stopper manuel
        if utils.check_stopper(id_categorie):
            self._log("ARRÊT MANUEL DÉTECTÉ")
            await self.api_client.post(
                "equivalence",
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
        self._log("Génération des équivalences Question/Caractéristique")
        self._log(f"Rubrique: {id_categorie} - {nom_rubrique}")
        self._log("=" * 50)
        
        # Récupérer ou initialiser le processus
        process_data = await self.api_client.post(
            "equivalence",
            "process",
            "get",
            {"id_categorie": id_categorie}
        ) or {}
        
        # Reset si demandé
        if request.is_reset:
            self._log("RESET DU PROCESSUS")
            await self.api_client.post(
                "equivalence",
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
        
        # Charger le jeu de caractéristiques final enrichi
        jeu_caracteristique = await self.api_client.post(
            "caracteristique",
            "final_enrichi",
            "get",
            {"id_categorie": id_categorie}
        )
        
        if not question_1 or not question_2_an or not jeu_caracteristique:
            raise Exception("Données d'entrée manquantes (questions ou caractéristiques)")
        
        self._log(f"Question 1 chargée")
        self._log(f"Questions 2aN: {len(question_2_an)} réponses")
        self._log(f"Jeu caractéristiques: {len(jeu_caracteristique)}")
        
        processed_count = 0
        
        # Initialiser done
        if "done" not in process_data:
            process_data["done"] = []
        
        # ========== TRAITER QUESTION 1 ==========
        id_question_1 = question_1.get('id')
        question_id = f"Q1_{id_question_1}"
        result_q1 = await self._generate_equivalence(
            id_categorie=id_categorie,
            nom_rubrique=nom_rubrique,
            question_data=question_1,
            jeu_caracteristique=jeu_caracteristique,
            question_identifier=question_id,
            process_data=process_data,
            use_transform=True 
        )
        
        if result_q1 == "already_done":
            self._log("Question 1 déjà traitée")
        elif result_q1:
            # Sauvegarder les équivalences Q1 (result_q1 contient directement les équivalences mappées)
            await self.api_client.post(
                "equivalence",
                "question1",
                "save",
                {
                    "id_categorie": id_categorie,
                    "id_question": id_question_1,
                    "equivalences": result_q1
                }
            )
            processed_count += 1
        
        # Marquer Q1 comme traité
        if "Q1" not in process_data["done"]:
            process_data["done"].append("Q1")
        
        await self.api_client.post(
            "equivalence",
            "process",
            "update",
            {
                "id_categorie": id_categorie,
                "etape": self.ETAPE,
                "process_data": process_data
            }
        )
        
        # ========== TRAITER QUESTIONS 2aN ==========
        # Récupérer les IDs des réponses Q1 pour mapping
        id_reponse_map = {}
        if 'reponses' in question_1:
            for rep in question_1['reponses']:
                id_rep = rep.get('id') or rep.get('id_reponse')
                intitule = rep.get('intitule')
                if id_rep and intitule:
                    id_reponse_map[int(id_rep)] = intitule
        
        # Traiter chaque réponse et ses questions suivantes
        for id_reponse, liste_questions in question_2_an.items():
            # Vérifier le stopper
            if utils.check_stopper(id_categorie):
                raise Exception("Processus arrêté manuellement")
            
            # Trouver le nom de la réponse
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

            
            # Vérifier si déjà traité
            if str(id_reponse) in process_data["done"]:
                self._log(f"Réponse {id_reponse} déjà traitée")
                continue
            
            # Collecter toutes les équivalences pour cette réponse
            equivalences_reponse = []
            
            # Traiter chaque question de cette réponse
            for question_suivante in liste_questions:
                # Vérifier le stopper
                if utils.check_stopper(id_categorie):
                    raise Exception("Processus arrêté manuellement")
                
                # Identifier la question
                numero_question = question_suivante.get('id', '')
                if not numero_question:
                    # Chercher dans les clés alternatives
                    for key, value in question_suivante.items():
                        if 'id' in key.lower() and not 'reponse' in key.lower():
                            numero_question = value
                            break
                
                question_id = f"R{id_reponse}_Q{numero_question}"
                
                
                result = await self._generate_equivalence(
                    id_categorie=id_categorie,
                    nom_rubrique=nom_rubrique,
                    question_data=question_suivante,
                    jeu_caracteristique=jeu_caracteristique,
                    question_identifier=question_id,
                    process_data=process_data,
                    use_transform=True  
                )
                
                if result == "already_done":
                    self._log(f"Question {question_id} déjà traitée")
                elif result:                   
                    # Sauvegarder les équivalences Q2aN (result contient directement les équivalences mappées)
                    await self.api_client.post(
                        "equivalence",
                        "question",
                        "save",
                        {
                            "id_categorie": id_categorie,
                            "id_question": numero_question,
                            "equivalences": result
                        }
                    )
                    processed_count += 1
                
                # Marquer comme traité
                if question_id not in process_data["done"]:
                    process_data["done"].append(question_id)
            
            # Marquer la réponse comme traitée
            if str(id_reponse) not in process_data["done"]:
                process_data["done"].append(f"R{id_reponse}")
            
            # Mettre à jour le processus une seule fois après avoir traité toutes les questions de cette réponse
            await self.api_client.post(
                "equivalence",
                "process",
                "update",
                {
                    "id_categorie": id_categorie,
                    "etape": self.ETAPE,
                    "process_data": process_data
                }
            )
        
        self._log("\n" + "=" * 50)
        self._log("GÉNÉRATION ÉQUIVALENCES TERMINÉE")
        self._log(f"Total traité: {processed_count}")
        self._log("=" * 50)

        await self.api_client.post(
            "equivalence",
            "mail",
            "success",
            {
                "id_categorie": id_categorie,
                "tracking_file": self.tracking_file,
                "total_processed": processed_count
            }
        )
        
        return EquivalenceGenerationResult(
            id_categorie=id_categorie,
            nom_rubrique=nom_rubrique,
            total_processed=processed_count,
            status="completed"
        )
    
    async def close(self):
        """Ferme les connexions"""
        await self.api_client.close()