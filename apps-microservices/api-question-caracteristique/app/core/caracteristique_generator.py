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


class CaracteristiqueGenerator:
    """Générateur de caractéristiques via LLM"""
    
    # IDs des prompts
    PROMPT_CARACTERISTIQUE_INITIAL_ID = "95"
    PROMPT_CARACTERISTIQUE_TEXTUELLE_ID = "96"
    PROMPT_CARACTERISTIQUE_NUM_ID = "104"
    
    def __init__(self, api_client: Optional[HelloProAPIClient] = None, etape: Optional[str] = None):
        self.api_client = api_client or HelloProAPIClient()
        self.tracking_file = None
        self.ETAPE = etape or "3"
    
    def _log(self, message: str):
        """Écrit dans le fichier de tracking et les logs"""
        if self.tracking_file:
            utils.write_log(self.tracking_file, message)
        logger.info(message)

    def _validate_caracteristiques(
        self, 
        data: Union[Dict[str, Any], List[Dict[str, Any]]], 
        source: str = "données",
        strict: bool = False
    ) -> Union[Caracteristique, List[Caracteristique]]:
        """
        Valide une ou plusieurs caractéristiques avec le schéma Pydantic
        
        Args:
            data: Dict (1 caractéristique) ou List[Dict] (plusieurs caractéristiques)
            source: Nom de la source pour les logs
            strict: Si True, raise Exception dès qu'une caractéristique est invalide
            
        Returns:
            Caracteristique validée ou List[Caracteristique] validées
        """
        # Cas 1: Une seule caractéristique (Dict)
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
        
        # Cas 2: Liste de caractéristiques (List[Dict])
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
    
    async def generate_caracteristiques_initiales(
        self, 
        id_categorie: str, 
        nom_rubrique: str,
        process_data: Dict[str, Any]
    ) -> Optional[str]:
        """
        Génère les 25 caractéristiques initiales
        """
        self._log("\n" + "=" * 50)
        self._log("GÉNÉRATION CARACTÉRISTIQUES INITIALES (25)")
        self._log("=" * 50)
        
        # Vérifier si déjà généré
        done_caracteristiques = process_data.get("done", [])
        
        if "caracteristique_initial" in done_caracteristiques:
            self._log("Déjà traité")
            return "already_done"
        
        # Récupération du prompt
        prompt_config = await utils.get_prompt(self.PROMPT_CARACTERISTIQUE_INITIAL_ID)
        
        if not prompt_config:
            self._log("ERREUR: Impossible de récupérer le prompt Caractéristiques Initiales")
            await self.api_client.post(
                "caracteristique",
                "mail",
                "error",
                {
                    "id_categorie": id_categorie,
                    "etape": self.ETAPE,
                    "error_message": "Impossible de récupérer le prompt",
                    "tracking_file": self.tracking_file
                }
            )
            raise Exception("Impossible de récupérer le prompt Caractéristiques Initiales")
        
        # Préparer le prompt
        prompt_text = prompt_config["contenu_prompt"]
        prompt_text = prompt_text.replace("{CATEGORIE}", nom_rubrique)
        
        self._log(f"Prompt: {prompt_text[:200]}...")
        
        # Appeler le LLM gemini
        gemini = GeminiProvider(
            model="gemini-3-pro-preview",
            thinking_level="high",
            max_retries=10
        )
        result = await asyncio.to_thread(gemini.chat, prompt_text)
        
        # Si "code" existe dans result, c'est une erreur
        if "code" in result:
            self._log(f"ERREUR API: {result}")
            await self.api_client.post(
                "caracteristique",
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
                "caracteristique",
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
            "caracteristique",
            "initial",
            "save",
            {
                "id_categorie": id_categorie,
                "etape": self.ETAPE,
                "data": json_data
            }
        )

        if not res_insert:
            raise Exception("Échec de la sauvegarde Caractéristiques Initiales")

        self._log(f"Résultat sauvegardé: {res_insert}")

        # VALIDATION 
        self._log("\n--- Validation res_insert Caractéristiques Initiales ---")
        self._validate_caracteristiques(res_insert, source="Insertion Initiales", strict=True)

        return res_insert
    
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
        nom_caracteristique = info_caracteristique.get('nom-caracteristique', '')
        exemples_carc = info_caracteristique.get('exemple-valeurs', '')
        type_carac = info_caracteristique.get('type', '')
        unite_carac = info_caracteristique.get('unite-principale', '')
        
        # Fallback si les clés ne matchent pas exactement
        if not nom_caracteristique or not exemples_carc or not type_carac:
            for key, value in info_caracteristique.items():
                if 'nom' in key.lower():
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
        
        self._log(f"\n--- Génération valeurs: {nom_caracteristique} ---")
        self._log(f"Exemples: {exemples_carc}")
        self._log(f"Type: {type_carac}")
        self._log(f"Unité: {unite_carac}")
        
        # Vérifier si déjà traité
        done_caracteristiques = process_data.get("caracteristique", {}).get("done", [])
        if nom_caracteristique in done_caracteristiques:
            self._log("Déjà traité, passage au suivant")
            return "already_done"
        
        # Déterminer le prompt à utiliser (textuel ou numérique)
        is_textuel = 'text' in type_carac
        prompt_id = self.PROMPT_CARACTERISTIQUE_TEXTUELLE_ID if is_textuel else self.PROMPT_CARACTERISTIQUE_NUM_ID
        
        # Récupérer le prompt
        prompt_config = await utils.get_prompt(prompt_id)
        
        if not prompt_config:
            self._log(f"ERREUR: Impossible de récupérer le prompt pour {nom_caracteristique}")
            await self.api_client.post(
                "caracteristique",
                "mail",
                "error",
                {
                    "id_categorie": id_categorie,
                    "etape": self.ETAPE,
                    "caracteristique": nom_caracteristique,
                    "error_message": "Impossible de récupérer le prompt",
                    "tracking_file": self.tracking_file
                }
            )
            raise Exception(f"Impossible de récupérer le prompt pour {nom_caracteristique}")
        
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
            model="gemini-3-pro-preview",
            thinking_level="high",
            max_retries=10
        )
        result = await asyncio.to_thread(gemini.chat, prompt_text)
        
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
        self._log(f"Réponse LLM: {response_text[:500]}...")
        
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
                "caracteristique": nom_caracteristique,
                "data": json_data
            }
        )

        if not res_insert:
            raise Exception(f"Échec de la sauvegarde pour {nom_caracteristique}")

        self._log(f"Résultat sauvegardé: {res_insert}")

        # VALIDATION
        self._log("\n--- Validation res_insert Valeurs ---")
        self._validate_caracteristiques(res_insert, source="Insertion Valeurs", strict=True)

        return res_insert
    
    async def generate_all_caracteristiques(
        self,
        request: RequestProcessus
    ) -> CaracteristiqueGenerationResult:
        """
        Processus de génération de caractéristiques
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
        self._log("Génération de caractéristiques via LLM")
        self._log(f"Rubrique: {id_categorie} - {nom_rubrique}")
        self._log("=" * 50)
        
        # Récupérer ou initialiser le processus
        process_data = await self.api_client.post(
            "caracteristique",
            "process",
            "get",
            {"id_categorie": id_categorie}
        ) or {}
        
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

        # Générer les 25 caractéristiques initiales
        if self.ETAPE == "3":
            res_initial = await self.generate_caracteristiques_initiales(
                id_categorie, 
                nom_rubrique, 
                process_data
            )
            
            if res_initial == "already_done":
                self._log("Caractéristiques initiales déjà générées")
            elif not res_initial:
                raise Exception("Erreur lors de la génération des caractéristiques initiales")
            else:
                # Mettre à jour le processus
                if "done" not in process_data:
                    process_data = {}
                process_data["done"] = res_initial
                
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
        
        # Charger les caractéristiques initiales
        if self.ETAPE == "4":
            carac_initiales = await self.api_client.post(
                "caracteristique",
                "initial",
                "get",
                {"id_categorie": id_categorie}
            )
            
            # VALIDATION STRICTE
            self._log("\n--- Validation caractéristiques initiales récupérées ---")
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
                    nom_carac = info_caracteristique.get('nom-caracteristique', 'inconnue')
                    self._log(f"Erreur lors de la génération des valeurs pour {nom_carac}")
                    raise Exception(f"Erreur lors de la génération des valeurs pour {nom_carac}")
                
                # Marquer comme traité                
                if "done" not in process_data:
                    process_data["done"] = []
                
                nom_carac = info_caracteristique.get('nom-caracteristique', '')
                process_data["done"].append(nom_carac)
                
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