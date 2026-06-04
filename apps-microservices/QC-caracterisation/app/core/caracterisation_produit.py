import time
import logging
import asyncio
import re
import contextvars
from typing import Dict, List, Any, Optional, Tuple

from app.core.api_client import HelloProAPIClient, DeepSeek
from app.core import utils
from app.schemas.question_caracteristique import (
    RequestProcessus,
    CaracterisationProduitResult
)
from app.core.credentials import settings


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


BATCH_SIZE = 15  # Nombre de produits traités en parallèle


class CaracterisationProduitGenerator:
    """Générateur de caractérisation des produits via LLM"""
    
    # IDs des prompts
    PROMPT_CARACTERISATION_ID = "100"
    PROMPT_REPASSE_ID = "103"
    # PROMPT_CARACTERISATION_ID = "108"
    # PROMPT_REPASSE_ID = "109"
    DEEPSEEK_MODEL = "deepseek-v4-pro"
    
    ETAPE = "7"

    # ID process
    ID_PROCESS = "30"
    
    # ContextVar pour identifier le produit en cours dans chaque tâche async
    _current_product_id = contextvars.ContextVar('current_product_id', default=None)
    
    def __init__(self, api_client: Optional[HelloProAPIClient] = None):
        self.api_client = api_client or HelloProAPIClient()
        self.tracking_file = None
        # Mapping entre ID incrémenté (pour LLM) et ID base de données
        self.id_mapping = {}  # {id_incremente: id_base}
        self.reverse_mapping = {}  # {id_base: id_incremente}
        self.prompt_caracterisation = None  # Sera chargé lors du premier traitement
        self.prompt_repasse = None  # Sera chargé lors du premier traitement
        # Buffer de logs par produit pour éviter l'entrelacement en mode parallèle
        self._product_log_buffers: Dict[str, List[str]] = {}
    
    def _log(self, message: str):
        """
        Écrit dans le fichier de tracking et les logs.
        En mode parallèle, bufferise les logs par produit pour éviter l'entrelacement.
        """
        product_id = self._current_product_id.get(None)
        
        if product_id is not None:
            # Mode parallèle: bufferiser le message avec préfixe produit
            prefixed = f"[P-{product_id}] {message}"
            if product_id not in self._product_log_buffers:
                self._product_log_buffers[product_id] = []
            self._product_log_buffers[product_id].append(prefixed)
            # Logger en temps réel dans la console (avec préfixe)
            logger.info(prefixed)
        else:
            # Mode séquentiel (hors traitement produit): écriture directe
            if self.tracking_file:
                utils.write_log(self.tracking_file, message)
            logger.info(message)
    
    def _flush_product_logs(self, product_id: str):
        """
        Écrit tous les logs bufferisés d'un produit d'un seul bloc dans le fichier de tracking.
        Garantit que les logs d'un même produit restent groupés et lisibles.
        """
        if product_id in self._product_log_buffers:
            logs = self._product_log_buffers.pop(product_id)
            if self.tracking_file and logs:
                # Écrire tout le bloc d'un coup
                block = "\n".join(logs)
                utils.write_log(self.tracking_file, block)


    async def _load_prompts(self, id_categorie: str):
        """Charge les 2 prompts (caractérisation et repasse) une seule fois au début"""
        if self.prompt_caracterisation is None:
            self.prompt_caracterisation = await utils.get_prompt(self.PROMPT_CARACTERISATION_ID)
            if not self.prompt_caracterisation:
                self._log("ERREUR: Impossible de charger le prompt Caractérisation")
                await self.api_client.post(
                    "caracterisation",
                    "mail",
                    "error",
                    {
                        "id_categorie": id_categorie,
                        "etape": self.ETAPE,
                        "error_message": "Impossible de charger le prompt Caractérisation",
                        "tracking_file": self.tracking_file
                    }
                )
                raise Exception("Impossible de charger le prompt Caractérisation")
            self._log(f"Prompt Caractérisation chargé (ID: {self.PROMPT_CARACTERISATION_ID})")
        
        if self.prompt_repasse is None:
            self.prompt_repasse = await utils.get_prompt(self.PROMPT_REPASSE_ID)
            if not self.prompt_repasse:
                self._log("ERREUR: Impossible de charger le prompt Repasse")
                await self.api_client.post(
                    "caracterisation",
                    "mail",
                    "error",
                    {
                        "id_categorie": id_categorie,
                        "etape": self.ETAPE,
                        "error_message": "Impossible de charger le prompt Repasse",
                        "tracking_file": self.tracking_file
                    }
                )
                raise Exception("Impossible de charger le prompt Repasse")
            self._log(f"Prompt Repasse chargé (ID: {self.PROMPT_REPASSE_ID})")

    def _normalize_for_comparison(self, text: str) -> str:
        """
        Normalise une chaîne pour comparaison stricte:
        - Transforme en minuscule
        - Supprime tous les espaces
        - Supprime les accents
        - Supprime les caractères spéciaux
        Retourne uniquement les lettres alphabétiques
        
        Args:
            text: Chaîne à normaliser
            
        Returns:
            Chaîne normalisée (uniquement alphabet minuscule)
        """
        if not text:
            return ""
        import unicodedata
        # Convertir en minuscule
        text = str(text).lower()
        # Normaliser pour supprimer les accents
        nfkd = unicodedata.normalize('NFKD', text)
        text_clean = ''.join([c for c in nfkd if not unicodedata.combining(c)])
        # Garder uniquement les lettres alphabétiques (supprimer espaces, chiffres, caractères spéciaux)
        return re.sub(r'[^a-z]', '', text_clean)
    
    def _normalize_string(self, text: str) -> str:
        """Normalise une chaîne pour comparaison (minuscule, sans caractères spéciaux)"""
        import unicodedata
        nfkd = unicodedata.normalize('NFKD', text)
        text_clean = ''.join([c for c in nfkd if not unicodedata.combining(c)])
        return re.sub(r'[^\w]', '', text_clean.lower())

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
            id_base = carac.get('id_caracteristique')
            
            # Créer le mapping
            id_mapping[index] = id_base
            reverse_mapping[str(id_base)] = index
            
            # Créer une copie avec l'ID incrémenté
            carac_copy = carac.copy()
            carac_copy['id_caracteristique'] = index
            
            caracteristiques_transformed.append(carac_copy)
        
        self._log(f"Mapping créé: {len(id_mapping)} caractéristiques")
        
        return caracteristiques_transformed, id_mapping, reverse_mapping

    def _restore_base_ids(
        self, 
        produit_caract: List[Dict[str, Any]], 
        id_mapping: Dict[int, Any]
    ) -> List[Dict[str, Any]]:
        """
        Reconvertit les IDs incrémentés en IDs base après la réponse LLM
        
        Args:
            produit_caract: Liste des caractéristiques produit avec ID incrémenté
            id_mapping: Mapping {id_incremente: id_base}
            
        Returns:
            Liste avec IDs base restaurés
        """
        restored = []
        for item in produit_caract:
            item_copy = item.copy()
            id_incremente = item_copy.get('id_caracteristique')
            
            if id_incremente is not None:
                id_base = id_mapping.get(int(id_incremente))
                if id_base:
                    item_copy['id_caracteristique'] = id_base
                else:
                    self._log(f"AVERTISSEMENT: ID incrémenté {id_incremente} non trouvé dans le mapping")
            
            restored.append(item_copy)
        
        return restored

    def _clean_caracteristiques_for_prompt(
        self, 
        caracteristiques: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Nettoie et prépare les caractéristiques pour le prompt LLM
        - Enlève micro-explication et autres-formulations des valeurs
        - Ajoute type=Textuelle si nécessaire
        
        Args:
            caracteristiques: Liste des caractéristiques
            
        Returns:
            Liste nettoyée pour le prompt
        """
        cleaned = []
        for carac in caracteristiques:
            carac_copy = carac.copy()
            
            # Ajouter type=Textuelle si unité vide ou type non numérique
            unite = carac_copy.get('unite', '')
            type_carac = carac_copy.get('type', '')
            
            if not unite or not re.match(r'.*num.*', type_carac, re.IGNORECASE):
                if not re.match(r'.*text.*', type_carac, re.IGNORECASE):
                    carac_copy['type'] = 'Textuelle'
            
            # Nettoyer les valeurs
            if 'valeurs' in carac_copy and carac_copy['valeurs']:
                valeurs_clean = []
                for valeur in carac_copy['valeurs']:
                    valeur_copy = valeur.copy()
                    valeur_copy.pop('micro-explication', None)
                    valeur_copy.pop('micro_explication', None)
                    valeur_copy.pop('autres-formulations', None)
                    valeur_copy.pop('autres_formulations', None)
                    valeurs_clean.append(valeur_copy)
                carac_copy['valeurs'] = valeurs_clean
            
            cleaned.append(carac_copy)
        
        return cleaned

    def _verify_caracteristiques_ids(
        self, 
        jeu_carac: Dict[Any, Dict], 
        produit_caract: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Vérifie et corrige les IDs de caractéristiques incohérents
        
        Args:
            jeu_carac: Dictionnaire des caractéristiques {id: carac}
            produit_caract: Liste des caractéristiques produit
            
        Returns:
            Dict avec produit_caract corrigé et flag has_change
        """
        has_change = False
        
        for idx, carac_produit in enumerate(produit_caract):
            id_carac = carac_produit.get('id_caracteristique')
            nom_carac = carac_produit.get('nom-caracteristique', '')
            
            if not nom_carac:
                # Rechercher le nom dans les clés variantes
                for key, value in carac_produit.items():
                    if re.search(r'.*nom.*', key, re.IGNORECASE):
                        nom_carac = value
                        break
            
            # Vérifier si l'ID correspond bien au nom
            if id_carac in jeu_carac:
                nom_ref = jeu_carac[id_carac].get('nom', '')
                if nom_ref == nom_carac or self._normalize_string(nom_ref) == self._normalize_string(nom_carac):
                    continue  # Tout est correct
            
            # Rechercher le bon ID
            nouvel_id = None
            
            # Recherche stricte par nom
            for id_ref, carac_ref in jeu_carac.items():
                if carac_ref.get('nom', '') == nom_carac:
                    nouvel_id = id_ref
                    break
            
            # Recherche via normalisation
            if nouvel_id is None:
                nom_produit_normal = self._normalize_string(nom_carac)
                for id_ref, carac_ref in jeu_carac.items():
                    if self._normalize_string(carac_ref.get('nom', '')) == nom_produit_normal:
                        nouvel_id = id_ref
                        break
            
            if nouvel_id is not None:
                produit_caract[idx]['id_caracteristique'] = nouvel_id
                has_change = True
        
        return {
            'produit_caract': produit_caract,
            'has_change': has_change
        }

    def _clean_null_values(self, produit_caract: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Nettoie les éléments avec id_valeur, valeur et new-value tous null
        """
        cleaned = []
        for item in produit_caract:
            if not (
                item.get('id_valeur') is None and 
                item.get('valeur') is None and 
                item.get('new-value') is None
            ):
                cleaned.append(item)
        return cleaned

    async def caracterise_produit(
        self,
        id_categorie: str,
        nom_rubrique: str,
        id_produit: str,
        titre_produit: str,
        description_produit: str,
        caracteristiques_for_llm: List[Dict[str, Any]],
        description_categorie: str
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Caractérise un produit via le LLM
        
        Returns:
            Liste des caractéristiques du produit ou None si erreur
        """
        self._log(f"\n--- Caractérisation produit: {id_produit} ---")
        self._log(f"Titre: {titre_produit[:50]}...")
        
        # Récupérer le prompt (copie du prompt chargé au début)
        prompt_config = self.prompt_caracterisation.copy()

        
        # Préparer le prompt
        json_caracteristique = utils.to_json_string(caracteristiques_for_llm)

        
        prompt_text = prompt_config["contenu_prompt"]
        prompt_text = prompt_text.replace("{JEU_CARACTERISTIQUE}", json_caracteristique)
        prompt_text = prompt_text.replace("{CATEGORIE}", nom_rubrique)
        prompt_text = prompt_text.replace("{DESCRIPTIF_CATEGORIE}", description_categorie)
        prompt_text = prompt_text.replace("{TITRE_DESCRIPTION}", f"{titre_produit} {description_produit}")
        
        self._log(f"Prompt: {prompt_text[:200]}...")
        
        # Appeler le LLM DeepSeek
        temperature = prompt_config.get("temperature") or 0.1
        deepseek = DeepSeek(temperature=float(temperature))
        result = await asyncio.to_thread(deepseek.chat, prompt_text)
        
        # Enregistrer l'utilisation LLM (coûts et tokens)        
        response_obj = result.get("response")
        if response_obj and hasattr(response_obj, "usage"):
            await self.api_client.log_llm_usage(
                type_ia=2,  # DeepSeek
                model=self.DEEPSEEK_MODEL,
                input_token=response_obj.usage.prompt_tokens,
                output_token=response_obj.usage.completion_tokens,
                id_process=self.ID_PROCESS,
                origine="qc-caracterisation",
                etat=1 if "code" not in result else 2,
                retour_erreur=str(result.get("error", "")) if "code" in result else "",
                temperature=temperature
            )
        
        
        if "code" in result:
            self._log(f"ERREUR API: {result}")
            raise Exception(f"Erreur API DeepSeek: {result.get('error')}")
        
        # Extraire le JSON
        response_text = result.get("content", "").strip()
        self._log(f"Réponse LLM: {response_text}...")
        
        json_data = utils.extract_json_from_text(response_text)
        
        # Si réponse vide "[]", c'est valide
        if json_data is None and re.sub(r'[^\[\]]', '', response_text) == "[]":
            return []
        
        # si json_data est vide et non un array vide, c'est une erreur
        if not json_data and json_data != []:
            self._log("ERREUR: Impossible d'extraire le JSON")
            raise Exception("Impossible d'extraire le JSON de la réponse")
        
        self._log(f"Caractéristiques extraites: {len(json_data)}")
        
        return json_data

    async def repasse_caracterisation(
        self,
        id_categorie: str,
        nom_rubrique: str,
        titre_produit: str,
        description_produit: str,
        produit_caract: List[Dict[str, Any]],
        carac_referentiel: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Repasse de validation des caractéristiques produit
        
        Returns:
            Liste des caractéristiques validées/corrigées
        """
        self._log("--- Repasse caractérisation ---")
        
        if not produit_caract:
            self._log("Caractéristiques produit vides, skip repasse")
            return produit_caract
        
        # Récupérer le prompt de repasse (copie du prompt chargé au début)
        prompt_config = self.prompt_repasse.copy()

        
        self._log(f"JSON Caractéristiques referentiel: {utils.to_json_string(carac_referentiel)}")
        
        # Préparer le prompt
        prompt_text = prompt_config["contenu_prompt"]
        prompt_text = prompt_text.replace("{JEU_CARACTERISTIQUE}", utils.to_json_string(carac_referentiel))
        prompt_text = prompt_text.replace("{CARACTERISTIQUE_PRODUIT}", utils.to_json_string(produit_caract))
        prompt_text = prompt_text.replace("{CATEGORIE}", nom_rubrique)
        prompt_text = prompt_text.replace("{TITRE_DESCRIPTION}", f"{titre_produit} {description_produit}")
        
        self._log(f"Prompt repasse: {prompt_text[:200]}...")
        
        # Appeler le LLM DeepSeek
        temperature = prompt_config.get("temperature") or 0.1
        deepseek = DeepSeek(temperature=float(temperature))
        result = await asyncio.to_thread(deepseek.chat, prompt_text)
        
        # Enregistrer l'utilisation LLM (coûts et tokens)        
        response_obj = result.get("response")
        if response_obj and hasattr(response_obj, "usage"):
            await self.api_client.log_llm_usage(
                type_ia=2,  # DeepSeek
                model=self.DEEPSEEK_MODEL,
                input_token=response_obj.usage.prompt_tokens,
                output_token=response_obj.usage.completion_tokens,
                id_process=self.ID_PROCESS,
                origine="qc-caracterisation-repasse",
                etat=1 if "code" not in result else 2,
                retour_erreur=str(result.get("error", "")) if "code" in result else "",
                temperature=temperature
            )
        
        
        if "code" in result:
            self._log(f"ERREUR API repasse: {result}")
            raise Exception(f"Erreur API DeepSeek repasse: {result.get('error')}")
        
        # Extraire le JSON
        response_text = result.get("content", "").strip()
        self._log(f"Réponse LLM repasse: {response_text}...")
        
        json_data = utils.extract_json_from_text(response_text)
        
        if json_data is None and re.sub(r'[^\[\]]', '', response_text) == "[]":
            return []
        
        if not json_data and json_data != []:
            self._log("ERREUR: Impossible d'extraire le JSON de repasse")
            raise Exception("Impossible d'extraire le JSON de la réponse repasse")
        
        self._log(f"Caractéristiques repasse: {len(json_data)}")
        
        return json_data

    async def _verify_textual_values(
        self,
        produit_caract: List[Dict[str, Any]],
        jeu_carac_dict: Dict[Any, Dict],
        id_categorie: str
    ) -> Tuple[List[Dict[str, Any]], bool]:
        """
        Vérifie et corrige les caractéristiques textuelles après la repasse LLM.
        
        Cette méthode traite 2 cas:
        1. Si new-value est non vide ET id_valeur + valeur sont vides:
           - Vérifie si new-value existe déjà parmi les valeurs possibles
           - Si oui: copie id_valeur + valeur de l'existant et supprime new-value
           - Si non: récupère et vérifie dans all_new_value
        
        2. Si id_valeur est vide MAIS valeur est non vide:
           - Recherche l'id_valeur correspondant dans les valeurs possibles
           - Si non trouvé: supprime la caractéristique
        
        Args:
            produit_caract: Liste des caractéristiques du produit
            jeu_carac_dict: Dictionnaire des caractéristiques {id: carac avec valeurs}
            id_categorie: ID de la catégorie pour charger all_new_value si nécessaire
            
        Returns:
            Tuple (liste corrigée, has_changed)
        """
        if not produit_caract:
            return produit_caract, False
        
        has_changed = False
        result = []
        all_new_value = None  # Sera chargé à la demande
        
        for item in produit_caract:
            id_carac = item.get('id_caracteristique')
            id_valeur = item.get('id_valeur')
            valeur = item.get('valeur')
            new_value = item.get('new-value') or item.get('new_value')
            
            # Récupérer les infos de la caractéristique du référentiel
            carac_ref = jeu_carac_dict.get(id_carac, {})
            valeurs_possibles = carac_ref.get('valeurs', [])
            type_carac = carac_ref.get('type', '')
            
            # Vérifier si c'est une caractéristique textuelle
            is_textuelle = re.match(r'.*text.*', str(type_carac), re.IGNORECASE)
            
            if not is_textuelle:
                # Caractéristique non textuelle, on garde tel quel
                result.append(item)
                continue
            
            item_copy = item.copy()
            
            # CAS 1: new-value non vide ET id_valeur + valeur vides
            if new_value and (not id_valeur and not valeur):
                new_value_normalized = self._normalize_for_comparison(new_value)
                found = False
                
                # Chercher dans les valeurs possibles de la caractéristique
                for val in valeurs_possibles:
                    val_text = val.get('valeur', '')
                    val_normalized = self._normalize_for_comparison(val_text)
                    
                    if val_normalized == new_value_normalized:
                        # Trouvé! Copier id_valeur et valeur, supprimer new-value
                        item_copy['id_valeur'] = val.get('id_valeur')
                        item_copy['valeur'] = val.get('valeur')
                        item_copy.pop('new-value', None)
                        item_copy.pop('new_value', None)
                        found = True
                        has_changed = True
                        self._log(f"[VERIF] new-value '{new_value}' trouvé dans valeurs possibles -> id_valeur={val.get('id_valeur')}")
                        break
                
                # Si pas trouvé, récupérer all_new_value et chercher dedans
                if not found:
                    # Charger all_new_value une seule fois si nécessaire
                    if all_new_value is None:
                        all_new_value = await self.api_client.post(
                            "caracteristique",
                            "new-value",
                            "get",
                            {"id_categorie": id_categorie}
                        ) or {}
                        self._log(f"[VERIF] all_new_value chargé pour vérification")
                    
                    if all_new_value:
                        # Filtrer les new-value de cette caractéristique
                        new_values_for_carac = all_new_value.get(id_carac, [])

                        if not new_values_for_carac:
                           for id_carac_base, base_new_value in all_new_value.items():
                               if self._normalize_for_comparison(id_carac_base) == self._normalize_for_comparison(id_carac):
                                   new_values_for_carac = base_new_value
                                   break
                        
                        for nv in new_values_for_carac:
                            nv_text = nv.get('valeur')
                            nv_normalized = self._normalize_for_comparison(nv_text)
                            
                            if nv_normalized == new_value_normalized and nv.get('id_valeur'):
                                # Trouvé dans all_new_value, copier les valeurs
                                item_copy['id_valeur'] = nv.get('id_valeur')
                                item_copy['valeur'] = nv.get('valeur')
                                item_copy.pop('new-value', None)
                                item_copy.pop('new_value', None)
                                found = True
                                has_changed = True
                                self._log(f"[VERIF] new-value '{new_value}' trouvé dans all_new_value -> id_valeur={nv.get('id_valeur')}")
                                break
                
                # Si toujours pas trouvé, on garde tel quel
                if not found:
                    self._log(f"[VERIF] new-value '{new_value}' non trouvé, conservé tel quel")
                
                result.append(item_copy)
                continue
            
            # CAS 2: id_valeur vide MAIS valeur non vide
            if not id_valeur and valeur:
                valeur_normalized = self._normalize_for_comparison(valeur)
                found = False
                
                # Chercher l'id_valeur dans les valeurs possibles
                for val in valeurs_possibles:
                    val_text = val.get('valeur', '')
                    val_normalized = self._normalize_for_comparison(val_text)
                    
                    if val_normalized == valeur_normalized:
                        # Trouvé! Mettre à jour l'id_valeur
                        item_copy['id_valeur'] = val.get('id_valeur')
                        found = True
                        has_changed = True
                        self._log(f"[VERIF] valeur '{valeur}' trouvée -> id_valeur={val.get('id_valeur')}")
                        break
                
                if not found:
                    # Non trouvé, supprimer cette caractéristique silencieusement
                    has_changed = True
                    continue  # Skip, ne pas ajouter au result
                
                result.append(item_copy)
                continue
            
            # Cas normal: garder tel quel
            result.append(item_copy)
        
        return result, has_changed

    async def _process_single_product(
        self,
        semaphore: asyncio.Semaphore,
        produit: Dict[str, Any],
        id_categorie: str,
        nom_rubrique: str,
        description_categorie: str,
        caracteristiques_for_llm: List[Dict[str, Any]],
        jeu_carac_dict: Dict[Any, Dict]
    ) -> bool:
        """
        Traite un seul produit (caractérisation + repasse + vérification + sauvegarde).
        Utilisé pour le traitement parallèle par batch.
        
        Args:
            semaphore: Sémaphore pour limiter la concurrence
            produit: Données du produit
            id_categorie: ID de la catégorie
            nom_rubrique: Nom de la rubrique
            description_categorie: Description de la catégorie
            caracteristiques_for_llm: Caractéristiques formatées pour le LLM
            jeu_carac_dict: Dictionnaire des caractéristiques {id: carac}
            
        Returns:
            True si le produit a été traité avec succès
        """
        async with semaphore:
            id_produit = str(produit.get("id_produit", ""))
            titre_produit = produit.get("titre", "")
            description_produit = produit.get("description", "")
            
            # Activer le contexte produit pour bufferiser les logs
            token = self._current_product_id.set(id_produit)
            
            try:
                self._log(f"\n--- Produit: {id_produit} {titre_produit}---")
                
                # Étape 1: Caractérisation initiale
                produit_caract = await self.caracterise_produit(
                    id_categorie,
                    nom_rubrique,
                    id_produit,
                    titre_produit,
                    description_produit,
                    caracteristiques_for_llm,
                    description_categorie
                )
                
                if produit_caract is None:
                    self._log(f"Caractérisation échouée pour produit {id_produit}")
                    raise Exception(f"Caractérisation échouée pour produit {id_produit}")
                
                # Nettoyer les valeurs nulles
                produit_caract = self._clean_null_values(produit_caract)
                
                # Restaurer les IDs base avant vérification
                # produit_caract = self._restore_base_ids(produit_caract, id_mapping)
                
                # Vérifier et corriger les IDs incohérents
                verif_result = self._verify_caracteristiques_ids(jeu_carac_dict, produit_caract)
                produit_caract = verif_result['produit_caract']
                
                if verif_result['has_change']:
                    self._log("IDs corrigés après vérification")
                
                # Étape 2: Repasse LLM — DÉSACTIVÉE avec DeepSeek v4-pro (une seule passe suffit).
                # Conservée en commentaire pour garder la trace de son utilisation et pouvoir
                # la réactiver si un modèle moins performant est réutilisé.
                # La méthode repasse_caracterisation() reste définie dans la classe.
                if produit_caract:
                    # # Construire le référentiel pour la repasse
                    # carac_referentiel = []
                    # for item in produit_caract:
                    #     id_carac = item.get('id_caracteristique')
                    #     if id_carac in jeu_carac_dict:
                    #         carac_referentiel.append(jeu_carac_dict[id_carac])
                    #
                    # if carac_referentiel:
                    #     produit_caract = await self.repasse_caracterisation(
                    #         id_categorie,
                    #         nom_rubrique,
                    #         titre_produit,
                    #         description_produit,
                    #         produit_caract,
                    #         carac_referentiel
                    #     )

                    # Vérification des caractéristiques textuelles (garde-fou conservé)
                    produit_caract, verif_changed = await self._verify_textual_values(
                        produit_caract,
                        jeu_carac_dict,
                        id_categorie
                    )

                    if verif_changed:
                        self._log("Caractéristiques textuelles corrigées après vérification")
                
                # Sauvegarder le résultat
                res_carac_produit = await self.api_client.post(
                    "caracterisation",
                    "produit",
                    "save",
                    {
                        "id_categorie": id_categorie,
                        "id_produit": id_produit,
                        "caracteristiques": produit_caract
                    }
                )

                if res_carac_produit == False:
                    raise Exception(f"Erreur lors de la sauvegarde du produit {id_produit}")
                
                self._log(f"✅ Traité avec succès ({len(produit_caract) if produit_caract else 0} caractéristiques)")
                
                return True
            
            finally:
                # Toujours flush les logs et reset le contexte, même en cas d'erreur
                self._flush_product_logs(id_produit)
                self._current_product_id.reset(token)

    async def generate_all_caracterisations(
        self,
        request: RequestProcessus
    ) -> CaracterisationProduitResult:
        """
        Processus complet de caractérisation des produits
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
                "caracterisation",
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
        description_categorie = category_info.get("description", "")
        
        # Initialiser le fichier de tracking
        self.tracking_file = utils.get_tracking_filepath(
            id_categorie, 
            prefix="caracterisation"
        )
        
        # Vérifier le stopper manuel
        if utils.check_stopper(id_categorie):
            self._log("ARRÊT MANUEL DÉTECTÉ")
            await self.api_client.post(
                "caracterisation",
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
        self._log("Caractérisation des produits via LLM")
        self._log(f"Rubrique: {id_categorie} - {nom_rubrique}")
        self._log(f"Requête: {request}")
        self._log("=" * 50)

        # Charger le prompt une seule fois au début
        await self._load_prompts(id_categorie)
        
        # Récupérer ou initialiser le processus
        process_data = await self.api_client.post(
            "caracterisation",
            "process",
            "get",
            {"id_categorie": id_categorie, "etape": self.ETAPE}
        ) or {}
        
        # verification si on peut commencer le processus
        can_start = process_data.get("can_start", False)
        if not can_start:
            self._log("Processus peut pas commencer")
            await self.api_client.post(
                "caracterisation",
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
                "caracterisation",
                "process",
                "reset",
                {"id_categorie": id_categorie, "etape": self.ETAPE}
            )
            process_data = {}
        
        self._log(f"Process data: {process_data}")
        
        # Charger le jeu de caractéristiques final enrichi
        jeu_caracteristique = await self.api_client.post(
            "caracteristique",
            "final",
            "get",
            {"id_categorie": id_categorie}
        ) 
        
        if not jeu_caracteristique:
            raise Exception("Jeu de caractéristiques non trouvé")
        
        self._log(f"Jeu caractéristiques: {len(jeu_caracteristique)}")
        
        # Créer le mapping d'IDs pour le LLM
        caracteristiques_cleaned = self._clean_caracteristiques_for_prompt(jeu_caracteristique)
        # caracteristiques_for_llm, id_mapping, reverse_mapping = self._create_id_mapping(caracteristiques_cleaned)        
        caracteristiques_for_llm = caracteristiques_cleaned

        # Sauvegarder les mappings (désactivé pour l'instant)
        # self.id_mapping = id_mapping
        # self.reverse_mapping = reverse_mapping
        
        # Créer un dictionnaire pour la vérification rapide
        jeu_carac_dict = {carac.get('id_caracteristique'): carac for carac in caracteristiques_cleaned}
        
        # Récupérer les produits à caractériser
        produits = await self.api_client.post(
            "caracterisation",
            "produits",
            "get",
            {"id_categorie": id_categorie , "is_script": True}
        )
        
        if not produits:
            self._log("Aucun produit à caractériser")
            return CaracterisationProduitResult(
                id_categorie=id_categorie,
                nom_rubrique=nom_rubrique,
                total_processed=0,
                status="completed"
            )
        
        self._log(f"Produits à traiter: {len(produits)}")
        self._log(f"Mode parallèle: {BATCH_SIZE} produits simultanés")
        
        processed_count = 0
        error_count = 0
        
        # Initialiser done si nécessaire
        if "done" not in process_data:
            process_data["done"] = []
        
        # Filtrer les produits déjà traités et invalides
        produits_to_process = []
        for produit in produits:            
            id_produit = str(produit.get("id_produit", ""))            
            
            if not id_produit:
                self._log("ID produit manquant")
                continue

            self._log(f"\n--- Produit: {id_produit}---")
            
            # Vérifier si déjà traité
            if id_produit in process_data["done"]:
                self._log(f"Produit {id_produit} déjà traité, skip")
                continue
            produits_to_process.append(produit)
        
        self._log(f"Produits restants à traiter: {len(produits_to_process)}")
        
        # Sémaphore pour limiter la concurrence
        semaphore = asyncio.Semaphore(BATCH_SIZE)
        
        # Traiter les produits par batch
        for batch_start in range(0, len(produits_to_process), BATCH_SIZE):
            # Vérifier le stopper entre chaque batch
            if utils.check_stopper(id_categorie):
                raise Exception("Processus arrêté manuellement")
            
            batch = produits_to_process[batch_start:batch_start + BATCH_SIZE]
            batch_num = (batch_start // BATCH_SIZE) + 1
            total_batches = (len(produits_to_process) + BATCH_SIZE - 1) // BATCH_SIZE
            self._log(f"\n{'='*30} BATCH {batch_num}/{total_batches} ({len(batch)} produits) {'='*30}")
            
            # Lancer le traitement parallèle du batch
            tasks = [
                self._process_single_product(
                    semaphore=semaphore,
                    produit=produit,
                    id_categorie=id_categorie,
                    nom_rubrique=nom_rubrique,
                    description_categorie=description_categorie,
                    caracteristiques_for_llm=caracteristiques_for_llm,
                    jeu_carac_dict=jeu_carac_dict
                )
                for produit in batch
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Analyser les résultats du batch
            batch_processed = 0
            batch_errors = []
            
            for produit, result in zip(batch, results):
                id_produit = str(produit.get("id_produit", ""))
                
                if isinstance(result, Exception):
                    error_count += 1
                    batch_errors.append((id_produit, result))
                    self._log(f"[CAT-{id_categorie}] ❌ Produit {id_produit} en erreur: {str(result)}")
                else:
                    # Succès: marquer comme traité
                    process_data["done"].append(id_produit)
                    processed_count += 1
                    batch_processed += 1
            
            self._log(f"Batch {batch_num} terminé: {batch_processed} OK, {len(batch_errors)} erreurs")
            
            # Mettre à jour le processus après chaque batch
            await self.api_client.post(
                "caracterisation",
                "process",
                "update",
                {
                    "id_categorie": id_categorie,
                    "etape": self.ETAPE,
                    "process_data": process_data
                }
            )
            
            # Si des erreurs dans ce batch, envoyer le mail d'erreur et lever l'exception
            if batch_errors:
                first_error_id, first_error = batch_errors[0]
                error_summary = "; ".join([f"Produit {eid}: {str(err)}" for eid, err in batch_errors])
                await self.api_client.post(
                    "caracterisation",
                    "mail",
                    "error",
                    {
                        "id_categorie": id_categorie,
                        "etape": self.ETAPE,
                        "error_message": error_summary,
                        "tracking_file": self.tracking_file
                    }
                )
                raise Exception(f"ERREUR batch {batch_num}: {error_summary}")
        
        self._log("\n" + "=" * 50)
        self._log("CARACTÉRISATION TERMINÉE")
        self._log(f"Total traité: {processed_count}")
        self._log("=" * 50)

        await self.api_client.post(
            "caracterisation",
            "mail",
            "success",
            {
                "id_categorie": id_categorie,
                "etape": self.ETAPE,
                "tracking_file": self.tracking_file,
                "total_processed": processed_count
            }
        )
        
        return CaracterisationProduitResult(
            id_categorie=id_categorie,
            nom_rubrique=nom_rubrique,
            total_processed=processed_count,
            status="completed"
        )
    
    async def close(self):
        """Ferme les connexions"""
        await self.api_client.close()
