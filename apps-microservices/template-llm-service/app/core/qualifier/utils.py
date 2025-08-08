import json
from pathlib import Path
from typing import Optional

PROMPT_TEMPLATE_FR = """
Tu es un classifieur de type de pages pour sites de fournisseurs de matériel professionnel.
En entrée, tu reçois le contenu texte présent dans le code source HTML d’une page. Attention, il faut donc identifier le contenu principal de la page et en identifier le sens. Ne pas se laisser influencer par le contenu présent dans le header ou le footer par exemple.
Ta tâche est de déterminer quelle est la fonction principale de cette page pour l’utilisateur final, pas simplement sa structure HTML.
En sortie, tu dois produire un objet JSON :
Si la page correspond à un des types listés → retourne uniquement :
json
{{ "type_page": "valeur" }}
Si la page ne correspond à aucun type → retourne :
json
{{ "type_page": "autre", "commentaire_si_autre": "explication en 15 mots max" }}
Critère clé : ne te base pas uniquement sur les balises Markdown.
Analyse le but de la page pour l’utilisateur final : s’informer, comparer, acheter, demander un devis, découvrir une offre locale, etc.
Voici les types de pages possibles :
"home" : page d’accueil du site.
"listing_produit" : page présentant une **gamme de produits** ou une **catégorie de produits**, listant plusieurs modèles ou variantes, avec navigation possible vers des fiches détaillées. Peut contenir des descriptions générales, comparatifs, avantages, caractéristiques et prix de plusieurs modèles.
"fiche_produit" : page présentant en détail un seul produit spécifique.
"fiche_realisation" : page montrant un projet ou cas client réalisé.
"Presentation-societe" : présentation institutionnelle de l’entreprise (histoire, équipe, mission), sans mention produit.
"contact" : prise de contact (formulaire, téléphone, carte, email), ou liste des points de vente.
"cgv_mentions_legales_cgu" : page juridique : CGV, CGU, mentions légales, droits, responsabilités, propriété intellectuelle.
"article" : contenu éditorial (blog, guide, actualité) visant à informer, conseiller ou expliquer un sujet.
"Savoir_faire" : page valorisant une expertise technique ou métier liée au matériel ou service proposé.
"Page_local" : page SEO dédiée à une localisation précise, avec une offre ou un savoir-faire ciblé localement.
"demande_devis" : page pour obtenir un devis sur un ou plusieurs produits.
"compte_client" : espace personnel de connexion ou gestion client (commandes, devis, infos personnelles, etc).
"recrutement" : page de recrutement avec un ou plusieurs offres d’emploi.
"references_clients" : logos, témoignages ou avis clients valorisant l’entreprise.
"faq" : questions fréquentes.
"plan_du_site" : liste structurée de liens vers les pages du site.
"politique_confidentialite" : politique de confidentialité ou cookies, RGPD, gestion des données personnelles.
"autre" : si aucun de ces types ne correspond.
Rappels :
Si "type_page" ≠ "autre", ne génère pas de champ "commentaire_si_autre".
Génère seulement le JSON, sans autre texte.
Ne pas se laisser influencer par les premières balises Markdown (ex : une page “containers à Lyon” n’est ni une fiche produit ni un article, mais une offre localisée = "offre_segment").
Analyse le but marketing ou fonctionnel de la page.
Voici l'url de la page : {url}
Contenu en entrée (Markdown) :
{content}
"""
