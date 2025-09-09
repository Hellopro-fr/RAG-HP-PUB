import json
import logging
import re
from typing import Dict, Any, List
from vllm import LLM, SamplingParams
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
import time
import traceback

class ProductTitleOptimizerBatch:
    def __init__(self):
        self.llm_args = {
            "model": "Qwen/Qwen3-14B-AWQ",
            "quantization": "awq",
            "gpu_memory_utilization": 0.85,
            "trust_remote_code": True,
            "dtype": "auto",
            "max_model_len": 16384
        }
        self.llm = LLM(**self.llm_args)
        self.tokenizer = self.llm.get_tokenizer()
        self.batch_size = 1000  # Taille des lots
    
    # def clean_html_attributes(self, html_content: str) -> str:
    #     """
    #     Nettoie les attributs des balises HTML tout en conservant les balises elles-mêmes.
    #     """
    #     if not html_content:
    #         return html_content
            
    #     pattern = r'<(/?)(\w+)(?:\s+[^>]*)?>'
    #     cleaned_content = re.sub(pattern, r'<\1\2>', html_content)
        
    #     return cleaned_content
    
    # def clean_input_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        # """
        # Nettoie les données d'entrée, notamment la description produit.
        # """
        # cleaned_data = data.copy()
        
        # if 'description_produit' in cleaned_data and cleaned_data['description_produit']:
        #     cleaned_data['description_produit'] = self.clean_html_attributes(
        #         cleaned_data['description_produit']
        #     )
        
        # if 'nom_produit' in cleaned_data and cleaned_data['nom_produit']:
        #     cleaned_data['nom_produit'] = self.clean_html_attributes(
        #         cleaned_data['nom_produit']
        #     )
        # if 'categorie_produit' in cleaned_data and cleaned_data['categorie_produit']:
        #     cleaned_data['categorie_produit'] = self.clean_html_attributes(
        #         cleaned_data['categorie_produit']
        #     )
            
        # return cleaned_data
    
    def generate_prompt(self, data: Dict[str, Any]) -> str:
        """Génère le prompt pour le modèle basé sur les données du produit."""
        prompt = f"""OUBLIE TOUTES LES INSTRUCTIONS PRÉCÉDENTES
            # GOAL =
            Générer un titre produit optimisé pour une fiche produit e-commerce en enrichissant uniquement avec des informations présentes dans le contenu.

            # TODO =
            Tu es un assistant éditorial du contenu produit pour un site e-commerce. Tu dois impérativement suivre les étapes ci-dessous et respecter les consignes avec précision. Toute modification non autorisée du contenu ou interprétation personnelle est interdite.

            # ÉTAPES =
            1. Lire attentivement "TITRE PRODUIT", "DESCRIPTION PRODUIT" et "CATEGORIE PRODUIT".
            2. Générer un nouveau titre produit en suivant **scrupuleusement** les règles de "CONSIGNES TITRE PRODUIT".

            # CONSIGNES POUR LE TITRE =
            - Longueur entre 30 et 130 caractères.
            - Tu dois uniquement réagencer ou enrichir le titre **avec des informations déjà présentes** dans "TITRE PRODUIT" ou "DESCRIPTION PRODUIT".
            - Ne JAMAIS inventer, supposer ou extrapoler.
            - Ne pas supprimer d'information du titre initial, sauf si clairement non pertinente (ex : "trtrtrtr","\\\\",...).
            - Dans l'idéal, inclure le nom de la catégorie produit (ou son synonyme/similaire), la marque, la référence, les caractéristiques différenciantes si elles sont explicitement présentes.
            - Utiliser des tirets (-) quand nécessaire
            - Évite les majuscules excessives (max 40% du titre).
            - Ne pas ajouter d'usage ou avantage commercial sauf si déjà présent.
            - Ne jamais utiliser de balise HTML
            - Écrire toujours m² (surface) et m³ (volume) avec exposant et espace insécable (ex. : 45 m², 12 m³).
            - Ne jamais écrire m2, m3 ni ajouter de pluriel aux symboles.
            - Toujours conserver le type d'acquisition du produit (neuf, occasion, location) présent dans le titre initial.

            Exemple 1: Scierie LT15 Wood Mizer - essence ou diesel pour billes jusqu'à 70cm de diamètre et 5,4m de long
            Exemple 2: Bungalow démontable sur mesure de 2 à 12m de long, avec accouplement possible
            Exemple 3: Chaîne à galets d'accumulation en acier, avec maillon raccord

            # FORMAT DE SORTIE OBLIGATOIRE =
            Tu dois répondre **uniquement** en JSON, sans aucune introduction ni commentaire, avec le format suivant :
            {{{{
            "Titre": "Ton titre généré ici"
            }}}}

            # INPUTS :
            CATEGORIE PRODUIT = {data.get('categorie_produit', '')}
            TITRE PRODUIT = {data.get('nom_produit', '')}
            DESCRIPTION PRODUIT = {data.get('description_produit', '')}

            Réponse JSON uniquement:"""
        return prompt

    def escape_for_prompt(self, text: str) -> str:
        """Échapper les caractères spéciaux pour éviter les problèmes dans le prompt."""
        if not text:
            return ""
        
        text = text.replace('\n', ' ').replace('\r', ' ')
        text = text.replace('\t', ' ')
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
        
        return text

    def extract_json_from_text(self, text: str) -> str:
        """Extrait le JSON de la réponse du modèle avec plusieurs stratégies."""
        text = text.strip()
        
        json_patterns = [
            r'```json\s*(\{.*?\})\s*```',
            r'```\s*(\{.*?\})\s*```',
        ]
        
        for pattern in json_patterns:
            matches = re.findall(pattern, text, re.DOTALL)
            if matches:
                return matches[0].strip()
        
        start = text.find('{')
        if start != -1:
            brace_count = 0
            end = start
            in_string = False
            escape_next = False
            
            for i, char in enumerate(text[start:], start):
                if escape_next:
                    escape_next = False
                    continue
                    
                if char == '\\':
                    escape_next = True
                    continue
                    
                if char == '"' and not escape_next:
                    in_string = not in_string
                    
                if not in_string:
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            end = i + 1
                            break
            
            if end > start:
                return text[start:end].strip()
        
        return text.strip()

    def clean_json_string(self, json_str: str) -> str:
        """Nettoie la chaîne JSON des caractères problématiques."""
        json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', json_str)
        json_str = json_str.strip()
        
        json_str = re.sub(r'//.*$', '', json_str, flags=re.MULTILINE)
        json_str = re.sub(r'/\*.*?\*/', '', json_str, flags=re.DOTALL)
        
        return json_str

    def fix_json_quotes(self, json_str: str) -> str:
        """Tente de réparer les guillemets non échappés dans le JSON."""
        try:
            json.loads(json_str)
            return json_str
        except json.JSONDecodeError as e:
            print(f"Tentative de réparation du JSON: {type(e).__name__}: {str(e)}")
            
            lines = json_str.split('\n')
            fixed_lines = []
            
            for line in lines:
                if ':' in line and '"' in line:
                    colon_pos = line.find(':')
                    key_part = line[:colon_pos]
                    value_part = line[colon_pos+1:]
                    
                    value_part = value_part.strip()
                    if value_part.startswith('"') and (value_part.endswith('"') or value_part.endswith('",') or value_part.endswith('"}')):
                        if value_part.endswith('",'):
                            end_chars = '",'
                            content = value_part[1:-2]
                        elif value_part.endswith('"}'):
                            end_chars = '"}'
                            content = value_part[1:-2]
                        else:
                            end_chars = '"'
                            content = value_part[1:-1]
                        
                        content = content.replace('"', '\\"')
                        value_part = f'"{content}{end_chars}'
                    
                    line = key_part + ': ' + value_part
                
                fixed_lines.append(line)
            
            return '\n'.join(fixed_lines)

    def parse_json_safely(self, json_str: str) -> Dict[str, Any]:
        """Parse le JSON de manière sécurisée avec plusieurs tentatives."""
        attempts = [
            json_str,
            self.clean_json_string(json_str),
            self.fix_json_quotes(json_str),
            self.fix_json_quotes(self.clean_json_string(json_str))
        ]
        
        for i, attempt in enumerate(attempts):
            try:
                result = json.loads(attempt)
                if i > 0:
                    print(f"JSON parsé avec succès à la tentative {i + 1}")
                return result
            except json.JSONDecodeError as e:
                print(f"Tentative {i + 1} échouée: {type(e).__name__}: {str(e)}")
                if i < len(attempts) - 1:
                    continue
                else:
                    return self.extract_manually(json_str)
        
        return None

    def extract_manually(self, text: str) -> Dict[str, Any]:
        """Extraction manuelle en cas d'échec du parsing JSON."""
        try:
            titre_match = re.search(r'"Titre"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', text, re.DOTALL)
            
            result = {}
            
            if titre_match:
                result["Titre"] = titre_match.group(1).replace('\\"', '"')
            
            if result:
                print("Extraction manuelle réussie")
                return result
            
        except Exception as e:
            print(f"Erreur lors de l'extraction manuelle: {type(e).__name__}: {str(e)}")
            
        
        return None
    
    def optimize_single_product(self, product_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Optimise uniquement le titre d'un seul produit.
        """
        product_id = product_data.get('id_produit_scrapping', 'unknown')
        
        try:
            prompt = self.generate_prompt(product_data)
            sampling_params = SamplingParams(
                max_tokens=256,
                temperature=0.1,
                repetition_penalty=1.05,
                top_k=40,
                top_p=0.9,
                stop=["}", "}}", "}\n}"]
            )
            
            conversation = [{"role": "user", "content": prompt}]
            formatted_prompt = self.tokenizer.apply_chat_template(
                conversation, 
                tokenize=False, 
                add_generation_prompt=True,
                enable_thinking=False
            )
            
            final_prompt_tokens = self.tokenizer.encode(formatted_prompt)
            prompt_tokens = len(final_prompt_tokens)

            if prompt_tokens >= self.llm_args["max_model_len"]:
                print(f"--- ERREUR : Prompt trop long ({prompt_tokens} tokens) pour le produit {product_id} ---")
                return {
                    "id_produit_scrapping": product_id,
                    "error": "erreur_prompt_trop_long"
                }
            
            outputs = self.llm.generate([formatted_prompt], sampling_params)
            raw_text = outputs[0].outputs[0].text.strip()
            
            json_str = self.extract_json_from_text(raw_text)
            result = self.parse_json_safely(json_str)
            
            if result is None:
                return {
                    "id_produit_scrapping": product_id,
                    "error": f"Impossible de parser le JSON pour le produit {product_id}"
                }
            
            if "Titre" not in result:
                return {
                    "id_produit_scrapping": product_id,
                    "error": f"Titre manquant dans la réponse pour le produit {product_id}"
                }
            
            return {
                "id_produit_scrapping": product_id,
                "success": result
            }
            
        except Exception as e:
            error_msg = f"Erreur lors du traitement du produit {product_id}: {type(e).__name__}: {str(e)}"
            debug_msg = f"{error_msg}\nTraceback:\n{traceback.format_exc()}"
            print(debug_msg)
            logging.error(error_msg)
            return {
                "id_produit_scrapping": product_id,
                "error": error_msg
            }

    def optimize_batch_vllm(self, batch_products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Optimise un lot de produits en utilisant la génération par lot de vLLM.
        """
        try:
            print(f"---")
            print(f"Lancement de l'optimize pour le lot de {len(batch_products)} produits")
            
            # Préparation des prompts
            formatted_prompts = []
            product_ids = []
            
            for product_data in batch_products:
                product_id = product_data.get('id_produit_scrapping', 'unknown')
                product_ids.append(product_id)
                
                prompt = self.generate_prompt(product_data)
                conversation = [{"role": "user", "content": prompt}]
                formatted_prompt = self.tokenizer.apply_chat_template(
                    conversation, 
                    tokenize=False, 
                    add_generation_prompt=True,
                    enable_thinking=False
                )
                
                # Vérifier la longueur du prompt
                prompt_tokens = len(self.tokenizer.encode(formatted_prompt))
                if prompt_tokens >= self.llm_args["max_model_len"]:
                    print(f"Prompt trop long pour le produit {product_id}, ajout d'un prompt de fallback")
                    formatted_prompt = "Erreur: prompt trop long"
                
                formatted_prompts.append(formatted_prompt)
            
            # Génération par lot
            sampling_params = SamplingParams(
                max_tokens=256,
                temperature=0.1,
                repetition_penalty=1.05,
                top_k=40,
                top_p=0.9,
                stop=["}", "}}", "}\n}"]
            )
            
            start_time = time.time()
            outputs = self.llm.generate(formatted_prompts, sampling_params)
            print(f"Optimize terminée, traitement des résultats...")

            # Traitement des résultats
            results = []
            for i, output in enumerate(outputs):
                product_id = product_ids[i]
                
                if formatted_prompts[i] == "Erreur: prompt trop long":
                    results.append({
                        "id_produit_scrapping": product_id,
                        "error": "erreur_prompt_trop_long"
                    })
                    continue
                
                try:
                    raw_text = output.outputs[0].text.strip()
                    json_str = self.extract_json_from_text(raw_text)
                    result = self.parse_json_safely(json_str)
                    
                    if result is None or "Titre" not in result:
                        results.append({
                            "id_produit_scrapping": product_id,
                            "error": "Impossible de parser le JSON ou titre manquant"
                        })
                    else:
                        results.append({
                            "id_produit_scrapping": product_id,
                            "success": result
                        })
                        
                except Exception as e:
                    results.append({
                        "id_produit_scrapping": product_id,
                        "error": f"Erreur de traitement: {type(e).__name__}: {str(e)}"
                    })
            end_time = time.time()
            print(f"Génération du lot terminée en {end_time - start_time:.2f} secondes")
            return results
            
        except Exception as e:
            error_msg = f"Erreur lors du traitement du lot: {type(e).__name__}: {str(e)}"
            debug_msg = f"{error_msg}\nTraceback:\n{traceback.format_exc()}"
            print(debug_msg)
            logging.error(error_msg)
            # Retourner des erreurs pour tous les produits du lot
            return [
                {
                    "id_produit_scrapping": product.get('id_produit_scrapping', 'unknown'),
                    "error": error_msg
                } for product in batch_products
            ]

    def optimize_products_batch(self, products_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Optimise une liste de produits par lots de taille définie.
        """
        if not products_data:
            return []
        
        print(f"Début du traitement de {len(products_data)} produits")
        
        all_results = []
        total_batches = (len(products_data) + self.batch_size - 1) // self.batch_size
        
        for i in range(0, len(products_data), self.batch_size):
            batch_num = i // self.batch_size + 1
            batch = products_data[i:i + self.batch_size]
            
            try:
                batch_results = self.optimize_batch_vllm(batch)
                all_results.extend(batch_results)
                
                # print(f"Lot {batch_num} terminé avec succès")
                
            except Exception as e:
                error_msg = f"Erreur lors du lancement du lot {batch_num}: {type(e).__name__}: {str(e)}"
                debug_msg = f"{error_msg}\nTraceback:\n{traceback.format_exc()}"
                print(debug_msg)
                logging.error(error_msg)
                
                # Ajouter des erreurs pour tous les produits du lot
                batch_errors = [
                    {
                        "id_produit_scrapping": product.get('id_produit_scrapping', 'unknown'),
                        "error": error_msg
                    } for product in batch
                ]
                all_results.extend(batch_errors)
        
        # print(f"Traitement terminé. {len(all_results)} résultats générés.")
        return all_results

    # Maintien de la compatibilité avec l'ancienne méthode
    def optimize_product(self, product_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Optimise uniquement le titre du produit (version legacy pour compatibilité).
        """
        return self.optimize_single_product(product_data)