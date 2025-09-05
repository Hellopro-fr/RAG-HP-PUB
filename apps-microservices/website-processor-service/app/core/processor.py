import json

from bs4 import BeautifulSoup

from common_utils.autres.CollectionName import CollectionName
from common_utils.cleaner.TrafilaturaCleaning import TrafilaturaHp
from common_utils.extractor.HeaderFooterExtractor import HeaderFooterExtractor

def process_website_data_for_embedding(website_data: dict, bdd: str = "qdrant") -> dict:
    """
    Prend un dictionnaire de produit, le nettoie et prépare le message
    pour l’étape d’embedding.

    Retourne : Un dictionnaire prêt à être publié.
    """
    # Étape 0: Initialisation du message de sortie
    output_message = {}
    log = "l'embedding"
    
    # Étape 1: Vérifier les données d'entrée
    if not isinstance(website_data, dict):
        raise ValueError("Les données doivent être un dictionnaire.")
    
    # Étape 2: Vérifier si la présence du page_type == "header_footer" sinon on procède normalement
    if website_data.get("type_page","") == "header_footer":
        log = "la vérification de template"
        # Étape 2.1: Extraire le header et footer
        try:
            extractor = HeaderFooterExtractor(website_data.get("text",""))
            if not isinstance(extractor.soup, BeautifulSoup):
                raise ValueError("Le contenu HTML est invalide ou vide.")
            
            header = extractor.extract_header(extractor.soup)
            footer = extractor.extract_footer(extractor.soup)
            
            if not header and not footer:
                raise ValueError("Aucun header ou footer extrait.")
            
            text_to_embed_clean = f"{header} {footer}".strip()
        except Exception as e:
            raise ValueError(f"Erreur lors de l'extraction des Headers - Footer: {e}")
    else:  
        # Étape 2.1: Préparer le texte à embedder (À voir avec l'équipe en charge)
        info = {
            "url": website_data.get("url",""),
            "content": website_data.get("text",""),
            "fetch": False
        }

        # Étape 2.2: Nettoyer les données  
        trafila = TrafilaturaHp(info)
        res_clean = trafila.extract(info)
        text_to_embed_clean = res_clean.content
        
    # Étape 3: Construire le message de sortie
    output_message = {
        "data": {
            "text": text_to_embed_clean,
            # Todo: à modifier si nécessaire
            **{k.replace("-", "_"): v for k, v in website_data.items() if k not in ['text']}
        },
        "collection": CollectionName.SITEWEB,
        "database": bdd  
    }

    # Étape 4: Afficher le message de sortie pour débogage
    print(f"🔍Website-Processor: Message prêt pour {log}: {json.dumps(output_message, indent=2)}")
    
    # Étape 5: Retourner le message prêt à être publié
    print(f"📦 Website-Processor: Website traité pour embedding.")
    return output_message