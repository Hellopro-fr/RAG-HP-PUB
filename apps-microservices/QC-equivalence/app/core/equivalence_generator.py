import time
import logging
import asyncio
import re
from typing import Dict, List, Any, Optional

from app.core.api_client import HelloProAPIClient, GeminiProvider
from app.core import utils
from app.schemas.question_caracteristique import (
    RequestProcessus,
    EquivalenceGenerationResult,
    RequestEquivalenceBO,
    EquivalenceBOResult
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
    # PROMPT_EQUIVALENCE_ID = "107"
    ETAPE = "6"    
    GEMINI_MODEL = "gemini-3.1-pro-preview"

    # ID process
    ID_PROCESS = "30"

    # Façade BO (équivalence sur questionnaire BO ANNUAIRE_BO) — indépendante du step 6
    # Étape 14 = entrée suivante de $all_step (envoie_mail) côté backend
    ETAPE_BO = "14"
    ORIGINE_BO = "qc-equivalence-bo"

    def __init__(self, api_client: Optional[HelloProAPIClient] = None):
        self.api_client = api_client or HelloProAPIClient()
        self.tracking_file = None
        self.prompt_equivalence = None  # Sera chargé lors du premier traitement
    
    def _log(self, message: str):
        """Écrit dans le fichier de tracking et les logs"""
        if self.tracking_file:
            utils.write_log(self.tracking_file, message)
        logger.info(message)

    async def _load_prompts(self, id_categorie: str):
        """Charge les prompts une seule fois au début du traitement"""
        if self.prompt_equivalence is None:
            self.prompt_equivalence = await utils.get_prompt(self.PROMPT_EQUIVALENCE_ID)
            if not self.prompt_equivalence:
                self._log("ERREUR: Impossible de charger le prompt Équivalence")
                await self.api_client.post(
                    "equivalence",
                    "mail",
                    "error",
                    {
                        "id_categorie": id_categorie,
                        "etape": self.ETAPE,
                        "error_message": "Impossible de charger le prompt Équivalence",
                        "tracking_file": self.tracking_file
                    }
                )
                raise Exception("Impossible de charger le prompt Équivalence")
            self._log(f"Prompt Équivalence chargé (ID: {self.PROMPT_EQUIVALENCE_ID})")
    
    def _normalize_string(self, text: str) -> str:
        """
        Normalise une chaîne: garde uniquement lettres/chiffres et met en minuscule
        """
        # Utiliser \w qui inclut lettres, chiffres et underscore (compatible re standard)
        return re.sub(r'[^a-zA-Z0-9àâäéèêëïîôùûüç]', '', text.lower())

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
        # Le PHP renvoie désormais la bulle d'aide structurée (libelle/explication/astuce).
        # Rétrocompat: si l'ancien champ "justification" texte est présent, on le conserve.
        bulle_aide = question_data.get("bulle_aide") or question_data.get("justification", "")
        data_final = {
            "intitule-question": question_data.get("intitule", ""),
            "bulle-aide": bulle_aide,
        }
        
        corres_reponse = {}
        reponses_possibles = question_data.get("reponses", [])
        
        index = 0
        for reponse in reponses_possibles:
            index += 1
            num_reponse = str(reponse.get("id_reponse", "")).strip()
            valeur_reponse = reponse.get("reponse", "")
            
            key = f"reponse-{index}"
            data_final[key] = valeur_reponse
            corres_reponse[key] = num_reponse
        
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
            carac_copy.pop("exemple", None)
            if "valeurs" in carac_copy:
                valeurs_clean = []
                for valeur in carac_copy["valeurs"]:
                    valeur_copy = valeur.copy()
                    valeur_copy.pop("micro_explication", None)
                    valeur_copy.pop("autres_formulations", None)
                    valeurs_clean.append(valeur_copy)
                carac_copy["valeurs"] = valeurs_clean
            jeu_carac_clean.append(carac_copy)
        return jeu_carac_clean

    def _extract_carac_ids_from_equivalences(self, json_data: Dict[str, Any]) -> List:
        """
        Extrait tous les id_caracteristique distincts du résultat d'équivalence.
        json_data est le dict mappé {id_reponse: [equivs normalisées]}
        """
        carac_ids = set()
        for reponse_key, equivs in json_data.items():
            # equivs peut être une liste de dicts normalisés ou un dict brut
            normalized = self._normalize_equivalence(equivs)
            for equiv in normalized:
                id_c = equiv.get("id_caracteristique")
                if id_c is not None:
                    carac_ids.add(str(id_c))
        return list(carac_ids)

    def _filter_jeu_caracteristique(
        self,
        jeu_caracteristique: List[Dict[str, Any]],
        exclude_ids: List
    ) -> List[Dict[str, Any]]:
        """
        Filtre le jeu de caractéristiques en excluant les IDs déjà trouvés
        dans les équivalences précédentes.
        
        Args:
            jeu_caracteristique: Jeu complet de caractéristiques
            exclude_ids: Liste d'IDs de caractéristiques à exclure
            
        Returns:
            Jeu de caractéristiques filtré
        """
        if not exclude_ids:
            return jeu_caracteristique
        exclude_set = set(str(id_c) for id_c in exclude_ids)
        filtered = [c for c in jeu_caracteristique if str(c.get("id_caracteristique", "")) not in exclude_set]
        self._log(f"Filtrage: {len(jeu_caracteristique)} → {len(filtered)} caractéristiques ({len(exclude_set)} exclues)")
        return filtered

    def _normalize_equivalence(self, data: Any) -> List[Dict[str, Any]]:
        """
        Normalise une ou plusieurs équivalences en format uniforme.
        
        Args:
            data: Liste, dict ou objet {"equivalences": [...]}
            
        Returns:
            Liste de dicts normalisés
        """
        # Nouveau format: {"equivalences": [...]}
        if isinstance(data, dict) and "equivalences" in data:
            equiv_list = data.get("equivalences", [])
            if isinstance(equiv_list, list):
                return [self._normalize_single_equivalence(item) for item in equiv_list if isinstance(item, dict)]
            return []
        
        # Si c'est une liste, normaliser chaque élément
        if isinstance(data, list):
            return [self._normalize_single_equivalence(item) for item in data if isinstance(item, dict)]
        elif isinstance(data, dict):
            return [self._normalize_single_equivalence(data)]
        return []
    
    def _normalize_single_equivalence(self, c: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalise une seule équivalence en format uniforme.
        
        """
        id_carac_base = None
        val_cibles = None
        val_bloquantes = None
        val_min = None
        val_max = None
        val_exact = None
        unite = None
        niveau = None
        justification = None
        
        for key, val in c.items():
            key_lower = key.lower().replace("-", "_").replace(" ", "_")
            
            # ID caractéristique
            if ("id" in key_lower and "caracteristique" in key_lower) or (key_lower == "id_caracteristique"):
                id_carac_base = val
            elif key_lower == "id" and id_carac_base is None:
                id_carac_base = val
            elif "cible" in key_lower and val_cibles is None:                
                val_cibles = val
            elif "bloquant" in key_lower and val_bloquantes is None:
                val_bloquantes = val                
            elif "unite" in key_lower and unite is None:
                unite = val                
            elif "ponder" in key_lower or "ponderation" in key_lower:
                if isinstance(val, dict):
                    niveau = val.get("niveau")
                    justification = val.get("justification")

                    if not niveau or not justification:
                        for key_pond, val_pond in val.items():
                            key_pond_lower = key_pond.lower().replace("-", "_").replace(" ", "_")
                            if "niveau" in key_pond_lower and niveau is None:
                                niveau = val_pond
                            elif "justification" in key_pond_lower and justification is None:
                                justification = val_pond   
                else:
                    niveau = val          
        
        return {
            "id_caracteristique": id_carac_base,
            "valeurs_cibles": val_cibles,
            "valeurs_bloquantes": val_bloquantes,
            "unite": unite,
            "ponderation" : {
                "niveau": niveau,
                "justification": justification
            }
        }


    async def _generate_equivalence(
        self,
        id_categorie: str,
        nom_rubrique: str,
        question_data: Dict[str, Any],
        jeu_caracteristique: List[Dict[str, Any]],
        question_identifier: str,
        process_data: Dict[str, Any],
        nom_reponse: str = "",
        use_transform: bool = True,
        exclude_carac_ids: List = None
    ) -> Optional[Dict[str, Any]]:
        """
        Génère les équivalences pour une question (factorisée)
        
        Args:
            id_categorie: ID de la catégorie
            nom_rubrique: Nom de la rubrique
            nom_reponse: Nom de la réponse (optionnel)
            question_data: Données de la question
            jeu_caracteristique: Jeu de caractéristiques
            question_identifier: Identifiant unique de la question (ex: "Q1", "123_Q2")
            process_data: Données du processus
            use_transform: Si True, transforme pour créer mapping (toujours True maintenant)
            exclude_carac_ids: IDs de caractéristiques à exclure (déjà trouvées dans questions précédentes)
            
        Returns:
            Résultat des équivalences ou "already_done"
        """

        id_question = question_data.get('id_question', '')

        self._log(f"\n--- Génération équivalences: {id_question} - {question_identifier} ---")

        if not id_question:
            self._log("ERREUR: Impossible de récupérer l'ID de la question")
            await self.api_client.post(
                "equivalence",
                "mail",
                "error",
                {
                    "id_categorie": id_categorie,
                    "etape": self.ETAPE,
                    "error_message": "Impossible de récupérer l'ID de la question",
                    "tracking_file": self.tracking_file
                }
            )
            raise Exception("Impossible d'extraire l'ID de la question")
        
        # Vérifier si déjà traité
        done_equivalences = process_data.get("done", [])
        if question_identifier in done_equivalences:
            self._log("Déjà traité")
            return "already_done"
        
        # Filtrer les caractéristiques déjà trouvées dans les questions précédentes
        if exclude_carac_ids:
            jeu_caracteristique = self._filter_jeu_caracteristique(jeu_caracteristique, exclude_carac_ids)
        
        # Récupérer le prompt (copie du prompt chargé au début)
        prompt_config = self.prompt_equivalence.copy()

        
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

        self._log(f"JSON Question: {json_question}")
        self._log(f"Corres Reponse: {corres_reponse}")
        self._log(f"Exclude Carac Ids: {exclude_carac_ids}")
        self._log(f"Jeu Caracteristique: {json_caracteristique}")
        
        prompt_text = prompt_config["contenu_prompt"]
        prompt_text = prompt_text.replace("{CATEGORIE}", nom_rubrique)
        prompt_text = prompt_text.replace("{CATEGORIE_REPONSE}", nom_rubrique + " " + nom_reponse)
        prompt_text = prompt_text.replace("{INFO_QUESTION_REPONSE}", json_question)
        prompt_text = prompt_text.replace("{JEU_CARACTERISTIQUE}", json_caracteristique)
        
        self._log(f"Prompt: {prompt_text[:100]}")
        
        # Appeler le LLM Gemini
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
            origine="qc-equivalence",
            etat=1 if "code" not in result else 2,
            retour_erreur=str(result.get("error", "")) if "code" in result else ""
        )
        
        
        if "code" in result:
            self._log(f"ERREUR API: {result}")
            await self.api_client.post(
                "equivalence",
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
        response_text = result.get("message", "").strip()
        self._log(f"Réponse LLM: {response_text}")
        
        json_data = utils.extract_json_from_text(response_text)
        if not json_data:
            self._log("ERREUR: Impossible d'extraire le JSON")
            await self.api_client.post(
                "equivalence",
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
                    equivalences_mapped[real_id] = self._normalize_equivalence(value)
                else:
                    # Si pas de mapping trouvé, garder la clé originale
                    raise Exception(f"Pas de mapping trouvé pour la clé {key}")
            
            self._log(f"Reverse mapping appliqué: {equivalences_mapped}")
            json_data = equivalences_mapped
        
        # Sauvegarder les équivalences Q2aN (result contient directement les équivalences mappées)
        res_insert = await self.api_client.post(
            "equivalence",
            "reponse",
            "save",
            {
                "id_categorie": id_categorie,
                "id_question": id_question,
                "equivalences": json_data
            }
        )

        if not res_insert:
            raise Exception("Échec de la sauvegarde de l'équivalence")

        self._log(f"Résultat sauvegardé: {res_insert}")

        # VALIDATION 
        self._log("\n--- Validation res_insert Équivalences ---")        
        id_equivalences = res_insert.get("id_equivalence", None)
        # verifie si id_equivalences n'est pas None
        if id_equivalences is not None:
            self._log(f"✅ Équivalence(s) créée(s) avec ID(s): {id_equivalences}")
        else:
            self._log("⚠️ Aucun ID d'équivalence retourné par l'API")
            raise Exception("Erreur lors de la génération des équivalences")

        return {
            "result": res_insert,
            "equivalences": json_data
        }
    
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
                    "etape": self.ETAPE,
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
                    "etape": self.ETAPE,
                    "error_message": "Le processus a été arrêté manuellement",
                    "tracking_file": self.tracking_file
                }
            )
            raise Exception("Processus arrêté manuellement")
        
        self._log("=" * 50)
        self._log("Génération des équivalences Question/Caractéristique")
        self._log(f"Rubrique: {id_categorie} - {nom_rubrique}")
        self._log(f"Requête: {request}")
        self._log("=" * 50)
        
        # Charger le prompt une seule fois au début
        await self._load_prompts(id_categorie)

        
        # Récupérer ou initialiser le processus
        process_data = await self.api_client.post(
            "equivalence",
            "process",
            "get",
            {"id_categorie": id_categorie, "etape": self.ETAPE}
        ) or {}
        
        # verification si on peut commencer le processus
        can_start = process_data.get("can_start", False)
        if not can_start:
            self._log("Processus peut pas commencer")
            await self.api_client.post(
                "equivalence",
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
                "equivalence",
                "process",
                "reset",
                {"id_categorie": id_categorie, "etape": self.ETAPE}
            )
            process_data = {}

        self._log(f"Process data: {process_data}")
        
        # Charger les questions (déjà normalisées)
        questions_data = await self.api_client.post(
            "question",
            "all",
            "get",
            {"id_categorie": id_categorie}
        )
        
        if not questions_data:
            raise Exception("Impossible de récupérer les données de questions")
        
        question_1 = questions_data.get("question_1", {})
        question_2_an = questions_data.get("question_2_an", {})
        
        # Charger le jeu de caractéristiques final enrichi
        jeu_caracteristique = await self.api_client.post(
            "caracteristique",
            "final",
            "get",
            {"id_categorie": id_categorie}
        )
        
        if not question_1 or not question_2_an or not jeu_caracteristique:
            self._log(f"ERREUR: Données manquantes - Q1: {bool(question_1)}, Q2aN: {bool(question_2_an)}, Carac: {bool(jeu_caracteristique)}")
            raise Exception("Données d'entrée manquantes (questions ou caractéristiques)")
        
        self._log(f"Question 1 chargée (ID: {question_1.get('id_question')})")
        self._log(f"Questions 2aN: {len(question_2_an)} réponses")
        self._log(f"Jeu caractéristiques: {len(jeu_caracteristique)}")
        
        processed_count = 0
        
        # Initialiser done et data
        if "done" not in process_data:
            process_data["done"] = []
        if "data" not in process_data:
            process_data["data"] = {}
        
        # ========== TRAITER QUESTION 1 ==========
        id_question_1 = question_1.get('id_question')
        question_id_q1 = f"Q1_{id_question_1}"
        result_q1 = await self._generate_equivalence(
            id_categorie=id_categorie,
            nom_rubrique=nom_rubrique,
            nom_reponse="",
            question_data=question_1,
            jeu_caracteristique=jeu_caracteristique,
            question_identifier=question_id_q1,
            process_data=process_data,
            use_transform=True 
        )
        
        if result_q1 == "already_done":
            self._log("Question 1 déjà traitée")
        elif result_q1:
            processed_count += 1
            # Extraire et stocker les IDs de caractéristiques trouvées pour Q1
            equivalences_q1 = result_q1.get("equivalences", {})
            carac_ids_q1 = self._extract_carac_ids_from_equivalences(equivalences_q1)
            process_data["data"][question_id_q1] = carac_ids_q1
            self._log(f"Q1 → caractéristiques trouvées: {carac_ids_q1}")
        
        # Marquer Q1 comme traité
        if question_id_q1 not in process_data["done"]:
            process_data["done"].append(question_id_q1)
        
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
        id_reponse_map = {int(rep.get('id_reponse')): rep.get('reponse') for rep in question_1.get('reponses', [])}
        
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
                raise Exception(f"Réponse {id_reponse} non trouvé")

            
            # Vérifier si déjà traité
            unique_reponse = f"R{id_reponse}"
            if unique_reponse in process_data["done"]:
                self._log(f"Réponse {id_reponse} déjà traitée")
                continue
            
            # Construire la liste cumulative des IDs de caractéristiques
            # à exclure pour cette chaîne de réponse.
            # On commence avec les caractéristiques trouvées dans Q1.
            cumulative_exclude_ids = list(process_data["data"].get(question_id_q1, []))
            self._log(f"Chaîne R{id_reponse}: exclusion initiale Q1 = {cumulative_exclude_ids} caractéristiques")
            
            # Traiter chaque question de cette réponse
            for question_suivante in liste_questions:
                # Vérifier le stopper
                if utils.check_stopper(id_categorie):
                    raise Exception("Processus arrêté manuellement")
                
                # Identifier la question
                numero_question = question_suivante.get('id_question')
                if not numero_question:
                    # Chercher dans les clés alternatives
                    for key, value in question_suivante.items():
                        if 'id' in key.lower() and not 'reponse' in key.lower():
                            numero_question = value
                            break
                
                question_id = f"R{id_reponse}_Q{numero_question}"
                
                # Si cette question a déjà été traitée (reprise après coupure),
                # récupérer ses IDs depuis process_data['data'] pour le cumul
                if question_id in process_data["done"]:
                    self._log(f"Question {question_id} déjà traitée")
                    # Ajouter ses caractéristiques au cumul pour les questions suivantes
                    previously_found = process_data["data"].get(question_id, [])
                    cumulative_exclude_ids.extend(previously_found)
                    self._log(f"{question_id} → {previously_found} caractéristiques trouvées, cumul exclu: {cumulative_exclude_ids}")
                    continue
                
                self._log(f"Question {question_id}: exclusion de {len(cumulative_exclude_ids)} caractéristiques des questions précédentes")
                
                result = await self._generate_equivalence(
                    id_categorie=id_categorie,
                    nom_rubrique=nom_rubrique,
                    nom_reponse=nom_reponse,
                    question_data=question_suivante,
                    jeu_caracteristique=jeu_caracteristique,
                    question_identifier=question_id,
                    process_data=process_data,
                    use_transform=True,
                    exclude_carac_ids=cumulative_exclude_ids
                )
                
                if result == "already_done":
                    self._log(f"Question {question_id} déjà traitée")
                elif result:
                    processed_count += 1
                    # Extraire les IDs de caractéristiques trouvées pour cette question
                    equivalences_q = result.get("equivalences", {})
                    carac_ids_found = self._extract_carac_ids_from_equivalences(equivalences_q)
                    # Stocker dans process_data['data']
                    process_data["data"][question_id] = carac_ids_found
                    # Ajouter au cumul pour les questions suivantes de cette chaîne
                    cumulative_exclude_ids.extend(carac_ids_found)
                    self._log(f"{question_id} → {carac_ids_found} nouvelles caractéristiques trouvées, cumul exclu: {cumulative_exclude_ids}")
                
                # Marquer comme traité
                if question_id not in process_data["done"]:
                    process_data["done"].append(question_id)

                # Mettre à jour le processus
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
            
            # Marquer la réponse comme traitée
            if unique_reponse not in process_data["done"]:
                process_data["done"].append(unique_reponse)
            
            # Mettre à jour le processus
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
                "etape": self.ETAPE,
                "total_processed": processed_count
            }
        )
        
        return EquivalenceGenerationResult(
            id_categorie=id_categorie,
            nom_rubrique=nom_rubrique,
            total_processed=processed_count,
            status="completed"
        )
    
    # ==================================================================
    # FAÇADE BO — équivalence indépendante sur le questionnaire BO
    # (ANNUAIRE_BO). Orchestrateur distinct du step 6 : pas de gating
    # can_start, pas de tracking process, pas de publication aval.
    # ==================================================================

    def _create_bo_question_prompt(
        self,
        question_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Transforme une question au format BO (ANNUAIRE_BO) pour le prompt.

        Format BO distinct du format IA : `question` (intitulé), `description`,
        et `choix` (liste de réponses, chacune avec `id` et `choix`).

        Returns:
            Dict avec json_question et corres_reponse (clé "reponse-N" -> id BO)
        """
        data_final = {
            "intitule-question": question_data.get("question", ""),
            "bulle-aide": question_data.get("description", "") or question_data.get("libelle_info", ""),
        }

        corres_reponse = {}
        index = 0
        for choix in question_data.get("choix", []):
            index += 1
            num_reponse = str(choix.get("id", "")).strip()
            valeur_reponse = choix.get("choix", "")

            key = f"reponse-{index}"
            data_final[key] = valeur_reponse
            corres_reponse[key] = num_reponse

        return {
            "json_question": utils.to_json_string(data_final),
            "corres_reponse": corres_reponse
        }

    async def _generate_equivalence_bo(
        self,
        id_categorie: str,
        nom_rubrique: str,
        question_data: Dict[str, Any],
        jeu_caracteristique: List[Dict[str, Any]],
        exclude_carac_ids: List = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Génère et sauvegarde l'équivalence BO d'une question (format liste plate
        ANNUAIRE_BO) dans la table dédiée equivalence_question_caracteristique_bo.

        Fonction unique : build prompt -> Gemini -> extract -> reverse mapping ->
        save (reponse_bo/save). Retourne {result, equivalences}.
        """
        id_question = str(question_data.get('id', '')).strip()
        self._log(f"\n--- Génération équivalence BO: question {id_question} ---")

        if not id_question:
            self._log("ERREUR: Impossible de récupérer l'ID de la question BO")
            await self.api_client.post(
                "equivalence",
                "mail",
                "error",
                {
                    "id_categorie": id_categorie,
                    "etape": self.ETAPE_BO,
                    "error_message": "Impossible de récupérer l'ID de la question BO",
                    "tracking_file": self.tracking_file
                }
            )
            raise Exception("Impossible d'extraire l'ID de la question BO")

        if exclude_carac_ids:
            jeu_caracteristique = self._filter_jeu_caracteristique(jeu_caracteristique, exclude_carac_ids)

        prompt_config = self.prompt_equivalence.copy()
        jeu_carac_clean = self._clean_jeu_caracteristique(jeu_caracteristique)

        json_prompt_data = self._create_bo_question_prompt(question_data)
        json_question = json_prompt_data["json_question"]
        corres_reponse = json_prompt_data["corres_reponse"]

        json_caracteristique = utils.to_json_string(jeu_carac_clean)

        self._log(f"JSON Question BO: {json_question}")
        self._log(f"Corres Reponse BO: {corres_reponse}")
        self._log(f"Exclude Carac Ids BO: {exclude_carac_ids}")

        prompt_text = prompt_config["contenu_prompt"]
        prompt_text = prompt_text.replace("{CATEGORIE}", nom_rubrique)
        prompt_text = prompt_text.replace("{CATEGORIE_REPONSE}", nom_rubrique)
        prompt_text = prompt_text.replace("{INFO_QUESTION_REPONSE}", json_question)
        prompt_text = prompt_text.replace("{JEU_CARACTERISTIQUE}", json_caracteristique)

        gemini = GeminiProvider(
            model=self.GEMINI_MODEL,
            thinking_level="high",
            max_retries=10
        )
        result = await asyncio.to_thread(gemini.chat, prompt_text)

        usage_metadata = result.get("api_response", {}).get("usage_metadata", {})
        await self.api_client.log_llm_usage(
            type_ia=3,  # Gemini
            model=self.GEMINI_MODEL,
            input_token=usage_metadata.get("prompt_token_count", 0),
            output_token=usage_metadata.get("candidates_token_count", 0) + usage_metadata.get("thoughtsTokenCount", 0),
            id_process=self.ID_PROCESS,
            origine=self.ORIGINE_BO,
            etat=1 if "code" not in result else 2,
            retour_erreur=str(result.get("error", "")) if "code" in result else ""
        )

        if "code" in result:
            self._log(f"ERREUR API BO: {result}")
            await self.api_client.post(
                "equivalence",
                "mail",
                "error",
                {
                    "id_categorie": id_categorie,
                    "etape": self.ETAPE_BO,
                    "error_message": f"Erreur API: {result}",
                    "tracking_file": self.tracking_file
                }
            )
            raise Exception(f"Erreur API Gemini (BO): {result.get('error')}")

        response_text = result.get("message", "").strip()
        self._log(f"Réponse LLM BO: {response_text}")

        json_data = utils.extract_json_from_text(response_text)
        if not json_data:
            self._log("ERREUR: Impossible d'extraire le JSON (BO)")
            await self.api_client.post(
                "equivalence",
                "mail",
                "error",
                {
                    "id_categorie": id_categorie,
                    "etape": self.ETAPE_BO,
                    "error_message": "Erreur extraction JSON",
                    "error_detail": result,
                    "tracking_file": self.tracking_file
                }
            )
            raise Exception("Impossible d'extraire le JSON de la réponse (BO)")

        self._log(f"Équivalences BO extraites: {len(json_data)} réponses")

        # Reverse mapping: clés "reponse-1"... -> vrais IDs de réponses BO
        if corres_reponse:
            equivalences_mapped = {}
            for key, value in json_data.items():
                real_id = corres_reponse.get(key)

                if not real_id:
                    for key_mapped, id_reponse in corres_reponse.items():
                        if self._normalize_string(key) == self._normalize_string(key_mapped):
                            real_id = id_reponse
                            break

                if real_id:
                    equivalences_mapped[real_id] = self._normalize_equivalence(value)
                else:
                    raise Exception(f"Pas de mapping trouvé pour la clé {key}")

            self._log(f"Reverse mapping BO appliqué: {equivalences_mapped}")
            json_data = equivalences_mapped

        res_insert = await self.api_client.post(
            "equivalence",
            "reponse_bo",
            "save",
            {
                "id_categorie": id_categorie,
                "id_question": id_question,
                "equivalences": json_data
            }
        )

        if not res_insert:
            raise Exception("Échec de la sauvegarde de l'équivalence BO")

        self._log(f"Résultat BO sauvegardé: {res_insert}")

        id_equivalences = res_insert.get("id_equivalence", None)
        if id_equivalences is not None:
            self._log(f"✅ Équivalence(s) BO créée(s) avec ID(s): {id_equivalences}")
        else:
            self._log("⚠️ Aucun ID d'équivalence BO retourné par l'API")
            raise Exception("Erreur lors de la génération des équivalences BO")

        return {
            "result": res_insert,
            "equivalences": json_data
        }

    async def generate_equivalences_bo(
        self,
        request: RequestEquivalenceBO
    ) -> EquivalenceBOResult:
        """
        Processus complet de génération des équivalences sur le questionnaire BO.

        Indépendant du pipeline QC step 6 :
        - questionnaire récupéré via question/all_bo/get (source BO) sous son
          format propre : une liste plate de questions (q1..n), pas de Q1/Q2..N,
        - mappé sur le MÊME jeu de caractéristiques final de la catégorie,
        - exclusion cumulative des caractéristiques le long de la liste (même
          logique que l'équivalence IA d'origine),
        - sauvegardé dans equivalence_question_caracteristique_bo,
        - AUCUNE publication vers un service aval.
        """
        id_categorie = request.id_categorie
        source = request.source

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
                    "etape": self.ETAPE_BO,
                    "error_message": f"Catégorie {id_categorie} non trouvée",
                    "tracking_file": self.tracking_file
                }
            )
            raise ValueError(f"Catégorie {id_categorie} non trouvée")

        nom_rubrique = category_info.get("nom_rubrique", "")

        # Initialiser le fichier de tracking (préfixe dédié BO)
        self.tracking_file = utils.get_tracking_filepath(
            id_categorie,
            prefix="equivalence_bo"
        )

        # Vérifier le stopper manuel
        if utils.check_stopper(id_categorie):
            self._log("ARRÊT MANUEL DÉTECTÉ (BO)")
            await self.api_client.post(
                "equivalence",
                "mail",
                "error",
                {
                    "id_categorie": id_categorie,
                    "etape": self.ETAPE_BO,
                    "error_message": "Le processus a été arrêté manuellement",
                    "tracking_file": self.tracking_file
                }
            )
            raise Exception("Processus arrêté manuellement")

        self._log("=" * 50)
        self._log("Génération des équivalences BO Question/Caractéristique")
        self._log(f"Rubrique: {id_categorie} - {nom_rubrique} | source={source}")
        self._log(f"Requête: {request}")
        self._log("=" * 50)

        # Charger le prompt (même prompt d'équivalence que le step 6)
        await self._load_prompts(id_categorie)

        # Reset si demandé : vider la table BO pour cette catégorie
        if request.is_reset:
            self._log("RESET DES ÉQUIVALENCES BO")
            await self.api_client.post(
                "equivalence",
                "reponse_bo",
                "reset",
                {"id_categorie": id_categorie}
            )

        # Récupérer le questionnaire BO : liste plate de questions (q1..n)
        questionnaire = await self.api_client.post(
            "question",
            "all_bo",
            "get",
            {"id_categorie": id_categorie, "source": source}
        )

        if not questionnaire:
            raise Exception("Impossible de récupérer le questionnaire BO")

        # Même jeu de caractéristiques final que la catégorie
        jeu_caracteristique = await self.api_client.post(
            "caracteristique",
            "final",
            "get",
            {"id_categorie": id_categorie}
        )

        if not jeu_caracteristique:
            self._log("ERREUR: Jeu de caractéristiques manquant")
            raise Exception("Données d'entrée manquantes (jeu de caractéristiques)")

        self._log(f"Questionnaire BO chargé: {len(questionnaire)} questions")
        self._log(f"Jeu caractéristiques: {len(jeu_caracteristique)}")

        processed_count = 0

        # Exclusion cumulative des caractéristiques le long de la liste de questions
        cumulative_exclude_ids = []

        for question in questionnaire:
            if utils.check_stopper(id_categorie):
                raise Exception("Processus arrêté manuellement")

            self._log(f"Question BO {question.get('id')}: exclusion de {len(cumulative_exclude_ids)} caractéristiques")

            result = await self._generate_equivalence_bo(
                id_categorie=id_categorie,
                nom_rubrique=nom_rubrique,
                question_data=question,
                jeu_caracteristique=jeu_caracteristique,
                exclude_carac_ids=cumulative_exclude_ids,
            )

            if result:
                processed_count += 1
                carac_ids_found = self._extract_carac_ids_from_equivalences(result.get("equivalences", {}))
                cumulative_exclude_ids.extend(carac_ids_found)
                self._log(f"Question {question.get('id')} → {carac_ids_found} nouvelles caractéristiques, cumul: {cumulative_exclude_ids}")

        self._log("\n" + "=" * 50)
        self._log("GÉNÉRATION ÉQUIVALENCES BO TERMINÉE")
        self._log(f"Total traité: {processed_count}")
        self._log("=" * 50)

        await self.api_client.post(
            "equivalence",
            "mail",
            "success",
            {
                "id_categorie": id_categorie,
                "tracking_file": self.tracking_file,
                "etape": self.ETAPE_BO,
                "total_processed": processed_count
            }
        )

        return EquivalenceBOResult(
            id_categorie=id_categorie,
            nom_rubrique=nom_rubrique,
            source=source,
            total_processed=processed_count,
            status="completed"
        )

    async def close(self):
        """Ferme les connexions"""
        await self.api_client.close()