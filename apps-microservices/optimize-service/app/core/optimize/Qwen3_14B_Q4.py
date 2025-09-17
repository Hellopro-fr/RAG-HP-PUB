import json
import logging
from typing import Dict, Any
import torch
import re

class ProductOptimizerQwen:
    """Classe pour optimiser les produits scrappés avec Qwen3-14B en Q4."""

    def __init__(self, tokenizer=None, model=None):
        """
        Initialise l'optimiseur de produits avec un modèle et tokenizer pré-chargés.

        Args:
            tokenizer: Tokenizer Hugging Face pré-chargé
            model: Modèle Hugging Face pré-chargé
        """
        if tokenizer is None or model is None:
            raise ValueError("Le tokenizer et le modèle doivent être fournis")
            
        self.tokenizer = tokenizer
        self.model = model
        print("✓ ProductOptimizerQwen initialisé avec le modèle pré-chargé")

    def generate_prompt(self, data: Dict[str, Any]) -> str:
        """Génère le prompt pour le modèle basé sur les données du produit."""
        prompt = f"""OUBLIE TOUTES LES INSTRUCTIONS PRÉCÉDENTES
            # GOAL =
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
            - Ne pas supprimer d'information du titre initial, sauf si clairement non pertinente (ex : “trtrtrtr”,"\\\\",...).
            - Dans l'idéal, inclure le nom de la catégorie produit (ou son synonyme/similaire), la marque, la référence, les caractéristiques différenciantes si elles sont explicitement présentes.
            - Utiliser des tirets (-) quand nécessaire
            - Évite les majuscules excessives (max 40% du titre).
            - Ne pas ajouter d'usage ou avantage commercial sauf si déjà présent.
            - Ne jamais utiliser de balise HTML

            Exemple 1: Scierie LT15 Wood Mizer - essence ou diesel pour billes jusqu'à 70cm de diamètre et 5,4m de long
            Exemple 2: Bungalow démontable sur mesure de 2 à 12m de long, avec accouplement possible
            Exemple 3: Chaîne à galets d'accumulation en acier, avec maillon raccord

            # CONSIGNES POUR LA DESCRIPTION =
            - Ne modifier ou reformuler les phrases, sauf erreur évidente ou contenu manifestement inutile.
            - Si la description contient déjà du HTML, tu peux le conserver s'il est correct, sinon le corriger ou le structurer proprement.
            - Tu dois mettre en gras (`<b>`) les mots, les passages et sections importants.
            - Tu as le droit de :
            - Corriger les ponctuations erronées (`?` → `,` ou `’`, etc.)
            - Ajouter des sauts de ligne (`<br>`), soulignages (`<u>`), puces HTML (`<ul><li>`) si utile.
            - Structurer les caractéristiques techniques en tableau HTML à 2 colonnes :
                - Colonne 1 : nom de la caractéristique en gras
                - Colonne 2 : valeur commencant en majuscule, même si ce n’est pas le cas dans le texte source.
            - Si le contenu contient des données multiples ou comparatives, générer un tableau HTML à plusieurs colonnes, avec un en-tête clair. Assure-toi que les valeurs soient bien alignées sur les bonnes colonnes pour une lecture fluide et précise.
            - Lorsque plusieurs lignes commencent par un tiret ou numérotation suivi d'un texte et d'un deux-points (ex. -texte : valeur), supprimer le tiret/numérotation. tu dois choisir de présenter ces informations sous forme de bullet points ou de tableau HTML ou les deux si nécessaires, selon ce qui rend la lecture la plus claire. Si un tableau est utilisé, afficher les données en deux colonnes sans inclure le tiret/numérotation ni le deux-points dans la première colonne. Si des bullet points sont utilisés, conserver le deux-points (:) après la clé, mais supprimer le tiret/numérotation au début.
            Exemple : "Hauteur :" ou "- Hauteur"  ou "1- Hauteur" ou "a) Hauteur"
            → devient simplement "Hauteur" si tableau HTML
            → devient simplement "Hauteur : " si bullet point
            - Supprimer uniquement les chaînes sans sens évident : “trtrtrtr”, “>>>”, etc.
            - Supprime les <br> ou sauts de ligne \n qui sont excessifs, redondants ou mal placés.
            - Conserve uniquement les sauts de ligne nécessaires pour structurer visuellement la description et aérer le texte, sans excès.
            - Ne pas insérer plus de deux <br> ou sauts de ligne \n consécutifs. Un <br> ou /n suffit généralement entre deux paragraphes.
            - Si le contenu est déjà bien espacé, n'ajoute pas de <br> ou \n supplémentaires.
            - uniquement si au moins deux éléments consécutifs doivent être listés.
            - Imbriquer les balises HTML (ex. <strong>,<b> dans <li> ou <td>).
            - Les unités peuvent être normalisées (si présentes) sans être considérées comme une modification de fond.
            exemple : Ø 60.30" → "Diamètre : 60,30 mm"

            - Tu ne dois :
            - JAMAIS modifier l'ordre ou le fond des phrases.
            - JAMAIS ajouter de contenu.
            - JAMAIS reformuler ou resumer le texte de sortie.
            - JAMAIS utiliser un bullet point <ul><li> s'il n'y a qu'un seul élément dans la liste. Utilise 

            # FORMAT DE SORTIE OBLIGATOIRE =
            Tu dois répondre **uniquement** en JSON, sans aucune introduction ni commentaire, avec le format suivant :
            {{{{
            "Titre": "Ton titre généré ici",
            "Description": "Ta description mise en forme ici avec balises HTML"
            }}}}

            # INPUTS :
            CATEGORIE PRODUIT = {data.get('categorie_produit', '')}
            TITRE PRODUIT = {data.get('nom_produit', '')}
            DESCRIPTION PRODUIT = {data.get('description_produit', '')}

            Réponse JSON uniquement:"""
        return prompt

    def extract_json_from_text(self, text: str) -> str:
        """
        Extrait le JSON de la réponse du modèle avec plusieurs stratégies.
        
        Args:
            text (str): Texte brut contenant le JSON
            
        Returns:
            str: JSON extrait et nettoyé
        """
        # Stratégie 1: Chercher les blocs de code markdown
        json_patterns = [
            r'```json\s*(\{.*?\})\s*```',
            r'```\s*(\{.*?\})\s*```',
            r'(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})'
        ]
        
        for pattern in json_patterns:
            matches = re.findall(pattern, text, re.DOTALL)
            if matches:
                return matches[0].strip()
        
        # Stratégie 2: Chercher la première accolade ouvrante et la dernière fermante
        start = text.find('{')
        if start != -1:
            # Compter les accolades pour trouver la fermeture correcte
            brace_count = 0
            end = start
            for i, char in enumerate(text[start:], start):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end = i + 1
                        break
            
            if end > start:
                return text[start:end].strip()
        
        # Stratégie 3: Retourner le texte tel quel si rien trouvé
        return text.strip()

    def clean_json_string(self, json_str: str) -> str:
        """
        Nettoie la chaîne JSON des caractères problématiques.
        
        Args:
            json_str (str): Chaîne JSON à nettoyer
            
        Returns:
            str: Chaîne JSON nettoyée
        """
        # Supprimer les caractères de contrôle et espaces en trop
        json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', json_str)
        
        # Supprimer les sauts de ligne et espaces en trop au début/fin
        json_str = json_str.strip()
        
        # Supprimer les commentaires JavaScript/JSON
        json_str = re.sub(r'//.*$', '', json_str, flags=re.MULTILINE)
        json_str = re.sub(r'/\*.*?\*/', '', json_str, flags=re.DOTALL)
        
        return json_str

    def optimize_product(self, product_data: Dict[str, Any], max_new_tokens: int = 2000, temperature: float = 0.1) -> Dict[str, Any]:
        """
        Optimise un produit en utilisant Qwen3-14B.

        Args:
            product_data (Dict[str, Any]): Données du produit (doit contenir 'id')
            max_new_tokens (int): Nombre maximal de tokens générés
            temperature (float): Température pour la génération

        Returns:
            Dict[str, Any]: Résultat avec 'success' ou 'error'
        """
        product_id = product_data.get('id_produit_scrapping', '')
        
        try:
            prompt = self.generate_prompt(product_data)

            # Préparer les entrées
            inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)

            # Génération avec paramètres optimisés
            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=max_new_tokens,
                    temperature=temperature,
                    do_sample=True,
                    pad_token_id=self.tokenizer.eos_token_id,
                    eos_token_id=self.tokenizer.eos_token_id
                )

            # Décoder seulement la partie générée
            generated_text = self.tokenizer.decode(
                outputs[0][inputs['input_ids'].shape[1]:], 
                skip_special_tokens=True
            ).strip()

            print(f"Texte généré brut: {repr(generated_text)}")

            # Extraire et nettoyer le JSON
            json_content = self.extract_json_from_text(generated_text)
            json_content = self.clean_json_string(json_content)
            
            print(f"JSON extrait: {repr(json_content)}")

            # Tentative de parsing JSON
            result = None
            try:
                result = json.loads(json_content)
            except json.JSONDecodeError:
                # Tentative de correction automatique
                corrected_json = json_content
                corrected_json = re.sub(r'(\w+):', r'"\1":', corrected_json)
                corrected_json = re.sub(r':\s*([^",\{\}\[\]]+)(?=\s*[,\}])', r': "\1"', corrected_json)
                
                try:
                    result = json.loads(corrected_json)
                    print("JSON corrigé avec succès")
                except json.JSONDecodeError as e:
                    return {
                        'error': f"Format JSON invalide pour le produit {str(product_id)}: {str(e)}"
                    }

            # Vérifier la structure de la réponse
            if not isinstance(result, dict):
                return {
                    'error': f"Format de réponse invalide pour le produit {str(product_id)}: doit être un objet JSON"
                }
                
            if "Titre" not in result or "Description" not in result:
                return {
                    'error': f"Clés manquantes dans la réponse pour le produit {str(product_id)}. Clés trouvées: {list(result.keys())}"
                }

            # Validation des types et contenu
            titre = str(result["Titre"]).strip()
            description = str(result["Description"]).strip()
            
            if not titre or not description:
                return {
                    'error': f"Titre ou description vide pour le produit {str(product_id)}"
                }

            # Retourner le succès avec l'ID
            return {
                'success': {
                    'resume': {
                        'id': product_id,
                        'titre': titre,
                        'description': description
                    }
                }
            }

        except Exception as e:
            error_msg = f"Erreur lors du traitement du produit {str(product_id)}: {str(e)}"
            print(error_msg)
            logging.error(error_msg)
            return {
                'error': error_msg
            }

    def optimize_batch(self, products_list: list) -> list:
        """
        Optimise plusieurs produits en lot.
        
        Args:
            products_list (list): Liste de dictionnaires contenant les données produits
            
        Returns:
            list: Liste des résultats avec 'success' ou 'error'
        """
        results = []
        for i, product_data in enumerate(products_list):
            print(f"Traitement du produit {i+1}/{len(products_list)}")
            result = self.optimize_product(product_data)
            results.append(result)
        return results