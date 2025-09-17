import json
import logging
from typing import Optional, Dict, Any
from openai import OpenAI

import re

# --- CONFIGURATION ---

class ProductOptimizer:
    """Classe pour optimiser les produits scrappées."""
    
    def __init__(self, api_key: str):
        """
        Initialise l'optimiseur de produits.
        
        Args:
            api_key (str): Clé API OpenAI
        """
        self.client = OpenAI(api_key=api_key)
        self.model = "gpt-4o-2024-05-13"  # Vous pouvez changer pour gpt-4 si nécessaire
        
    def generate_prompt(self, data: Dict[str, Any]) -> str:
        """
        Génère le prompt pour OpenAI basé sur les données du produit.
        
        Args:
            data (Dict[str, Any]): Données du produit
            
        Returns:
            str: Prompt formaté
        """
        prompt = f"""
            # GOAL =
            Générer un contenu optimisé pour une fiche produit e-commerce . Il comprend :
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
            - Ne pas supprimer d'information du titre initial, sauf si clairement non pertinente (ex : "trtrtrtr","\\\\",...).
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
            - Tu as le droit de :
              - Corriger les ponctuations erronées (`?` → `,` ou `'`, etc.)
              - Mettre en gras (`<b>`) les mots, les passages et sections importants.
              - Ajouter des sauts de ligne (`<br>`), soulignages (`<u>`), puces HTML (`<ul><li>`) si utile.
              - Structurer les caractéristiques techniques en tableau HTML à 2 colonnes :
                - Colonne 1 : nom de la caractéristique en gras
                - Colonne 2 : valeur commencant en majuscule, même si ce n'est pas le cas dans le texte source.
              - Si le contenu contient des données multiples ou comparatives, générer un tableau HTML à plusieurs colonnes, avec un en-tête clair. Assure-toi que les valeurs soient bien alignées sur les bonnes colonnes pour une lecture fluide et précise.
              - Lorsque plusieurs lignes commencent par un tiret ou numérotation suivi d'un texte et d'un deux-points (ex. -texte : valeur), supprimer le tiret/numérotation. tu dois choisir de présenter ces informations sous forme de bullet points ou de tableau HTML ou les deux si nécessaires, selon ce qui rend la lecture la plus claire. Si un tableau est utilisé, afficher les données en deux colonnes sans inclure le tiret/numérotation ni le deux-points dans la première colonne. Si des bullet points sont utilisés, conserver le deux-points (:) après la clé, mais supprimer le tiret/numérotation au début.
              Exemple : "Hauteur :" ou "- Hauteur"  ou "1- Hauteur" ou "a) Hauteur"
              → devient simplement "Hauteur" si tableau HTML
              → devient simplement "Hauteur : " si bullet point
              - Supprimer uniquement les chaînes sans sens évident : "trtrtrtr", ">>>", etc.
              - Supprime les <br> ou sauts de ligne \\n qui sont excessifs, redondants ou mal placés.
              - Conserve uniquement les sauts de ligne nécessaires pour structurer visuellement la description et aérer le texte, sans excès.
              - Ne pas insérer plus de deux <br> consécutifs. Un <br> suffit généralement entre deux paragraphes.
              - Si le contenu est déjà bien espacé, n'ajoute pas de <br> supplémentaires.
              - N'utilise pas de bullet point <ul><li> s'il n'y a qu'un seul élément dans la liste. Utilise uniquement si au moins deux éléments consécutifs doivent être listés.
              - Imbriquer les balises HTML (ex. <strong>,<b> dans <li> ou <td>).
              - Les unités peuvent être normalisées (si présentes) sans être considérées comme une modification de fond.
              exemple : Ø 60.30" → "Diamètre : 60,30 mm"
            
            - Tu ne dois :
              - JAMAIS modifier l'ordre ou le fond des phrases.
              - JAMAIS ajouter de contenu.
              - JAMAIS reformuler ou resumer le texte de sortie.
            
            # FORMAT DE SORTIE OBLIGATOIRE =
            Tu dois répondre **uniquement** en JSON, sans aucune introduction ni commentaire, avec le format suivant :
            {{
              "Titre": "Ton titre généré ici",
              "Description": "Ta description mise en forme ici avec balises HTML"
            }}
            
            # INPUTS :
            CATEGORIE PRODUIT = {data.get('categorie_produit', '')}
            TITRE PRODUIT = {data.get('nom_produit', '')}
            DESCRIPTION PRODUIT = {data.get('description_produit', '')}
        """
        return prompt

    def optimize_product(self, product_data: Dict[str, Any]) -> Dict[str, str]:
        """
        Optimise un produit en utilisant OpenAI.
        
        Args:
            product_data (Dict[str, Any]): Données du produit
            
        Returns:
            Dict[str, str]: Titre et description optimisés
            
        Raises:
            Exception: Si l'API OpenAI échoue
        """
        try:
            prompt = self.generate_prompt(product_data)
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system", 
                        "content": "Tu es un expert en optimisation de contenu e-commerce. Tu suis scrupuleusement les instructions données et réponds uniquement en JSON valide."
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                temperature=0.3,  # Faible température pour plus de cohérence
                max_tokens=2000
            )
            
            # Extraction de la réponse
            content = response.choices[0].message.content.strip()
            
            # Nettoyage de la réponse si elle contient des backticks
            if content.startswith('```json'):
                content = content[7:-3]  # Supprime ```json et ```
            elif content.startswith('```'):
                content = content[3:-3]  # Supprime ``` et ```
            
            # Parse du JSON
            result = json.loads(content)
            
            # Validation du format de sortie
            if "Titre" not in result or "Description" not in result:
                raise ValueError("Format de réponse invalide - clés manquantes")
            
            return {
                "titre": result["Titre"],
                "description": result["Description"]
            }
            
        except json.JSONDecodeError as e:
            raise Exception(f"Réponse OpenAI invalide (JSON malformé): {str(e)}")
        except Exception as e:
            raise Exception(f"Erreur OpenAI: {str(e)}")
