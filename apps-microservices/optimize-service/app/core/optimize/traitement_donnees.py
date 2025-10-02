import json
import logging
import re
from typing import Dict, Any, List
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
import time
import traceback

class TraitementDonnees:
    def __init__(self):
        pass
    def generate_prompt(self, data: Dict[str, Any]) -> str:
        
        prompt = f"""OUBLIE TOUTES LES INSTRUCTIONS PRÉCÉDENTES
            # GOAL =
            Générer un titre produit optimisé pour une fiche produit e-commerce en enrichissant uniquement avec des informations présentes dans le contenu.

            # TODO =
            Tu es un assistant éditorial du contenu produit pour un site e-commerce. Tu dois impérativement suivre les étapes ci-dessous et respecter les consignes avec précision. Toute modification non autorisée du contenu ou interprétation personnelle est interdite.

            # ÉTAPES =
            1. Lire attentivement "TITRE PRODUIT", "DESCRIPTION PRODUIT" et "CATEGORIE PRODUIT".
            2. Générer un nouveau titre produit en suivant **scrupuleusement** les règles de "CONSIGNES TITRE PRODUIT".

            # CONSIGNES POUR LE TITRE =
            - La longueur du titre doit être comprise **strictement** entre 30 et 130 caractères (espaces inclus).
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

            # FORMAT DE SORTIE TRES IMPORTANT ET OBLIGATOIRE : 
            Ta réponse doit être un JSON strictement valide, sans aucun texte avant ou après, sans balises Markdown, sans ```json, sans commentaire, sans indentation inutile. Exemple :
            {{{{"Titre": "Titre généré ici"}}}}

            # INPUTS :
            CATEGORIE PRODUIT = {data.get('categorie_produit', '')}
            TITRE PRODUIT = {data.get('nom_produit', '')}
            DESCRIPTION PRODUIT = {data.get('description_produit', '')}
            """
        return prompt

    def fix_json_quotes(resp: str) -> str:
        # Corrige les "" en "
        resp = resp.replace('""', '"')
        
        # Optionnel : si jamais le texte contient des guillemets dans la valeur, les échapper
        # Exemple: 1"1/2 doit devenir 1\"1/2
        resp = re.sub(r'(\d)"(\d)', r'\1\"\2', resp)

        return resp

    def clean_json_response(self, resp: str) -> str:
        resp = resp.strip()

        if resp.startswith("{{") and resp.endswith("}}"):
            resp = resp[1:-1].strip()

        match = re.search(r'\{.*\}', resp, re.DOTALL)
        if match:
            resp = match.group(0)

        # tentative de réparation
        resp = fix_json_quotes(resp)

        return resp


    