import time
import logging
import asyncio
from typing import Dict, List, Any, Optional, Union
from pydantic import ValidationError

from app.core.api_client import HelloProAPIClient, GeminiProvider
from app.core import utils
from app.schemas.question_caracteristique import (
    RequestProcessus,
    CaracteristiqueGenerationResult,
    Caracteristique,
    ValeurCaracteristique
)
from app.core.credentials import settings


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class InfoCaracteristiquesGenerator:
    """Générateur des informations/valeurs de caractéristiques via LLM"""
    
    # IDs des prompts
    PROMPT_CARACTERISTIQUE_TEXTUELLE_ID = "96"
    PROMPT_CARACTERISTIQUE_NUM_ID = "104"
    # PROMPT_CARACTERISTIQUE_TEXTUELLE_ID = "104"
    # PROMPT_CARACTERISTIQUE_NUM_ID = "105"
    ETAPE = "4"
    GEMINI_MODEL = "gemini-3.1-pro-preview "
    
    def __init__(self, api_client: Optional[HelloProAPIClient] = None):
        self.api_client = api_client or HelloProAPIClient()
        self.tracking_file = None
        self.prompt_textuelle = None  # Sera chargé lors du premier traitement
        self.prompt_numerique = None  # Sera chargé lors du premier traitement
    
    def _log(self, message: str):
        """Écrit dans le fichier de tracking et les logs"""
        if self.tracking_file:
            utils.write_log(self.tracking_file, message)
        logger.info(message)

    async def _load_prompts(self, id_categorie: str):
        """Charge les 2 prompts (textuelle et numérique) une seule fois au début"""
        if self.prompt_textuelle is None:
            self.prompt_textuelle = await utils.get_prompt(self.PROMPT_CARACTERISTIQUE_TEXTUELLE_ID)
            if not self.prompt_textuelle:
                self._log("ERREUR: Impossible de charger le prompt Textuel")
                await self.api_client.post(
                    "caracteristique",
                    "mail",
                    "error",
                    {
                        "id_categorie": id_categorie,
                        "etape": self.ETAPE,
                        "error_message": "Impossible de charger le prompt Textuel",
                        "tracking_file": self.tracking_file
                    }
                )
                raise Exception("Impossible de charger le prompt Textuel")
            self._log(f"Prompt Textuel chargé (ID: {self.PROMPT_CARACTERISTIQUE_TEXTUELLE_ID})")
        
        if self.prompt_numerique is None:
            self.prompt_numerique = await utils.get_prompt(self.PROMPT_CARACTERISTIQUE_NUM_ID)
            if not self.prompt_numerique:
                self._log("ERREUR: Impossible de charger le prompt Numérique")
                await self.api_client.post(
                    "caracteristique",
                    "mail",
                    "error",
                    {
                        "id_categorie": id_categorie,
                        "etape": self.ETAPE,
                        "error_message": "Impossible de charger le prompt Numérique",
                        "tracking_file": self.tracking_file
                    }
                )
                raise Exception("Impossible de charger le prompt Numérique")
            self._log(f"Prompt Numérique chargé (ID: {self.PROMPT_CARACTERISTIQUE_NUM_ID})")

    def _normalize_caracteristique(self, c: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalise une caractéristique en format uniforme.
        
        Args:
            c: Dictionnaire représentant une caractéristique avec des clés variables
            
        Returns:
            Dictionnaire normalisé avec les clés: nom, description, unite, type, valeurs, exemple
        """
        nom, description, unite, type_car, exemple = None, None, None, None, None
        valeurs = []
        
        for key, val in c.items():
            key_lower = key.lower()
            
            # Recherche insensitive des champs principaux
            if "nom" in key_lower and nom is None:
                nom = val
            elif "description" in key_lower and description is None:
                description = val
            elif "unite" in key_lower and unite is None:
                unite = val if val else None
            elif "type" in key_lower and type_car is None:
                type_car = val
            elif "exemple" in key_lower and exemple is None:
                exemple = str(val) if val else None
            elif "valeur" in key_lower and "exemple" not in key_lower:
                if isinstance(val, list):
                    for item in val:
                        if isinstance(item, dict):
                            valeurs.append(self._normalize_valeur(item))
        
        # Normaliser le type
        normalized_type = None
        if type_car is not None:
            type_lower = str(type_car).lower()
            if "text" in type_lower or "textuel" in type_lower:
                normalized_type = "Textuel"
            elif "num" in type_lower or "numérique" in type_lower:
                normalized_type = "Numérique"
            else:
                normalized_type = type_car
        
        return {
            "nom": nom or "",
            "description": description,
            "unite": unite,
            "type": normalized_type,
            "valeurs": valeurs if valeurs else None,
            "exemple": exemple
        }

    def _normalize_valeur(self, v: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalise une valeur de caractéristique.
        
        Args:
            v: Dictionnaire représentant une valeur avec des clés variables
            
        Returns:
            Dictionnaire normalisé avec les clés: valeur, micro_explication, autres_formulations
        """
        valeur, micro_expl, autres_form = None, None, None
        
        for key, val in v.items():
            key_lower = key.lower()
            
            if "valeur" in key_lower and "id" not in key_lower and valeur is None:
                valeur = val
            elif "micro" in key_lower and "explication" in key_lower and micro_expl is None:
                micro_expl = val
            elif "autre" in key_lower and "formulation" in key_lower and autres_form is None:
                autres_form = val if isinstance(val, list) else None
        
        return {
            "valeur": valeur or "",
            "micro_explication": micro_expl,
            "autres_formulations": autres_form
        }

    def _normalize_llm_caracteristiques(self, json_data: Any) -> List[Dict[str, Any]]:
        """
        Normalise les résultats JSON du LLM pour les caractéristiques en format uniforme.
        
        Entrée: dict (une seule caractéristique) ou list (plusieurs caractéristiques)
        Sortie: [{"nom": "...", "description": "...", "unite": "...", "type": "...", "valeurs": [...], "exemple": "..."}]
        """
        
        # Traiter dict (une caractéristique) ou list (plusieurs caractéristiques)
        if isinstance(json_data, dict):
            return self._normalize_caracteristique(json_data)
        elif isinstance(json_data, list):
            return [self._normalize_caracteristique(c) for c in json_data if isinstance(c, dict)]
        return []

    def _validate_caracteristiques(
        self, 
        data: Union[Dict[str, Any], List[Dict[str, Any]]], 
        source: str = "données",
        strict: bool = False
    ) -> Union[Caracteristique, List[Caracteristique]]:
        """
        Valide une ou plusieurs caractéristiques avec le schéma Pydantic
        """
        if isinstance(data, dict):
            try:
                caracteristique = Caracteristique(**data)
                self._log(f"{source} validé")
                return caracteristique
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
            
            for idx, c_data in enumerate(data, 1):
                try:
                    caracteristique = Caracteristique(**c_data)
                    validated.append(caracteristique)
                    self._log(f"Caractéristique {idx}/{total} de {source} validée")
                except ValidationError as e:
                    error_msg = f"Caractéristique {idx}/{total} de {source} invalide"
                    self._log(error_msg)
                    for error in e.errors():
                        self._log(f"  - {error['loc']}: {error['msg']}")
                    
                    if strict:
                        raise Exception(f"{error_msg}: {e}")
                    continue
            
            if strict and not validated:
                raise Exception(f"Aucune caractéristique valide dans {source}")
            
            self._log(f"{source}: {len(validated)}/{total} caractéristiques validées")
            return validated
        
        else:
            raise TypeError(f"Type non supporté: {type(data)}")
    
    async def generate_valeurs_caracteristique(
        self,
        id_categorie: str,
        nom_rubrique: str,
        info_caracteristique: Dict[str, Any],
        process_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Génère les valeurs pour une caractéristique (textuelle ou numérique)
        """
        # Extraire les informations de la caractéristique
        id_caracteristique = info_caracteristique.get('id_caracteristique', '')
        nom_caracteristique = info_caracteristique.get('nom', '')
        exemples_carc = info_caracteristique.get('exemple', '')
        type_carac = info_caracteristique.get('type', '')
        unite_carac = info_caracteristique.get('unite', '')

        #enlever description
        info_caracteristique.pop('description', None)
        
        # Fallback si les clés ne matchent pas exactement
        if not nom_caracteristique or not exemples_carc or not type_carac:
            for key, value in info_caracteristique.items():
                if 'id' in key.lower():
                    id_caracteristique = value
                elif 'nom' in key.lower():
                    nom_caracteristique = value
                elif 'exemple' in key.lower():
                    exemples_carc = value
                elif 'type' in key.lower():
                    type_carac = value
                elif 'unit' in key.lower():
                    unite_carac = value
        
        nom_caracteristique = nom_caracteristique.strip()
        exemples_carc = exemples_carc.strip()
        type_carac = type_carac.strip().lower()        
        
        self._log(f"--- Génération valeurs: {id_caracteristique} - {nom_caracteristique} ---")
        self._log(f"Exemples: {exemples_carc}")
        self._log(f"Type: {type_carac}")
        self._log(f"Unité: {unite_carac}")

        if not nom_caracteristique or not id_caracteristique:
            self._log("ERREUR: Nom ou ID de caractéristique manquant")
            raise Exception("Nom ou ID de caractéristique manquant")
        
        # Vérifier si déjà traité
        done_caracteristiques = process_data.get("done", [])
        if id_caracteristique in done_caracteristiques:
            self._log("Déjà traité, passage au suivant")
            return "already_done"
        
        # Déterminer le prompt à utiliser (textuel ou numérique)
        is_textuel = 'text' in type_carac
        
        # Récupérer le prompt (copie du prompt chargé au début)
        prompt_config = self.prompt_textuelle.copy() if is_textuel else self.prompt_numerique.copy()

        
        # Préparer le prompt
        prompt_text = prompt_config["contenu_prompt"]
        prompt_text = prompt_text.replace("{CATEGORIE}", nom_rubrique)
        prompt_text = prompt_text.replace(
            "{INFO_CARACTERISTIQUE}", 
            utils.to_json_string(info_caracteristique)
        )
        
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
            output_token=usage_metadata.get("candidates_token_count", 0),
            id_process=id_categorie,
            origine="qc-generation-valeurs",
            etat=1 if "code" not in result else 2,
            retour_erreur=str(result.get("error", "")) if "code" in result else ""
        )
        
        
        if "code" in result:
            self._log(f"ERREUR API: {result}")
            await self.api_client.post(
                "caracteristique",
                "mail",
                "error",
                {
                    "id_categorie": id_categorie,
                    "etape": self.ETAPE,
                    "caracteristique": nom_caracteristique,
                    "error_message": f"Erreur API: {result}",
                    "tracking_file": self.tracking_file
                }
            )
            raise Exception(f"Erreur API Gemini pour {nom_caracteristique}: {result.get('error')}")
        
        # Extraire le JSON
        response_text = result.get("message", "")
        self._log(f"Réponse LLM: {response_text}...")
        
        json_data = utils.extract_json_from_text(response_text)
        
        if not json_data:
            self._log("ERREUR: Impossible d'extraire le JSON")
            await self.api_client.post(
                "caracteristique",
                "mail",
                "error",
                {
                    "id_categorie": id_categorie,
                    "etape": self.ETAPE,
                    "caracteristique": nom_caracteristique,
                    "error_message": "Erreur extraction JSON",
                    "error_detail": result,
                    "tracking_file": self.tracking_file
                }
            )
            raise Exception(f"Impossible d'extraire le JSON pour {nom_caracteristique}")
        
        # Sauvegarder le résultat        
        res_insert = await self.api_client.post(
            "caracteristique",
            "final",
            "save",
            {
                "id_categorie": id_categorie,
                "etape": self.ETAPE,
                "id_caracteristique": id_caracteristique,
                "data": self._normalize_llm_caracteristiques(json_data)
            }
        )

        if not res_insert:
            raise Exception(f"Échec de la sauvegarde pour {nom_caracteristique}")

        self._log(f"Résultat sauvegardé: {res_insert}")

        # VALIDATION
        self._log("\n--- Validation res_insert Valeurs ---")
        id_caracteristiques = res_insert.get("id_caracteristique", None)
        if id_caracteristiques:
            self._log(f"✅ Caractéristique(s) mise(s) à jour avec ID(s): {id_caracteristiques}")
        else:
            self._log("⚠️ Aucun ID de caractéristique retourné par l'API")

        return id_caracteristiques
    
    async def generate_all_caracteristiques(
        self,
        request: RequestProcessus
    ) -> CaracteristiqueGenerationResult:
        """
        Processus de génération des valeurs pour chaque caractéristique
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
                "caracteristique",
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
            prefix="caracteristique"
        )
        
        # Vérifier le stopper manuel
        if utils.check_stopper(id_categorie):
            self._log("ARRÊT MANUEL DÉTECTÉ")
            await self.api_client.post(
                "caracteristique",
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
        self._log("Génération des valeurs de caractéristiques via LLM")
        self._log(f"Rubrique: {id_categorie} - {nom_rubrique}")
        self._log(f"Requête: {request}")
        self._log("=" * 50)
        
        # Charger les prompts une seule fois au début
        await self._load_prompts(id_categorie)

        
        # Récupérer ou initialiser le processus
        process_data = await self.api_client.post(
            "caracteristique",
            "process",
            "get",
            {"id_categorie": id_categorie, "etape": self.ETAPE}
        ) or {}
        
        # verification si on peut commencer le processus
        can_start = process_data.get("can_start", False)
        if not can_start:
            self._log("Processus peut pas commencer")
            await self.api_client.post(
                "caracteristique",
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
                "caracteristique",
                "process",
                "reset",
                {"id_categorie": id_categorie, "etape": self.ETAPE}
            )
            process_data = {}
        
        processed_count = 0

        self._log(f"Process data: {process_data}")        

        # Charger les caractéristiques initiales
        carac_initiales = await self.api_client.post(
            "caracteristique",
            "initial",
            "get",
            {"id_categorie": id_categorie}
        )
        
        # VALIDATION STRICTE
        self._log(f"\n--- Validation caractéristiques initiales récupérées: \n {carac_initiales} ---")
        validated_carac = self._validate_caracteristiques(
            carac_initiales, 
            source="carac_initiales", 
            strict=True
        )
        
        # Vérifier que carac_initiales existe
        if not carac_initiales or not isinstance(carac_initiales, list):
            self._log("ERREUR: Impossible de récupérer les caractéristiques initiales")
            await self.api_client.post(
                "caracteristique",
                "mail",
                "error",
                {
                    "id_categorie": id_categorie,
                    "etape": self.ETAPE,
                    "error_message": "Impossible de récupérer les caractéristiques initiales",
                    "tracking_file": self.tracking_file
                }
            )
            raise Exception("Impossible de récupérer les caractéristiques initiales")
        
        # Générer les valeurs pour chaque caractéristique
        total_caracteristiques = len(carac_initiales)
        
        for idx, info_caracteristique in enumerate(carac_initiales, 1):
            
            # Vérifier le stopper à chaque itération
            if utils.check_stopper(id_categorie):
                await self.api_client.post(
                    "caracteristique",
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
            
            valeurs_data = await self.generate_valeurs_caracteristique(
                id_categorie,
                nom_rubrique,
                info_caracteristique,
                process_data
            )

            # Gérer le cas "déjà traité"
            if valeurs_data == "already_done":
                self._log(f"Caractéristique {idx}/{total_caracteristiques} déjà traitée")
                continue

            if not valeurs_data:
                nom_carac = info_caracteristique.get('nom', 'inconnue')
                self._log(f"Erreur lors de la génération des valeurs pour {valeurs_data} {nom_carac}")
                raise Exception(f"Erreur lors de la génération des valeurs pour {valeurs_data} {nom_carac}")
            
            # Marquer comme traité                
            if "done" not in process_data:
                process_data["done"] = []
            
            process_data["done"].append(valeurs_data)
            
            await self.api_client.post(
                "caracteristique",
                "process",
                "update",
                {
                    "id_categorie": id_categorie,
                    "etape": self.ETAPE,
                    "process_data": process_data
                }
            )
            
            processed_count += 1
            self._log(f"Progression: {idx}/{total_caracteristiques}")

        self._log("\n" + "=" * 50)
        self._log("GÉNÉRATION TERMINÉE")
        self._log("=" * 50)

        await self.api_client.post(
            "caracteristique",
            "mail",
            "success",
            {
                "id_categorie": id_categorie,
                "etape": self.ETAPE,
                "tracking_file": self.tracking_file
            }
        )
        
        return CaracteristiqueGenerationResult(
            id_categorie=id_categorie,
            nom_rubrique=nom_rubrique,
            total_processed=processed_count,
            status="completed"
        )
    
    async def close(self):
        """Ferme les connexions"""
        await self.api_client.close()
