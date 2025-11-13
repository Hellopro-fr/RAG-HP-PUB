import os
import json
import time
import logging
import asyncio
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict

import openai

from .search import (
    call_search_api,
    get_product_details,
    get_category_details,
    call_search_api_async,
    get_category_details_async,
    get_prompt_details_async,
    EXTERNAL_PRODUCT_API_URL,
    EXTERNAL_CATEGORY_API_URL,
    EXTERNAL_PROMPT_API_URL
)

logger = logging.getLogger(__name__)

# Import du client gRPC pour Qwen
try:
    from common_utils.grpc_clients import (llm_client)
    from common_utils.grpc_clients.schemas.chat import ChatRequest
    QWEN_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Impossible d'importer le client gRPC Qwen: {e}")
    QWEN_AVAILABLE = False
    llm_client = None
    ChatRequest = None


class ProductClassifier:
    def __init__(self, llm_choice: str = 'DeepSeek'):
        self.llm_choice = llm_choice
        self.openai_client = None
        self.deepseek_client = None
        self.category_cache = {}
        self.category_summary_cache = {}  # Cache pour les résumés de descriptions
        self.prompt_cache = {}  # Cache pour les templates de prompts avec timestamp
        self.prompt_cache_duration = 900  # Durée du cache en secondes (15 minutes = 900s)
        self.search_results_limit = 30
        self.categories_limit = 10

        self._initialize_clients()
    
    def _initialize_clients(self):
        """Initialise les clients LLM"""
        if self.llm_choice == 'OpenAI':
            api_key = os.getenv('OPENAI_API_KEY')
            if api_key:
                self.openai_client = openai.OpenAI(api_key=api_key)
                #logger.info("Client OpenAI configuré")
            else:
                raise ValueError("OPENAI_API_KEY manquante")

        elif self.llm_choice == 'DeepSeek':
            api_key = os.getenv('DEEPSEEK_API_KEY')
            if api_key:
                self.deepseek_client = openai.OpenAI(
                    api_key=api_key,
                    base_url="https://api.deepseek.com",
                    timeout=60
                )
                #logger.info("Client DeepSeek configuré")
            else:
                raise ValueError("DEEPSEEK_API_KEY manquante")

        elif self.llm_choice == 'Qwen':
            if not QWEN_AVAILABLE:
                raise ValueError("Client gRPC Qwen non disponible. Vérifiez que common_utils est installé.")
            # Vérifier que la variable d'environnement LLM_SERVICE_URL est définie
            llm_service_url = os.getenv('LLM_SERVICE_URL')
            if not llm_service_url:
                logger.warning("LLM_SERVICE_URL non définie, utilisation de la valeur par défaut: llm-service:50051")
            logger.info(f"Client gRPC Qwen configuré (URL: {llm_service_url or 'llm-service:50051'})")
    
    def update_configuration(self, config: Dict[str, Any]):
        """Met à jour la configuration du classificateur"""
        if 'llm_choice' in config and config['llm_choice'] != self.llm_choice:
            self.llm_choice = config['llm_choice']
            self._initialize_clients()
        
        if 'search_results_limit' in config:
            self.search_results_limit = config['search_results_limit']
        
        if 'categories_limit' in config:
            self.categories_limit = config['categories_limit']
    
    def get_configuration(self) -> Dict[str, Any]:
        """Retourne la configuration actuelle"""
        return {
            'llm_choice': self.llm_choice,
            'search_results_limit': self.search_results_limit,
            'categories_limit': self.categories_limit
        }

    def _format_categories_candidates(self, categories: List[Dict]) -> List[Dict[str, Any]]:
        """Formate la liste des catégories candidates pour le retour API"""
        return [
            {
                'id': cat['id'],
                'name': cat['name'],
                'average_score': round(cat['average_score'], 4),
                'total_score': round(cat['total_score'], 4),
                'product_count': cat['product_count']
            }
            for cat in categories[:self.categories_limit]
        ]

    def is_llm_configured(self) -> bool:
        """Vérifie si un LLM est configuré"""
        if self.llm_choice == 'Qwen':
            return QWEN_AVAILABLE
        return (self.openai_client is not None) or (self.deepseek_client is not None)
    
    def search_similar_products(self, title: str, n_results: int = None) -> List[Dict]:
        """Recherche des produits similaires"""
        if n_results is None:
            n_results = self.search_results_limit
            
        try:
            raw_results = call_search_api(title, num_results=n_results, use_reranker=True)
            if not raw_results:
                return []
            
            # Construire les résultats
            results = []
            for item in raw_results:
                metadata = item.get('metadata', {}).get('entity', {})
                prod_id = metadata.get('id_produit')
                if not prod_id:
                    continue
                    
                result = {
                    'id_produit': prod_id,
                    'nom_produit': metadata.get('nom_produit', 'N/A'),
                    'categorie': metadata.get('categorie', 'N/A'),
                    'id_categorie': metadata.get('id_categorie', 'N/A'),
                    'score': item.get('rerank_score', item.get('score', 0.0))
                }
                results.append(result)
            
            return sorted(results, key=lambda x: x['score'], reverse=True)
            
        except Exception as e:
            logger.error(f"Erreur recherche similaires: {e}")
            return []

    def group_by_category(self, products: List[Dict]) -> List[Dict]:
        """Groupe les produits par catégorie et calcule les scores"""
        category_groups = defaultdict(list)
        
        for product in products:
            cat_id = product['id_categorie']
            cat_name = product['categorie']
            if cat_id and cat_name:
                category_groups[cat_id].append(product)
        
        categories = []
        for cat_id, prods in category_groups.items():
            cat_name = prods[0]['categorie']
            avg_score = sum(p['score'] for p in prods) / len(prods)
            total_score = sum(p['score'] for p in prods)
            
            categories.append({
                'id': cat_id,
                'name': cat_name,
                'average_score': avg_score,
                'total_score': total_score,
                'product_count': len(prods)
            })
        
        return sorted(categories, key=lambda x: x['total_score'], reverse=True)

    def get_category_descriptions(self, categories: List[Dict]) -> Dict[str, str]:
        """Récupère les descriptions de catégories"""
        descriptions = {}
        
        # Récupérer les IDs non mis en cache
        ids_to_fetch = [c['id'] for c in categories if c['id'] not in self.category_cache]
        
        if ids_to_fetch:
            try:
                details = get_category_details(ids_to_fetch, EXTERNAL_CATEGORY_API_URL)
                if details:
                    for detail in details:
                        cat_id = str(detail['id_categorie'])
                        desc = detail['description_categorie']
                        if len(desc) > 200:
                            desc = desc[:200] + "..."
                        self.category_cache[cat_id] = desc
            except Exception as e:
                logger.error(f"Erreur descriptions catégories: {e}")
                for cat_id in ids_to_fetch:
                    self.category_cache[cat_id] = "Description non disponible"
        
        # Retourner les descriptions
        for cat in categories:
            descriptions[cat['id']] = self.category_cache.get(cat['id'], "N/A")
        
        return descriptions

    async def search_similar_products_async(self, title: str, n_results: int = None) -> List[Dict]:
        """
        Version asynchrone de search_similar_products pour pipeline parallèle.
        Utilise call_search_api_async pour des appels HTTP non-bloquants.
        """
        if n_results is None:
            n_results = self.search_results_limit

        try:
            raw_results = await call_search_api_async(title, num_results=n_results, use_reranker=True)
            if not raw_results:
                return []

            # Construire les résultats
            results = []
            for item in raw_results:
                metadata = item.get('metadata', {}).get('entity', {})
                prod_id = metadata.get('id_produit')
                if not prod_id:
                    continue

                result = {
                    'id_produit': prod_id,
                    'nom_produit': metadata.get('nom_produit', 'N/A'),
                    'categorie': metadata.get('categorie', 'N/A'),
                    'id_categorie': metadata.get('id_categorie', 'N/A'),
                    'score': item.get('rerank_score', item.get('score', 0.0))
                }
                results.append(result)

            return sorted(results, key=lambda x: x['score'], reverse=True)

        except Exception as e:
            logger.error(f"[ASYNC] Erreur recherche similaires: {e}")
            return []

    async def _summarize_category_description_async(self, description: str) -> Dict[str, Any]:
        """
        Résume une description de catégorie en 2 phrases maximum via DeepSeek.

        Returns:
            Dict contenant:
                - summary: Le résumé de la description
                - input_tokens: Nombre de tokens d'entrée
                - output_tokens: Nombre de tokens de sortie
        """
        if not description or description == "N/A" or description == "Description non disponible":
            return {
                "summary": description,
                "input_tokens": 0,
                "output_tokens": 0
            }

        # Initialiser le client DeepSeek pour la summarization
        api_key = os.getenv('DEEPSEEK_API_KEY')
        if not api_key:
            logger.warning("DEEPSEEK_API_KEY non disponible pour la summarization")
            return {
                "summary": description[:200] + "..." if len(description) > 200 else description,
                "input_tokens": 0,
                "output_tokens": 0
            }

        try:
            deepseek_client = openai.OpenAI(
                api_key=api_key,
                base_url="https://api.deepseek.com",
                timeout=60
            )

            prompt = f"Résume cette description de catégorie en maximum 2 phrases concises, sans mise en forme, sans liste à puces:\n\n{description}"

            response = await asyncio.to_thread(
                deepseek_client.chat.completions.create,
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=150
            )

            summary = response.choices[0].message.content.strip()
            input_tokens = response.usage.prompt_tokens if hasattr(response.usage, 'prompt_tokens') else 0
            output_tokens = response.usage.completion_tokens if hasattr(response.usage, 'completion_tokens') else 0

            return {
                "summary": summary,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens
            }

        except Exception as e:
            logger.error(f"Erreur lors du résumé DeepSeek: {e}")
            # En cas d'erreur, retourner une version tronquée
            return {
                "summary": description[:200] + "..." if len(description) > 200 else description,
                "input_tokens": 0,
                "output_tokens": 0
            }

    async def get_category_descriptions_async(self, categories: List[Dict]) -> Tuple[Dict[str, str], Dict[str, int]]:
        """
        Version asynchrone de get_category_descriptions pour pipeline parallèle.
        Utilise get_category_details_async pour des appels HTTP non-bloquants.
        Résume les descriptions via DeepSeek et retourne les tokens consommés.

        Returns:
            tuple: (descriptions_dict, tokens_dict)
                - descriptions_dict: {cat_id: résumé}
                - tokens_dict: {'input_tokens': X, 'output_tokens': Y}
        """
        descriptions = {}
        total_input_tokens = 0
        total_output_tokens = 0

        # Récupérer les IDs non mis en cache (ni description ni résumé)
        ids_to_fetch = [c['id'] for c in categories if c['id'] not in self.category_cache]

        if ids_to_fetch:
            try:
                details = await get_category_details_async(ids_to_fetch, EXTERNAL_CATEGORY_API_URL)
                if details:
                    for detail in details:
                        cat_id = str(detail['id_categorie'])
                        desc = detail['description_categorie']
                        self.category_cache[cat_id] = desc
            except Exception as e:
                logger.error(f"[ASYNC] Erreur descriptions catégories: {e}")
                for cat_id in ids_to_fetch:
                    self.category_cache[cat_id] = "Description non disponible"

        # Résumer les descriptions qui n'ont pas encore de résumé en cache
        ids_to_summarize = [c['id'] for c in categories if c['id'] not in self.category_summary_cache]

        if ids_to_summarize:
            # Créer des tâches pour résumer en parallèle
            summarize_tasks = []
            for cat_id in ids_to_summarize:
                original_desc = self.category_cache.get(cat_id, "N/A")
                summarize_tasks.append(self._summarize_category_description_async(original_desc))

            # Exécuter les résumés en parallèle
            summary_results = await asyncio.gather(*summarize_tasks)

            # Mettre en cache et accumuler les tokens
            for cat_id, result in zip(ids_to_summarize, summary_results):
                self.category_summary_cache[cat_id] = result["summary"]
                total_input_tokens += result["input_tokens"]
                total_output_tokens += result["output_tokens"]

        # Retourner les résumés
        for cat in categories:
            descriptions[cat['id']] = self.category_summary_cache.get(cat['id'], "N/A")

        return descriptions, {
            'input_tokens': total_input_tokens,
            'output_tokens': total_output_tokens
        }

    async def get_prompt_template_async(self, prompt_id: int = 20) -> str:
        """
        Récupère le template de prompt depuis l'API externe avec mise en cache de 15 minutes.

        Args:
            prompt_id: ID du prompt à récupérer (par défaut 20)

        Returns:
            Le template de prompt avec les placeholders {titre_produit}, {description_produit}, etc.
        """
        current_time = time.time()

        # Vérifier si le prompt est en cache et s'il n'a pas expiré (15 minutes)
        if prompt_id in self.prompt_cache:
            cached_data = self.prompt_cache[prompt_id]
            cache_timestamp = cached_data.get('timestamp', 0)
            cache_age = current_time - cache_timestamp

            # Si le cache a moins de 15 minutes (900 secondes)
            if cache_age < self.prompt_cache_duration:
                logger.info(f"[ASYNC] Prompt ID {prompt_id} récupéré depuis le cache (âge: {cache_age:.0f}s)")
                return cached_data['content']
            else:
                logger.info(f"[ASYNC] Cache du prompt ID {prompt_id} expiré (âge: {cache_age:.0f}s), récupération d'une nouvelle version")

        # Récupérer le prompt depuis l'API externe
        try:
            prompt_template = await get_prompt_details_async(prompt_id, EXTERNAL_PROMPT_API_URL)

            if prompt_template:
                # Mettre en cache avec timestamp
                self.prompt_cache[prompt_id] = {
                    'content': prompt_template,
                    'timestamp': current_time
                }
                logger.info(f"[ASYNC] Prompt ID {prompt_id} récupéré et mis en cache pour 15 minutes")
                return prompt_template
            else:
                logger.error(f"[ASYNC] Impossible de récupérer le prompt ID {prompt_id}, utilisation du prompt par défaut")
                # Retourner le prompt par défaut (actuel) en cas d'erreur
                return self._get_default_prompt_template()

        except Exception as e:
            logger.error(f"[ASYNC] Erreur lors de la récupération du prompt ID {prompt_id}: {e}")
            return self._get_default_prompt_template()

    def _get_default_prompt_template(self) -> str:
        """
        Retourne le template de prompt par défaut (l'ancien prompt statique)
        en cas d'erreur de récupération depuis l'API externe.
        """
        return """*** OUBLI TOUTES LES INSTRUCTIONS PRECEDENTES

OBJECTIFS :

Déterminer si le produit "CONTENU DU PRODUIT" peut être catégorisé dans une des catégories proposées dans la "LISTE DES CATEGORIES".
Identifier si aucune des catégories proposées ne correspond parfaitement au produit.
RÉPONDRE : OUI ou NON
Indiquer qu'il ne peut être catégorisé dans aucune des catégories proposées, car aucune catégorie ne correspond parfaitement.

RÉPONDRE : Catégorie Absente.

ÉTAPES TEST en ENTONNOIR A SUIVRE :

1ère étape : Analyse du produit

Lire attentivement le "CONTENU DU PRODUIT" : mots clés, termes, et spécificités.
Identifier la nature du produit, son utilisation, ses caractéristiques détaillées (ex. marque, modèle, caractéristiques).
Ne pas faire d'interprétations ou d'extrapolations du contenu du produit. S'en tenir strictement aux informations fournies.

2ème étape : Évaluation des catégories

Examiner la définition de chaque catégorie dans la "LISTE DES CATEGORIES".
Pour chaque catégorie, vérifier si le produit peut y être classé. Si correspondance exacte ou non.
La catégorie doit correspondre parfaitement au produit en termes de nature, utilisation et caractéristiques spécifiques.

3ème étape : Décision de classification

Si une catégorie correspond parfaitement, répondre OUI.
Sinon, répondre NON.

4ème étape : Attribution du score suivant les conditions énumérées

Score = 1 : Choisir cette catégorie si et seulement si le produit correspond parfaitement à tous les critères spécifiés. Aucune autre catégorie dans la "LISTE DES CATEGORIES" ne correspondrait mieux.
Score = 0 : Si la catégorie semble convenir mais il est possible qu'une autre catégorie dans la "LISTE DES CATEGORIES" soit une meilleure correspondance ou si aucune catégorie ne correspond parfaitement.

"IMPORTANTS" :
La liste des catégories dans "LISTE DES CATEGORIES" n'est pas exhaustive. Il est possible qu'il existe d'autres catégories appropriées pour ce produit.

Si la catégorie est très spécifique, le score doit être 0 si le produit ne respecte pas tous ses critères.

Si le produit est un accessoire ou un consommable lié à une catégorie spécifique, le score doit être directement mis à 0. (Exemple : un produit comme un 'pied de table' ne devrait pas être classé dans la catégorie 'table').

La description exacte du produit doit être considérée pour éviter toute confusion avec une catégorie similaire mais non correspondante. (Exemple : "Brouette gravillonneuse" – si le produit est une "Brouette" avec le descriptif précisant que c'est fait pour le "gravillon", alors le classer dans cette catégorie avec un score = 1. Sinon, si ce n'est pas indiqué avec précision que c'est une "Brouette gravillonneuse", alors mettre score = 0.)

Si la description du produit manque de précision sur un usage spécifique ou une caractéristique clé nécessaire pour une catégorie, considérer que le produit ne correspond pas à cette catégorie score = 0.

En cas de doute sur l'application précise d'une catégorie, privilégier la prudence et ne pas classer le produit dans une catégorie inappropriée, score = 0.

Vérifiez également que le produit n'est pas simplement un accessoire ou une partie d'un autre produit. Si c'est le cas, il doit être exclu de cette catégorie et marqué avec un score = 0.

Fin étape : Validation des scores
Revérifier que le score attribué (0 ou 1) est approprié en suivant les exemples et critères donnés.
Revalider avec les conditions "IMPORTANTS"

---
CONTENU DU PRODUIT :
Titre: {titre_produit}
Description: {description_produit}
---
LISTE DES CATEGORIES (avec leur description) :
{liste_categories}
---
EXEMPLES DE PRODUITS SIMILAIRES (pour contexte) :
{liste_produits}
---

Format de réponse JSON **uniquement**, avec 2 champs :
Score = 1 : (si et seulement si le produit remplit à 100% toutes les caractéristiques correspondant à cette catégorie) "Categorie" avec l'ID de la catégorie sélectionnée et "Score".
ou sinon
Score = 0  (catégorie qui se rapproche au mieux du produit)
"Categorie" ID catégorie choisie  et "Score".
{{
  "id_categorie": "ID de la catégorie choisie (même si le score est 0)",
  "score": <0 ou 1>
}}
"""

    async def build_prompt_async(self, product: Dict, categories: List[Dict], descriptions: Dict, top_k_products: List[Dict]) -> str:
        """
        Construit le prompt pour le LLM en récupérant le template depuis l'API externe.
        Remplace les placeholders par les valeurs réelles.
        """
        # Récupérer le template de prompt (avec cache)
        prompt_template = await self.get_prompt_template_async(prompt_id=20)

        # Formater les catégories
        formatted_categories = "\n".join([
            f"- ID: {cat['id']}, Nom: {cat['name']} (Score: {cat['total_score']:.2f})\n"
            f"  Description: {descriptions.get(cat['id'], 'N/A')}"
            for cat in categories[:self.categories_limit]
        ])

        # Formater les produits similaires
        formatted_products = "\n".join([
            f"- {ex['nom_produit']} → {ex['categorie']} (Similarité: {ex['score']:.2f})"
            for ex in top_k_products[:5]
        ])

        # Remplacer les placeholders dans le template
        prompt_final = prompt_template.replace("{titre_produit}", product['nom_produit'])
        prompt_final = prompt_final.replace("{description_produit}", product['description'])
        prompt_final = prompt_final.replace("{liste_categories}", formatted_categories)
        prompt_final = prompt_final.replace("{liste_produits}", formatted_products)

        return prompt_final

    async def query_llm_qwen(self, prompt: str, enable_thinking: bool = False) -> Dict:
        """Appel au LLM Qwen via gRPC"""
        if not QWEN_AVAILABLE:
            return {
                "success": False,
                "error": "Client gRPC Qwen non disponible",
                "error_type": "ImportError",
                "raw_response": {
                    "error": "Client gRPC Qwen non disponible",
                    "error_type": "ImportError"
                }
            }

        try:
            # Créer la requête ChatRequest pour Qwen
            chat_request = ChatRequest(
                prompt=prompt,
                temperature=0.0,
                max_tokens=256,  # Optimisé: réduit de 1024 → 256 (la réponse JSON est petite)
                enable_thinking=enable_thinking
            )

            # Appel gRPC asynchrone
            response_text = await llm_client.get_llm_chat_response(chat_request)

            # Vérification que la réponse contient du JSON valide
            # Note: response_text peut être du JSON brut ou du texte contenant du JSON
            # On le laisse tel quel pour que le parsing se fasse plus tard (ligne ~497)
            # Cela assure une cohérence avec OpenAI et DeepSeek

            # Créer un objet simulé similaire à OpenAI pour compatibilité
            class QwenResponse:
                def __init__(self, content):
                    self.choices = [type('obj', (object,), {
                        'message': type('obj', (object,), {'content': content})()
                    })()]

            qwen_response = QwenResponse(response_text)

            return {
                "success": True,
                "response": qwen_response,
                "raw_response": {
                    "model": "Qwen3-14B-AWQ",
                    "response_text": response_text
                }
            }

        except Exception as e:
            logger.error(f"Erreur lors de l'appel gRPC Qwen: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "raw_response": {
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "exception_details": str(e)
                }
            }

    async def query_llm(self, prompt: str, enable_thinking: bool = False) -> Dict:
        """Appel au LLM selon le choix (asynchrone pour supporter Qwen)"""
        messages = [{"role": "user", "content": prompt}]

        try:
            if self.llm_choice == 'Qwen':
                # Appel asynchrone à Qwen via gRPC
                return await self.query_llm_qwen(prompt, enable_thinking=enable_thinking)

            elif self.llm_choice == 'OpenAI' and self.openai_client:
                # Exécuter l'appel synchrone dans un thread pour ne pas bloquer
                response = await asyncio.to_thread(
                    self.openai_client.chat.completions.create,
                    model="gpt-4o-2024-05-13",
                    messages=messages,
                    temperature=0,
                    response_format={"type": "json_object"}
                )
                # Convertir en dictionnaire pour la sérialisation JSON
                raw_response_dict = response.model_dump() if hasattr(response, 'model_dump') else response.dict()
                return {"success": True, "response": response, "raw_response": raw_response_dict}

            elif self.llm_choice == 'DeepSeek' and self.deepseek_client:
                # Exécuter l'appel synchrone dans un thread pour ne pas bloquer
                response = await asyncio.to_thread(
                    self.deepseek_client.chat.completions.create,
                    model="deepseek-chat",
                    messages=messages,
                    temperature=0,
                    response_format={"type": "json_object"}
                )
                # Convertir en dictionnaire pour la sérialisation JSON
                raw_response_dict = response.model_dump() if hasattr(response, 'model_dump') else response.dict()
                return {"success": True, "response": response, "raw_response": raw_response_dict}
            else:
                raise ValueError(f"LLM {self.llm_choice} non configuré")

        except Exception as e:
            logger.error(f"Erreur LLM: {e}")
            # Capturer l'exception complète avec ses détails
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "raw_response": {
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "exception_details": str(e)
                }
            }

    async def classify_single(self, product: Dict, llm_override: Optional[str] = None, enable_thinking: bool = False) -> Dict:
        """Classifie un seul produit (asynchrone)"""
        start_time = time.time()

        # Gestion de l'override du LLM
        original_llm_choice = self.llm_choice
        original_openai_client = self.openai_client
        original_deepseek_client = self.deepseek_client

        if llm_override:
            try:
                self.llm_choice = llm_override
                self._initialize_clients()
            except Exception as e:
                logger.error(f"Erreur lors de l'initialisation du LLM override {llm_override}: {e}")
                # Restaurer les valeurs originales
                self.llm_choice = original_llm_choice
                self.openai_client = original_openai_client
                self.deepseek_client = original_deepseek_client
                return {
                    'id_produit': product['id_produit'],
                    'titre_produit': product.get('nom_produit', ''),
                    'description_produit': product.get('description', ''),
                    'status': 'ERROR',
                    'id_categorie': None,
                    'nom_categorie': None,
                    'score_llm': None,
                    'categorie_candidates': None,
                    'error': f'Erreur configuration LLM {llm_override}: {str(e)}',
                    'llm_type': llm_override,
                    'enable_thinking': enable_thinking,
                    'llm_response': None,
                    'processing_time': time.time() - start_time,
                    'input_tokens': 0,
                    'output_tokens': 0
                }

        try:
            # ⚡ OPTIMISATION: Recherche asynchrone de produits similaires (pipeline parallèle)
            similar_products = await self.search_similar_products_async(product['nom_produit'])
            if not similar_products:
                return {
                    'id_produit': product['id_produit'],
                    'titre_produit': product['nom_produit'],
                    'description_produit': product['description'],
                    'status': 'ERROR',
                    'id_categorie': None,
                    'nom_categorie': None,
                    'score_llm': None,
                    'categorie_candidates': None,
                    'error': 'Aucun produit similaire trouvé',
                    'llm_type': self.llm_choice,
                    'enable_thinking': enable_thinking,
                    'llm_response': None,
                    'processing_time': time.time() - start_time,
                    'input_tokens': 0,
                    'output_tokens': 0
                }

            # Groupement par catégorie (synchrone, rapide)
            categories = self.group_by_category(similar_products)
            if not categories:
                return {
                    'id_produit': product['id_produit'],
                    'titre_produit': product['nom_produit'],
                    'description_produit': product['description'],
                    'status': 'ERROR',
                    'id_categorie': None,
                    'nom_categorie': None,
                    'score_llm': None,
                    'categorie_candidates': None,
                    'error': 'Aucune catégorie trouvée',
                    'llm_type': self.llm_choice,
                    'enable_thinking': enable_thinking,
                    'llm_response': None,
                    'processing_time': time.time() - start_time,
                    'input_tokens': 0,
                    'output_tokens': 0
                }

            # ⚡ OPTIMISATION: Récupération asynchrone des descriptions avec résumé DeepSeek (pipeline parallèle)
            descriptions, summarization_tokens = await self.get_category_descriptions_async(categories)

            # Initialiser les compteurs de tokens
            total_input_tokens = summarization_tokens['input_tokens']
            total_output_tokens = summarization_tokens['output_tokens']

            # Construction du prompt et appel LLM (asynchrone)
            prompt = await self.build_prompt_async(product, categories, descriptions, similar_products)
            llm_result_wrapper = await self.query_llm(prompt, enable_thinking=enable_thinking)

            # Vérifier si l'appel LLM a échoué
            if not llm_result_wrapper.get('success', False):
                return {
                    'id_produit': product['id_produit'],
                    'titre_produit': product['nom_produit'],
                    'description_produit': product['description'],
                    'status': 'ERROR',
                    'id_categorie': None,
                    'nom_categorie': None,
                    'score_llm': None,
                    'categorie_candidates': self._format_categories_candidates(categories),
                    'error': llm_result_wrapper.get('error', 'Erreur LLM inconnue'),
                    'llm_type': self.llm_choice,
                    'enable_thinking': enable_thinking,
                    'llm_response': [llm_result_wrapper.get('raw_response')] if llm_result_wrapper.get('raw_response') else None,
                    'processing_time': time.time() - start_time,
                    'input_tokens': total_input_tokens,
                    'output_tokens': total_output_tokens
                }

            raw_llm = llm_result_wrapper['response']

            # Extraire les tokens de la réponse LLM (classification)
            llm_raw_response = llm_result_wrapper.get('raw_response', {})
            if 'usage' in llm_raw_response:
                total_input_tokens += llm_raw_response['usage'].get('prompt_tokens', 0)
                total_output_tokens += llm_raw_response['usage'].get('completion_tokens', 0)
            elif hasattr(raw_llm, 'usage'):
                total_input_tokens += getattr(raw_llm.usage, 'prompt_tokens', 0)
                total_output_tokens += getattr(raw_llm.usage, 'completion_tokens', 0)

            try:
                llm_result = json.loads(raw_llm.choices[0].message.content)
            except (AttributeError, KeyError, json.JSONDecodeError) as e:
                return {
                    'id_produit': product['id_produit'],
                    'titre_produit': product['nom_produit'],
                    'description_produit': product['description'],
                    'status': 'ERROR',
                    'id_categorie': None,
                    'nom_categorie': None,
                    'score_llm': None,
                    'categorie_candidates': self._format_categories_candidates(categories),
                    'error': f'Erreur parsing réponse LLM: {str(e)}',
                    'llm_type': self.llm_choice,
                    'enable_thinking': enable_thinking,
                    'llm_response': [llm_result_wrapper.get('raw_response')] if llm_result_wrapper.get('raw_response') else None,
                    'processing_time': time.time() - start_time,
                    'input_tokens': total_input_tokens,
                    'output_tokens': total_output_tokens
                }

            chosen_id = llm_result.get('id_categorie')
            score = llm_result.get('score', -1)

            if not chosen_id or score not in [0, 1]:
                return {
                    'id_produit': product['id_produit'],
                    'titre_produit': product['nom_produit'],
                    'description_produit': product['description'],
                    'status': 'ERROR',
                    'id_categorie': None,
                    'nom_categorie': None,
                    'score_llm': None,
                    'categorie_candidates': self._format_categories_candidates(categories),
                    'error': 'Réponse LLM invalide',
                    'llm_type': self.llm_choice,
                    'enable_thinking': enable_thinking,
                    'llm_response': [llm_result_wrapper.get('raw_response')] if llm_result_wrapper.get('raw_response') else None,
                    'processing_time': time.time() - start_time,
                    'input_tokens': total_input_tokens,
                    'output_tokens': total_output_tokens
                }

            # Trouver la catégorie choisie
            chosen_category = next((c for c in categories if str(c['id']) == str(chosen_id)), None)
            if not chosen_category:
                return {
                    'id_produit': product['id_produit'],
                    'titre_produit': product['nom_produit'],
                    'description_produit': product['description'],
                    'status': 'ERROR',
                    'id_categorie': None,
                    'nom_categorie': None,
                    'score_llm': None,
                    'categorie_candidates': self._format_categories_candidates(categories),
                    'error': f'Catégorie {chosen_id} introuvable',
                    'llm_type': self.llm_choice,
                    'enable_thinking': enable_thinking,
                    'llm_response': [llm_result_wrapper.get('raw_response')] if llm_result_wrapper.get('raw_response') else None,
                    'processing_time': time.time() - start_time,
                    'input_tokens': total_input_tokens,
                    'output_tokens': total_output_tokens
                }
            
            # Résultat final
            return {
                'id_produit': product['id_produit'],
                'titre_produit': product['nom_produit'],
                'description_produit': product['description'],
                'status': 'SUCCESS',
                'id_categorie': chosen_category['id'],
                'nom_categorie': chosen_category['name'],
                'score_llm': score,
                'categorie_candidates': self._format_categories_candidates(categories),
                'llm_type': self.llm_choice,
                'enable_thinking': enable_thinking,
                'processing_time': time.time() - start_time,
                'llm_response': [llm_result_wrapper.get('raw_response')] if llm_result_wrapper.get('raw_response') else None,
                'input_tokens': total_input_tokens,
                'output_tokens': total_output_tokens
            }
            
        except Exception as e:
            logger.error(f"Erreur classification produit {product['id_produit']}: {e}")
            return {
                'id_produit': product['id_produit'],
                'titre_produit': product.get('nom_produit', ''),
                'description_produit': product.get('description', ''),
                'status': 'ERROR',
                'id_categorie': None,
                'nom_categorie': None,
                'score_llm': None,
                'categorie_candidates': None,
                'error': str(e),
                'llm_type': self.llm_choice,
                'enable_thinking': enable_thinking,
                'llm_response': [f'Exception générale: {str(e)}'],
                'processing_time': time.time() - start_time,
                'input_tokens': 0,
                'output_tokens': 0
            }
        finally:
            # Restaurer le LLM original si un override était utilisé
            if llm_override:
                self.llm_choice = original_llm_choice
                self.openai_client = original_openai_client
                self.deepseek_client = original_deepseek_client

    async def classify_batch(self, products: List[Dict], llm_override: Optional[str] = None, enable_thinking: bool = False) -> Dict:
        """Classifie plusieurs produits en lot (asynchrone avec traitement parallèle)"""
        start_time = time.time()

        if not products:
            return {
                'total_produits': 0,
                'success_count': 0,
                'error_count': 0,
                'resultats': [],
                'llm_type': llm_override if llm_override else self.llm_choice,
                'processing_time_total': time.time() - start_time
            }

        # Créer une tâche asynchrone pour chaque produit
        tasks = [
            self.classify_single(product, llm_override=llm_override, enable_thinking=enable_thinking)
            for product in products
        ]

        # Exécuter toutes les tâches en parallèle et attendre leurs résultats
        results = await asyncio.gather(*tasks)

        # Compter les succès et les erreurs
        success_count = 0
        error_count = 0

        for result in results:
            if result['status'] == 'SUCCESS':
                success_count += 1
            else:
                error_count += 1
                logger.warning(f"Erreur produit {result['id_produit']}: {result.get('error', 'Inconnue')}")

        # Déterminer le llm_type réellement utilisé
        # Priorité 1: llm_override s'il est fourni
        # Priorité 2: llm_type du premier résultat
        # Priorité 3: self.llm_choice (fallback)
        actual_llm_type = llm_override if llm_override else (results[0].get('llm_type') if results else self.llm_choice)

        return {
            'total_produits': len(products),
            'success_count': success_count,
            'error_count': error_count,
            'resultats': results,
            'llm_type': actual_llm_type,
            'processing_time_total': time.time() - start_time
        }