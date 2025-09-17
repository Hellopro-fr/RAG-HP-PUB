import os
import json
import time
import logging
from typing import Dict, List, Any, Optional
from collections import defaultdict

import openai

from .search import (
    call_search_api, 
    get_product_details, 
    get_category_details,
    EXTERNAL_PRODUCT_API_URL,
    EXTERNAL_CATEGORY_API_URL
)

logger = logging.getLogger(__name__)

class ProductClassifier:
    def __init__(self, llm_choice: str = 'DeepSeek'):
        self.llm_choice = llm_choice
        self.openai_client = None
        self.deepseek_client = None
        self.category_cache = {}
        self.search_results_limit = 30
        self.categories_limit = 10
        
        self._initialize_clients()
    
    def _initialize_clients(self):
        """Initialise les clients LLM"""
        if self.llm_choice == 'OpenAI':
            api_key = os.getenv('OPENAI_API_KEY')
            if api_key:
                self.openai_client = openai.OpenAI(api_key=api_key)
                logger.info("Client OpenAI configuré")
            else:
                raise ValueError("OPENAI_API_KEY manquante")
                
        elif self.llm_choice == 'DeepSeek':
            api_key = os.getenv('DEEPSEEK_API_KEY', "sk-6981c921e302498aaa85a13df198d6b3")
            if api_key:
                self.deepseek_client = openai.OpenAI(
                    api_key=api_key,
                    base_url="https://api.deepseek.com",
                    timeout=60
                )
                logger.info("Client DeepSeek configuré")
            else:
                raise ValueError("DEEPSEEK_API_KEY manquante")
    
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
    
    def is_llm_configured(self) -> bool:
        """Vérifie si un LLM est configuré"""
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

    def build_prompt(self, product: Dict, categories: List[Dict], descriptions: Dict, top_k_products: List[Dict]) -> str:
        """Construit le prompt pour le LLM"""
        formatted_categories = "\n".join([
            f"- ID: {cat['id']}, Nom: {cat['name']} (Score: {cat['total_score']:.2f})\n"
            f"  Description: {descriptions.get(cat['id'], 'N/A')}"
            for cat in categories[:self.categories_limit]
        ])
        
        formatted_products = "\n".join([
            f"- {ex['nom_produit']} → {ex['categorie']} (Similarité: {ex['score']:.2f})"
            for ex in top_k_products[:5]
        ])
        
        return f"""*** OUBLI TOUTES LES INSTRUCTIONS PRECEDENTES

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
Titre: {product['nom_produit']}
Description: {product['description']}
---
LISTE DES CATEGORIES (avec leur description) :
{formatted_categories}
---
EXEMPLES DE PRODUITS SIMILAIRES (pour contexte) :
{formatted_products}
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

    def query_llm(self, prompt: str) -> Dict:
        """Appel au LLM selon le choix"""
        messages = [{"role": "user", "content": prompt}]
        
        try:
            if self.llm_choice == 'OpenAI' and self.openai_client:
                response = self.openai_client.chat.completions.create(
                    model="gpt-4o-2024-05-13",
                    messages=messages,
                    temperature=0,
                    response_format={"type": "json_object"}
                )
                return json.loads(response.choices[0].message.content)
                
            elif self.llm_choice == 'DeepSeek' and self.deepseek_client:
                response = self.deepseek_client.chat.completions.create(
                    model="deepseek-chat",
                    messages=messages,
                    temperature=0,
                    response_format={"type": "json_object"}
                )
                return json.loads(response.choices[0].message.content)
            else:
                raise ValueError(f"LLM {self.llm_choice} non configuré")
                
        except Exception as e:
            logger.error(f"Erreur LLM: {e}")
            return {"id_categorie": None, "score": -1}

    def classify_single(self, product: Dict) -> Dict:
        """Classifie un seul produit"""
        start_time = time.time()
        
        try:
            # Recherche de produits similaires
            similar_products = self.search_similar_products(product['nom_produit'])
            if not similar_products:
                return {
                    'id_produit': product['id_produit'],
                    'status': 'ERROR',
                    'error': 'Aucun produit similaire trouvé',
                    'processing_time': time.time() - start_time
                }
            
            # Groupement par catégorie
            categories = self.group_by_category(similar_products)
            if not categories:
                return {
                    'id_produit': product['id_produit'],
                    'status': 'ERROR',
                    'error': 'Aucune catégorie trouvée',
                    'processing_time': time.time() - start_time
                }
            
            # Récupération des descriptions de catégories
            descriptions = self.get_category_descriptions(categories)
            
            # Construction du prompt et appel LLM
            prompt = self.build_prompt(product, categories, descriptions, similar_products)
            llm_result = self.query_llm(prompt)
            
            chosen_id = llm_result.get('id_categorie')
            score = llm_result.get('score', -1)
            
            if not chosen_id or score not in [0, 1]:
                return {
                    'id_produit': product['id_produit'],
                    'status': 'ERROR',
                    'error': 'Réponse LLM invalide',
                    'processing_time': time.time() - start_time
                }
            
            # Trouver la catégorie choisie
            chosen_category = next((c for c in categories if str(c['id']) == str(chosen_id)), None)
            if not chosen_category:
                return {
                    'id_produit': product['id_produit'],
                    'status': 'ERROR',
                    'error': f'Catégorie {chosen_id} introuvable',
                    'processing_time': time.time() - start_time
                }
            
            # Résultat final
            return {
                'id_produit': product['id_produit'],
                'status': 'SUCCESS',
                'id_categorie': chosen_category['id'],
                'nom_categorie': chosen_category['name'],
                'score_llm': score,
                'deepseek_response': llm_result,
                'processing_time': time.time() - start_time
            }
            
        except Exception as e:
            logger.error(f"Erreur classification produit {product['id_produit']}: {e}")
            return {
                'id_produit': product['id_produit'],
                'status': 'ERROR',
                'error': str(e),
                'processing_time': time.time() - start_time
            }

    def classify_batch(self, products: List[Dict]) -> Dict:
        """Classifie plusieurs produits en lot"""
        start_time = time.time()
        results = []
        success_count = 0
        error_count = 0
        
        for product in products:
            result = self.classify_single(product)
            results.append(result)
            
            if result['status'] == 'SUCCESS':
                success_count += 1
            else:
                error_count += 1
                logger.warning(f"Erreur produit {result['id_produit']}: {result.get('error', 'Inconnue')}")
        
        return {
            'total_produits': len(products),
            'success_count': success_count,
            'error_count': error_count,
            'resultats': results,
            'processing_time_total': time.time() - start_time
        }