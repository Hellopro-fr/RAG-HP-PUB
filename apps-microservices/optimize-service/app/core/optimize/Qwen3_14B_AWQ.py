import json
import logging
import re
from typing import Dict, Any
from vllm import LLM, SamplingParams

class ProductOptimizerQwen:
    def __init__(self):
        self.llm_args = {
            "model": "Qwen/Qwen3-14B-AWQ",
            "quantization": "awq",
            "gpu_memory_utilization": 0.85,
            "trust_remote_code": True,
            "dtype": "auto",
            "max_model_len": 8192
        }
        self.llm = LLM(**self.llm_args)
        self.tokenizer = self.llm.get_tokenizer()
    
    def generate_prompt(self, data: Dict[str, Any]) -> str:
        """Génère le prompt pour le modèle basé sur les données du produit."""
        # Échapper les caractères spéciaux dans les données d'entrée
        categorie = self.escape_for_prompt(data.get('categorie_produit', ''))
        nom = self.escape_for_prompt(data.get('nom_produit', ''))
        description = self.escape_for_prompt(data.get('description_produit', ''))
        
        prompt = f"""# GOAL =
Générer un contenu optimisé pour une fiche produit e-commerce. Il comprend :
1. Un titre produit amélioré en enrichissant uniquement avec des informations présentes dans le contenu.
2. Une version mise en forme HTML de la description produit, **sans changer le contenu ni la structure des phrases**.

# TODO =
Tu es un assistant éditorial du contenu produit pour un site e-commerce. Tu dois impérativement suivre les étapes ci-dessous et respecter les consignes avec précision. Toute modification non autorisée du contenu ou interprétation personnelle est interdite.

# ÉTAPES =
1. Lire attentivement "TITRE PRODUIT", "DESCRIPTION PRODUIT" et "CATEGORIE PRODUIT".
2. Générer un nouveau titre produit en suivant **scrupuleusement** les règles de "CONSIGNES TITRE PRODUIT".
3. Générer une version **mise en forme HTML** de la description produit, en respectant **strictement** les règles de "CONSIGNES DESCRIPTION PRODUIT".

# CONSIGNES POUR LE TITRE =
- Longueur entre 30 et 130 caractères.
- Tu dois uniquement réagencer ou enrichir le titre **avec des informations déjà présentes** dans "TITRE PRODUIT" ou "DESCRIPTION PRODUIT".
- Ne JAMAIS inventer, supposer ou extrapoler.
- Ne pas supprimer d'information du titre initial, sauf si clairement non pertinente (ex : "trtrtrtr","\\\\\\\\",...)
- Dans l'idéal, inclure le nom de la catégorie produit (ou son synonyme/similaire), la marque, la référence, les caractéristiques différenciantes si elles sont explicitement présentes.
- Utiliser des tirets (-) quand nécessaire
- Évite les majuscules excessives (max 40% du titre).
- Ne pas ajouter d'usage ou avantage commercial sauf si déjà présent.
- Ne jamais utiliser de balise HTML

# CONSIGNES POUR LA DESCRIPTION =
- Ne modifier ou reformuler les phrases, sauf erreur évidente ou contenu manifestement inutile.
- Si la description contient déjà du HTML, tu peux le conserver s'il est correct, sinon le corriger ou le structurer proprement.
- Tu as le droit de :
  - Corriger les ponctuations erronées
  - Mettre en gras les mots importants avec <b>
  - Ajouter des sauts de ligne avec <br>
  - Structurer les caractéristiques techniques en tableau HTML
  - Supprimer les chaînes sans sens évident
- Tu ne dois JAMAIS modifier l'ordre ou le fond des phrases.

# FORMAT DE SORTIE OBLIGATOIRE =
Tu dois répondre UNIQUEMENT en JSON valide, sans introduction ni commentaire :

{{"Titre": "titre optimisé ici", "Description": "description HTML ici"}}

# INPUTS :
CATEGORIE PRODUIT = {categorie}
TITRE PRODUIT = {nom}
DESCRIPTION PRODUIT = {description}

Réponse JSON uniquement :"""
        
        return prompt

    def escape_for_prompt(self, text: str) -> str:
        """Échapper les caractères spéciaux pour éviter les problèmes dans le prompt."""
        if not text:
            return ""
        
        # Remplacer les caractères problématiques
        text = text.replace('\n', ' ').replace('\r', ' ')
        text = text.replace('\t', ' ')
        text = re.sub(r'\s+', ' ', text)  # Normaliser les espaces multiples
        text = text.strip()
        
        return text

    def extract_json_from_text(self, text: str) -> str:
        """Extrait le JSON de la réponse du modèle avec plusieurs stratégies."""
        # Nettoyer le texte d'abord
        text = text.strip()
        
        # Stratégie 1: Chercher les blocs de code markdown
        json_patterns = [
            r'```json\s*(\{.*?\})\s*```',
            r'```\s*(\{.*?\})\s*```',
        ]
        
        for pattern in json_patterns:
            matches = re.findall(pattern, text, re.DOTALL)
            if matches:
                return matches[0].strip()
        
        # Stratégie 2: Chercher un objet JSON valide
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
        # Supprimer les caractères de contrôle
        json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', json_str)
        json_str = json_str.strip()
        
        # Supprimer les commentaires
        json_str = re.sub(r'//.*$', '', json_str, flags=re.MULTILINE)
        json_str = re.sub(r'/\*.*?\*/', '', json_str, flags=re.DOTALL)
        
        return json_str

    def fix_json_quotes(self, json_str: str) -> str:
        """Tente de réparer les guillemets non échappés dans le JSON."""
        try:
            # Essayer de parser d'abord
            json.loads(json_str)
            return json_str
        except json.JSONDecodeError as e:
            print(f"Tentative de réparation du JSON: {str(e)}")
            
            # Stratégie de réparation basique
            # Échapper les guillemets dans les valeurs de chaînes
            lines = json_str.split('\n')
            fixed_lines = []
            
            for line in lines:
                # Si la ligne contient une paire clé-valeur
                if ':' in line and '"' in line:
                    # Trouver la position du premier ':'
                    colon_pos = line.find(':')
                    key_part = line[:colon_pos]
                    value_part = line[colon_pos+1:]
                    
                    # Nettoyer la partie valeur
                    value_part = value_part.strip()
                    if value_part.startswith('"') and (value_part.endswith('"') or value_part.endswith('",') or value_part.endswith('"}')):
                        # Échapper les guillemets internes
                        if value_part.endswith('",'):
                            end_chars = '",'
                            content = value_part[1:-2]
                        elif value_part.endswith('"}'):
                            end_chars = '"}'
                            content = value_part[1:-2]
                        else:
                            end_chars = '"'
                            content = value_part[1:-1]
                        
                        # Échapper les guillemets dans le contenu
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
                print(f"Tentative {i + 1} échouée: {str(e)}")
                if i < len(attempts) - 1:
                    continue
                else:
                    # Dernière tentative : extraction manuelle
                    return self.extract_manually(json_str)
        
        return None

    def extract_manually(self, text: str) -> Dict[str, Any]:
        """Extraction manuelle en cas d'échec du parsing JSON."""
        try:
            # Chercher le titre
            titre_match = re.search(r'"Titre"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', text, re.DOTALL)
            description_match = re.search(r'"Description"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', text, re.DOTALL)
            
            result = {}
            
            if titre_match:
                result["Titre"] = titre_match.group(1).replace('\\"', '"')
            
            if description_match:
                result["Description"] = description_match.group(1).replace('\\"', '"')
            
            if result:
                print("Extraction manuelle réussie")
                return result
            
        except Exception as e:
            print(f"Erreur lors de l'extraction manuelle: {str(e)}")
        
        return None
    
    def optimize_product(self, product_data: Dict[str, Any], max_new_tokens: int = 2000, temperature: float = 0.1) -> Dict[str, Any]:
        product_id = product_data.get('id_produit_scrapping', 'unknown')
        
        try:
            prompt = self.generate_prompt(product_data)
            sampling_params = SamplingParams(
                max_tokens=800,  # Augmenté pour permettre des réponses plus complètes
                temperature=0.05,  # Réduit pour plus de consistance
                repetition_penalty=1.1,
                stop=["}}", "}\n}"]  # Arrêter à la fin du JSON
            )
            
            conversation = [{"role": "user", "content": prompt}]
            formatted_prompt = self.tokenizer.apply_chat_template(
                conversation, 
                tokenize=False, 
                add_generation_prompt=True,
                enable_thinking=False
            )
            
            final_prompt_tokens = self.tokenizer.encode(formatted_prompt)
            if len(final_prompt_tokens) >= self.llm_args["max_model_len"]:
                print(f"--- ERREUR CRITIQUE : Le prompt final ({len(final_prompt_tokens)} tokens) dépasse la limite de {self.llm_args['max_model_len']}. ---")
                return {"error": "erreur_prompt_trop_long"}
            
            outputs = self.llm.generate([formatted_prompt], sampling_params)
            raw_text = outputs[0].outputs[0].text.strip()
            
            print(f"Réponse brute du modèle pour le produit {product_id}:")
            print(raw_text)
            print("=" * 50)
            
            json_str = self.extract_json_from_text(raw_text)
            result = self.parse_json_safely(json_str)
            
            if result is None:
                error_msg = f"Impossible de parser le JSON pour le produit {product_id}"
                print(error_msg)
                print("JSON extrait:")
                print(json_str[:500] + "..." if len(json_str) > 500 else json_str)
                return {"error": error_msg}
            
            return {"success": result}
            
        except Exception as e:
            error_msg = f"Erreur lors du traitement du produit {product_id}: {str(e)}"
            print(error_msg)
            logging.error(error_msg)
            return {'error': error_msg}