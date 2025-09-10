# app/services/classifier.py
import json
import time
import logging
from typing import Dict, Any, List, Tuple, Optional
from collections import defaultdict

from .llm_client import LLMClient
from .search_api import call_search_api, get_product_details
from ..utils.text_processing import clean_text
from ..models import ProductInput, ClassificationResponse, LLMProvider
from ..exceptions import *
from ..handlers import ErrorHandler

logger = logging.getLogger(__name__)


class CombinedHit:
    """Classe pour représenter un résultat de recherche combiné"""
    def __init__(self, id: Any, distance: float, entity: Dict[str, Any]):
        self.id = id
        self.distance = distance
        self.entity = entity


class ProductClassifier:
    """
    Classificateur de produits utilisant l'API de recherche centralisée,
    un LLM (OpenAI/DeepSeek), et une stratégie de chunking.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.category_summary_cache = {}
        
        # Validation de la configuration
        self._validate_config()
        
        try:
            self.llm_client = LLMClient(config)
        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation des clients LLM: {e}")
            raise ConfigurationError("LLM_CLIENTS", "Impossible d'initialiser les clients LLM")
        
        # Initialisation du client Milvus
        # self.category_milvus_client = None
        # self._initialize_milvus()
    
    def _validate_config(self):
        """Valide la configuration requise"""
        required_fields = ['search_api_url', 'external_product_api_url']
        for field in required_fields:
            if not self.config.get(field):
                raise ConfigurationError(field, "URL requise manquante")
        
        # Validation des configurations LLM
        has_openai = bool(self.config.get('openai', {}).get('api_key'))
        has_deepseek = bool(self.config.get('deepseek', {}).get('api_key'))
        
        if not (has_openai or has_deepseek):
            raise ConfigurationError("LLM_API_KEYS", "Au moins une clé API LLM est requise")
    
    def get_available_llms(self) -> List[str]:
        """Retourne la liste des LLMs disponibles"""
        return self.llm_client.get_available_llms()
    
    def is_category_api_connected(self) -> bool:
        """Vérifie si l'API catégories est configurée"""
        return bool(self.config.get('external_category_api_url'))
    
    def classify_product(self, 
                        product: ProductInput, 
                        enhance_content: bool = True,
                        llm_provider: LLMProvider = LLMProvider.OPENAI,
                        n_similar: int = 50,
                        m_categories: int = 10,
                        k_products: int = 5) -> ClassificationResponse:
        """Classifie un seul produit avec gestion complète des erreurs"""
        start_time = time.time()
        request_id = getattr(logging.getLoggerClass().manager.loggerDict.get(__name__), 'request_id', 'unknown')
        
        try:
            # Validation des paramètres
            self._validate_classification_params(product, llm_provider, n_similar, m_categories, k_products)
            
            # Nettoyage et validation du texte
            title = clean_text(product.nom_produit)
            description = clean_text(product.description)
            
            if not title:
                raise ValidationError("nom_produit", "Le nom du produit ne peut pas être vide")
            
            logger.info(f"[{request_id}] Classification du produit: {product.id_produit}")
            
            # Amélioration du contenu si demandé
            if enhance_content and title and description:
                try:
                    enhanced_title, enhanced_description = self._enhance_product_info(
                        title, description, llm_provider
                    )
                    if enhanced_title != title or enhanced_description != description:
                        title, description = enhanced_title, enhanced_description
                        logger.debug(f"[{request_id}] Contenu amélioré avec succès")
                except Exception as e:
                    logger.warning(f"[{request_id}] Erreur lors de l'amélioration du contenu: {e}")
                    # Continue avec le contenu original
            
            # Recherche des produits similaires
            try:
                search_results = self._search_weighted(title, n_similar)
                if not search_results:
                    raise SearchAPIError("Aucun produit similaire trouvé")
                logger.debug(f"[{request_id}] {len(search_results)} produits similaires trouvés")
            except Exception as e:
                if isinstance(e, ClassificationAPIException):
                    raise
                else:
                    raise ErrorHandler.handle_requests_error(e, "API de recherche")
            
            # Groupement par catégorie
            category_groups = self._group_by_category(search_results)
            if not category_groups:
                raise ClassificationAPIException("Aucune catégorie trouvée parmi les produits similaires")
            
            # Calcul des scores agrégés
            aggregated_categories = self._calculate_aggregated_scores(category_groups)
            sorted_candidate_categories = sorted(aggregated_categories, key=lambda x: x['total_score'], reverse=True)
            
            top_m_cat_for_llm = sorted_candidate_categories[:m_categories]
            top_k_prod_for_llm = search_results[:k_products]
            
            # Préparation pour le LLM
            product_info = {'title': title, 'description': description}
            
            try:
                summarized_descriptions = self._get_and_summarize_category_descriptions(
                    top_m_cat_for_llm, llm_provider
                )
            except Exception as e:
                logger.warning(f"[{request_id}] Erreur lors du résumé des catégories: {e}")
                # Utilise des descriptions par défaut
                summarized_descriptions = {cat['id']: 'Description non disponible' for cat in top_m_cat_for_llm}
            
            messages = self._build_llm_prompt(
                product_info, top_m_cat_for_llm, summarized_descriptions, top_k_prod_for_llm
            )
            
            # Appel du LLM
            try:
                llm_json = self._call_llm(messages, llm_provider)
                logger.debug(f"[{request_id}] Réponse LLM reçue")
            except Exception as e:
                if isinstance(e, ClassificationAPIException):
                    raise
                else:
                    raise ErrorHandler.handle_openai_error(e, llm_provider.value)
            
            # Validation et traitement du résultat LLM
            chosen_id, llm_score = self._validate_llm_response(llm_json, top_m_cat_for_llm)
            
            chosen_category_data = next(
                (c for c in top_m_cat_for_llm if str(c['id']) == str(chosen_id)), None
            )
            
            status = "Validation Automatique (Score=1)" if llm_score == 1 else "Nécessite une revue manuelle (Score=0)"
            
            # Vérification de précision
            precision_check = None
            if product.id_categorie_attendue:
                predicted_category = chosen_category_data['id']
                expected_category = product.id_categorie_attendue
                precision_check = {
                    "expected": expected_category,
                    "predicted": predicted_category,
                    "is_correct": str(predicted_category) == str(expected_category)
                }
            
            processing_time = time.time() - start_time
            logger.info(f"[{request_id}] Classification terminée en {processing_time:.2f}s")
            
            return ClassificationResponse(
                id_produit=product.id_produit,
                status="SUCCESS",
                precision_check=precision_check,
                resultat_classification={
                    "id_categorie_choisie": chosen_category_data['id'],
                    "nom_categorie": chosen_category_data['name'],
                    "score_llm": llm_score,
                    "status": status,
                    "source_llm": llm_provider.value,
                    "titre_original": product.nom_produit,
                    "titre_utilise": title,
                    "description_utilisee": description[:100] + "..." if len(description) > 100 else description
                },
                contexte_fourni_au_llm={
                    "categories_candidates": [
                        {
                            "id": cat['id'],
                            "name": cat['name'],
                            "average_score": round(cat['average_score'], 3),
                            "total_score": round(cat['total_score'], 3),
                            "product_count": cat['product_count']
                        }
                        for cat in top_m_cat_for_llm
                    ],
                    "produits_similaires_montres": [
                        {
                            "nom": prod.entity.get('nom_produit', 'N/A'),
                            "categorie": prod.entity.get('categorie', 'N/A'),
                            "similarite": round(prod.distance, 3)
                        }
                        for prod in top_k_prod_for_llm
                    ]
                },
                processing_time_seconds=round(processing_time, 2)
            )
            
        except ClassificationAPIException:
            # Re-raise les exceptions personnalisées
            raise
        except Exception as e:
            processing_time = time.time() - start_time
            logger.exception(f"[{request_id}] Erreur inattendue lors de la classification du produit {product.id_produit}: {e}")
            return ClassificationResponse(
                id_produit=product.id_produit,
                status="ERROR",
                error=f"Erreur interne: {str(e)}",
                processing_time_seconds=processing_time
            )
    
    def _validate_classification_params(self, product: ProductInput, llm_provider: LLMProvider, 
                                       n_similar: int, m_categories: int, k_products: int):
        """Valide les paramètres de classification"""
        if not product.nom_produit or not product.nom_produit.strip():
            raise ValidationError("nom_produit", "Le nom du produit est requis")
        
        if llm_provider not in [LLMProvider.OPENAI, LLMProvider.DEEPSEEK]:
            available_llms = self.llm_client.get_available_llms()
            if llm_provider.value not in available_llms:
                raise ModelNotAvailableError(llm_provider.value)
        
        if not (10 <= n_similar <= 100):
            raise ValidationError("n_similar", "n_similar doit être entre 10 et 100")
        
        if not (3 <= m_categories <= 20):
            raise ValidationError("m_categories", "m_categories doit être entre 3 et 20")
        
        if not (0 <= k_products <= 15):
            raise ValidationError("k_products", "k_products doit être entre 0 et 15")
    
    def _validate_llm_response(self, llm_json: Dict[str, Any], top_categories: List[Dict]) -> Tuple[str, int]:
        """Valide la réponse du LLM"""
        if not isinstance(llm_json, dict):
            raise ClassificationAPIException("La réponse du LLM n'est pas un JSON valide")
        
        chosen_id = llm_json.get('id_categorie')
        if chosen_id is None:
            raise ClassificationAPIException("Le LLM n'a pas retourné d'id_categorie")
        
        try:
            llm_score = int(llm_json.get('score', -1))
        except (ValueError, TypeError):
            raise ClassificationAPIException("Le score du LLM n'est pas un entier valide")
        
        if llm_score not in [0, 1]:
            raise ClassificationAPIException(f"Score LLM invalide: {llm_score} (doit être 0 ou 1)")
        
        # Vérifier que l'ID de catégorie existe dans les candidats
        valid_ids = [str(cat['id']) for cat in top_categories]
        if str(chosen_id) not in valid_ids:
            raise ClassificationAPIException(f"ID de catégorie invalide retourné par le LLM: {chosen_id}")
        
        return chosen_id, llm_score
    
    def _search_weighted(self, query_text: str, n_val: int = 100) -> List[CombinedHit]:
        """Effectue une recherche de produits via l'API"""
        logger.info(f"Recherche pour '{query_text}' avec {n_val} résultats")
        
        raw_api_results = call_search_api(
            query_text, 
            num_results=n_val, 
            use_reranker=True, 
            reranker_model=self.config.get('bge_reranker_model', 'BAAI/bge-reranker-v2-m3'),
            search_api_url=self.config.get('search_api_url', '')
        )
        
        if not raw_api_results:
            logger.warning(f"Aucun résultat pour '{query_text}'")
            return []
        
        # Enrichissement avec les noms de produits
        unique_product_ids = set()
        for item in raw_api_results:
            prod_id = item.get('metadata', {}).get('id_produit')
            if prod_id:
                unique_product_ids.add(prod_id)
        
        product_name_map = {}
        if unique_product_ids:
            product_details = get_product_details(
                list(unique_product_ids), 
                self.config.get('external_product_api_url', '')
            )
            if product_details:
                product_name_map = {prod['id_produit']: prod['nom_produit'] for prod in product_details}
        
        # Création des CombinedHit
        combined_hits = []
        for item in raw_api_results:
            metadata = item.get('metadata', {})
            prod_id = metadata.get('id_produit')
            if not prod_id:
                continue
            
            product_name = product_name_map.get(prod_id, metadata.get('nom_produit', 'N/A'))
            
            entity_payload = {
                'id_produit': prod_id,
                'nom_produit': product_name,
                'categorie': metadata.get('categorie', 'N/A'),
                'id_categorie': metadata.get('id_categorie', 'N/A'),
                'chunk_number': metadata.get('chunk_number', 'N/A')
            }
            
            score = item.get('rerank_score', item.get('score', 0.0))
            hit = CombinedHit(id=prod_id, distance=score, entity=entity_payload)
            combined_hits.append(hit)
        
        return sorted(combined_hits, key=lambda h: h.distance, reverse=True)[:n_val]
    
    def _group_by_category(self, search_results: List[CombinedHit]) -> Dict:
        """Groupe les résultats par catégorie"""
        category_groups = defaultdict(lambda: {'name': '', 'hits': []})
        for hit in search_results:
            cat_id = hit.entity.get('id_categorie')
            cat_name = hit.entity.get('categorie')
            if cat_id and cat_name:
                category_groups[cat_id]['name'] = cat_name
                category_groups[cat_id]['hits'].append(hit)
        return category_groups
    
    def _calculate_aggregated_scores(self, category_groups: Dict) -> List[Dict]:
        """Calcule les scores agrégés par catégorie"""
        aggregated_categories = []
        for cat_id, group_data in category_groups.items():
            hits_in_group = group_data['hits']
            aggregated_categories.append({
                "id": group_data['name'],
                "name": cat_id,
                "average_score": sum(h.distance for h in hits_in_group) / len(hits_in_group),
                "total_score": sum(h.distance for h in hits_in_group),
                "product_count": len(hits_in_group)
            })
        return aggregated_categories
    
    def _enhance_product_info(self, title: str, description: str, llm_provider: LLMProvider) -> Tuple[str, str]:
        """Améliore les informations produit via LLM"""
        try:
            # Template de prompt pour l'amélioration
            prompt_text = f"""Améliore le titre et la description du produit suivant pour une meilleure classification. 
Garde les informations importantes mais rend le texte plus clair et structuré.

Titre actuel: {title}
Description actuelle: {description}

Retourne un JSON avec les clés "Titre" et "Description" contenant les versions améliorées."""
            
            messages = [{"role": "user", "content": prompt_text}]
            
            if llm_provider == LLMProvider.OPENAI:
                raw_json_string = self.llm_client.query_openai(messages)
            elif llm_provider == LLMProvider.DEEPSEEK:
                raw_json_string = self.llm_client.query_deepseek(messages)
            else:
                raise ValueError(f"LLM non supporté pour l'amélioration: {llm_provider}")
            
            json_response = json.loads(raw_json_string)
            enhanced_title = json_response.get("Titre", title)
            enhanced_description = json_response.get("Description", description)
            
            return enhanced_title, enhanced_description
            
        except Exception as e:
            logger.warning(f"Erreur lors de l'amélioration du contenu: {e}")
            return title, description
    
    def _get_and_summarize_category_descriptions(self, candidate_categories: List[Dict], llm_provider: LLMProvider) -> Dict[str, str]:
        """
        Récupère et résume les descriptions de catégories via l'API externe.
        MODIFIÉ: Utilise l'API externe au lieu de Milvus.
        """
        if not self.config.get('external_category_api_url'):
            logger.warning("URL de l'API catégories non configurée")
            return {c['id']: "Résumé non disponible (API catégories non configurée)." for c in candidate_categories}
        
        # Récupération des descriptions manquantes dans le cache
        ids_to_fetch = [c['id'] for c in candidate_categories if c['id'] not in self.category_summary_cache]
        
        if ids_to_fetch:
            try:
                logger.info(f"Récupération de {len(ids_to_fetch)} descriptions de catégories via API externe")
                
                # MODIFIÉ: Appel à l'API externe au lieu de Milvus
                from .search_api import get_category_details
                categories_data = get_category_details(
                    ids_to_fetch, 
                    self.config.get('external_category_api_url', '')
                )
                
                if categories_data:
                    # Création du mapping ID -> description
                    desc_map = {
                        item['id_categorie']: item.get('description_categorie', 'Description non disponible.') 
                        for item in categories_data
                    }
                    
                    # Génération des résumés via LLM
                    for cat_id in ids_to_fetch:
                        desc = desc_map.get(cat_id, "Description non disponible.")
                        prompt_messages = [{
                            "role": "user", 
                            "content": f"Résume en une phrase (20-25 mots) la description de catégorie suivante : \"{desc}\""
                        }]
                        
                        summary = "Erreur de résumé."
                        try:
                            if llm_provider == LLMProvider.OPENAI:
                                summary = self.llm_client.query_openai(prompt_messages, use_response_format=False)
                            elif llm_provider == LLMProvider.DEEPSEEK:
                                summary = self.llm_client.query_deepseek(prompt_messages, use_response_format=False)
                            
                            # Nettoyage du résumé
                            summary = summary.strip().strip('"\'')
                            self.category_summary_cache[cat_id] = summary
                            logger.debug(f"Résumé généré pour catégorie {cat_id}: {summary}")
                            
                        except Exception as e:
                            logger.warning(f"Erreur lors du résumé de la catégorie {cat_id}: {e}")
                            self.category_summary_cache[cat_id] = summary
                else:
                    logger.warning("Aucune donnée de catégorie reçue de l'API externe")
                    # Cache par défaut pour éviter les appels répétés
                    for cat_id in ids_to_fetch:
                        self.category_summary_cache[cat_id] = "Description non disponible (API externe)."
                        
            except Exception as e:
                logger.error(f"Erreur lors de la récupération des descriptions de catégories: {e}")
                # Cache par défaut en cas d'erreur
                for cat_id in ids_to_fetch:
                    self.category_summary_cache[cat_id] = "Description non disponible (erreur API)."
        
        return {cat['id']: self.category_summary_cache.get(cat['id'], 'N/A') for cat in candidate_categories}
    
    def _build_llm_prompt(self, product_info: Dict[str, str], candidate_categories: List[Dict], 
                         summarized_descriptions: Dict[str, str], top_k_products: List[CombinedHit]) -> List[Dict[str, str]]:
        """Construit le prompt pour le LLM"""
        formatted_categories = "\n".join([
            f"- ID: {cat['id']}, Nom: {cat['name']} (Score agrégé: {cat['total_score']:.2f} / Score moyenne : {cat['average_score']:.2f})\n  Description: {summarized_descriptions.get(cat['id'], 'N/A')}" 
            for cat in candidate_categories
        ])
        
        formatted_products = "Aucun exemple fourni."
        if top_k_products:
            product_lines = [
                f"- Titre: {prod.entity.get('nom_produit', 'N/A')}, Catégorie: {prod.entity.get('categorie', 'N/A')} (Similarité: {prod.distance:.2f})" 
                for prod in top_k_products
            ]
            formatted_products = "\n".join(product_lines)
        
        prompt_template = f"""Tu es un expert en classification de produits. Analyse le produit suivant et détermine sa catégorie la plus appropriée parmi les options proposées.

PRODUIT À CLASSIFIER:
Titre: {product_info['title']}
Description: {product_info['description']}

CATÉGORIES CANDIDATES (triées par pertinence):
{formatted_categories}

PRODUITS SIMILAIRES POUR RÉFÉRENCE:
{formatted_products}

INSTRUCTIONS:
1. Analyse le produit en tenant compte de ses caractéristiques principales
2. Compare avec les catégories candidates et leurs descriptions
3. Utilise les produits similaires comme référence
4. Choisis la catégorie la plus appropriée

RÉPONSE:
Retourne uniquement un JSON avec:
- "id_categorie": l'ID de la catégorie choisie (exactement comme fourni dans la liste)
- "score": 1 si tu es très confiant (>90% de certitude), 0 si tu as des doutes

Exemple: {{"id_categorie": "12345", "score": 1}}"""
        
        return [{"role": "user", "content": prompt_template}]
    
    def _call_llm(self, messages: List[Dict[str, str]], llm_provider: LLMProvider) -> Dict[str, Any]:
        """Appelle le LLM sélectionné"""
        if llm_provider == LLMProvider.OPENAI:
            raw_response = self.llm_client.query_openai(messages)
        elif llm_provider == LLMProvider.DEEPSEEK:
            raw_response = self.llm_client.query_deepseek(messages)
        else:
            raise ValueError(f"LLM non supporté: {llm_provider}")
        
        return json.loads(raw_response)
    
    def _parse_batch_input(self, batch_text: str) -> List[Dict[str, str]]:
        """
        Parse le texte d'entrée en format JSONL pour extraire les produits.
        Format attendu: ["id","nom_produit","description","id_categorie_attendue"]
        """
        products = []
        lines = batch_text.strip().split('\n')

        for i, line in enumerate(lines, 1):
            line = line.strip()
            if not line:
                continue

            try:
                # Essayer de parser comme JSON
                data = json.loads(line)

                # Vérifier que c'est une liste avec au moins 3 éléments
                if isinstance(data, list) and len(data) >= 3:
                    product = {
                        'id_produit': str(data[0]) if len(data) > 0 else f"prod_{i}",
                        'nom_produit': str(data[1]) if len(data) > 1 else "",
                        'description': str(data[2]) if len(data) > 2 else "",
                        'id_categorie_attendue': str(data[3]) if len(data) > 3 else None
                    }
                    products.append(product)
                else:
                    logger.warning(f"Ligne {i} ignorée : format invalide (doit être une liste avec au moins 3 éléments)")

            except json.JSONDecodeError as e:
                logger.warning(f"Ligne {i} ignorée : erreur JSON - {e}")
                continue

        return products
    
    def classify_batch(self, 
                      products: List[ProductInput],
                      enhance_content: bool = True,
                      llm_provider: LLMProvider = LLMProvider.OPENAI,
                      n_similar: int = 50,
                      m_categories: int = 10,
                      k_products: int = 5) -> List[ClassificationResponse]:
        """Classifie un lot de produits"""
        results = []
        
        for product in products:
            result = self.classify_product(
                product=product,
                enhance_content=enhance_content,
                llm_provider=llm_provider,
                n_similar=n_similar,
                m_categories=m_categories,
                k_products=k_products
            )
            results.append(result)
            
            # Petite pause pour éviter la surcharge
            time.sleep(0.1)
        
        return results