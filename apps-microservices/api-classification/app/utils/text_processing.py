# app/utils/text_processing.py
import re
import html
import unicodedata
import logging
from typing import Any, Optional, List, Tuple, Dict
import ftfy

logger = logging.getLogger(__name__)

class TextProcessor:
    """Classe utilitaire pour le traitement et nettoyage de texte"""
    
    # Patterns de nettoyage courants
    WHITESPACE_PATTERN = re.compile(r'\s+')
    HTML_TAG_PATTERN = re.compile(r'<[^<]+?>')
    SPECIAL_CHARS_PATTERN = re.compile(r'[^\w\s\-\.\,\!\?\:\;\(\)\[\]\'\"\/\%\&\@\#\+\=\>\<]')
    MULTIPLE_PUNCTUATION_PATTERN = re.compile(r'([.!?]){2,}')
    PRICE_PATTERN = re.compile(r'\d+[.,]?\d*\s*[€$£¥]\s*|\d+\s*(?:euros?|dollars?|pound|yen)', re.IGNORECASE)
    DIMENSION_PATTERN = re.compile(r'\d+[.,]?\d*\s*(?:mm?|cm?|km?|inch|ft|m)\b', re.IGNORECASE)
    
    # Caractères à supprimer ou remplacer
    UNWANTED_CHARS = {
        '\u00a0': ' ',  # Non-breaking space
        '\u2019': "'",  # Right single quotation mark
        '\u2018': "'",  # Left single quotation mark
        '\u201c': '"',  # Left double quotation mark
        '\u201d': '"',  # Right double quotation mark
        '\u2013': '-',  # En dash
        '\u2014': '-',  # Em dash
        '\u2026': '...',  # Horizontal ellipsis
        '\u00e9': 'e',  # é
        '\u00e8': 'e',  # è
        '\u00ea': 'e',  # ê
        '\u00e0': 'a',  # à
        '\u00e2': 'a',  # â
        '\u00e7': 'c',  # ç
        '\u00f9': 'u',  # ù
        '\u00fb': 'u',  # û
        '\u00ee': 'i',  # î
        '\u00f4': 'o',  # ô
    }
    
    @staticmethod
    def clean_text(text: Any, 
                   fix_encoding: bool = True,
                   remove_html: bool = True,
                   normalize_whitespace: bool = True,
                   normalize_unicode: bool = True,
                   remove_special_chars: bool = False,
                   max_length: Optional[int] = None) -> str:
        """
        Nettoie et normalise le texte de manière complète.
        
        Args:
            text: Texte à nettoyer (peut être n'importe quel type)
            fix_encoding: Corrige les problèmes d'encodage
            remove_html: Supprime les balises HTML
            normalize_whitespace: Normalise les espaces
            normalize_unicode: Normalise les caractères Unicode
            remove_special_chars: Supprime les caractères spéciaux
            max_length: Longueur maximale du texte
        
        Returns:
            Texte nettoyé
        """
        if not isinstance(text, str):
            if text is None:
                return ""
            text = str(text)
        
        if not text.strip():
            return ""
        
        try:
            # 1. Correction d'encodage avec ftfy
            if fix_encoding:
                text = TextProcessor._fix_encoding(text)
            
            # 2. Suppression des balises HTML
            if remove_html:
                text = TextProcessor._remove_html_tags(text)
            
            # 3. Décodage des entités HTML
            text = html.unescape(text)
            
            # 4. Normalisation Unicode
            if normalize_unicode:
                text = TextProcessor._normalize_unicode(text)
            
            # 5. Remplacement des caractères problématiques
            text = TextProcessor._replace_unwanted_chars(text)
            
            # 6. Suppression des caractères spéciaux si demandé
            if remove_special_chars:
                text = TextProcessor._remove_special_chars(text)
            
            # 7. Normalisation des espaces
            if normalize_whitespace:
                text = TextProcessor._normalize_whitespace(text)
            
            # 8. Nettoyages finaux
            text = TextProcessor._final_cleanup(text)
            
            # 9. Limitation de longueur
            if max_length and len(text) > max_length:
                text = text[:max_length].rsplit(' ', 1)[0] + "..."
            
            return text.strip()
            
        except Exception as e:
            logger.error(f"Erreur lors du nettoyage du texte: {e}")
            return str(text) if text else ""
    
    @staticmethod
    def _fix_encoding(text: str) -> str:
        """Corrige les problèmes d'encodage courants"""
        try:
            # Utilise ftfy pour corriger automatiquement les problèmes d'encodage
            fixed = ftfy.fix_text(text)
            
            # Correction manuelle pour les cas spécifiques
            encodings_to_try = [
                ('latin-1', 'utf-8'),
                ('cp1252', 'utf-8'),
                ('iso-8859-1', 'utf-8')
            ]
            
            for from_enc, to_enc in encodings_to_try:
                try:
                    # Test si le texte peut être encodé puis décodé
                    test_encode = text.encode(from_enc)
                    test_decode = test_encode.decode(to_enc)
                    if '�' not in test_decode and len(test_decode) > len(fixed):
                        fixed = test_decode
                        break
                except (UnicodeEncodeError, UnicodeDecodeError):
                    continue
            
            return fixed
            
        except Exception:
            return text
    
    @staticmethod
    def _remove_html_tags(text: str) -> str:
        """Supprime les balises HTML"""
        # Suppression des balises HTML courantes
        text = TextProcessor.HTML_TAG_PATTERN.sub(' ', text)
        
        # Nettoyage des balises mal fermées
        text = re.sub(r'<[^>]*$', '', text)  # Balise non fermée en fin
        text = re.sub(r'^[^<]*>', '', text)  # Balise non ouverte au début
        
        return text
    
    @staticmethod
    def _normalize_unicode(text: str) -> str:
        """Normalise les caractères Unicode"""
        # Normalisation NFD pour séparer les caractères et leurs accents
        text = unicodedata.normalize('NFD', text)
        
        # Option: supprimer complètement les accents (décommenter si nécessaire)
        # text = ''.join(char for char in text if unicodedata.category(char) != 'Mn')
        
        # Re-normalisation en NFC
        text = unicodedata.normalize('NFC', text)
        
        return text
    
    @staticmethod
    def _replace_unwanted_chars(text: str) -> str:
        """Remplace les caractères problématiques"""
        for old_char, new_char in TextProcessor.UNWANTED_CHARS.items():
            text = text.replace(old_char, new_char)
        
        return text
    
    @staticmethod
    def _remove_special_chars(text: str) -> str:
        """Supprime les caractères spéciaux non désirés"""
        # Garde les caractères alphanumériques et la ponctuation de base
        text = TextProcessor.SPECIAL_CHARS_PATTERN.sub(' ', text)
        return text
    
    @staticmethod
    def _normalize_whitespace(text: str) -> str:
        """Normalise les espaces blancs"""
        # Remplacement des espaces multiples par un seul
        text = TextProcessor.WHITESPACE_PATTERN.sub(' ', text)
        
        # Suppression des espaces en début et fin de ligne
        lines = [line.strip() for line in text.split('\n')]
        text = '\n'.join(line for line in lines if line)
        
        return text
    
    @staticmethod
    def _final_cleanup(text: str) -> str:
        """Nettoyages finaux"""
        # Normalisation de la ponctuation multiple
        text = TextProcessor.MULTIPLE_PUNCTUATION_PATTERN.sub(r'\1', text)
        
        # Suppression des espaces avant la ponctuation
        text = re.sub(r'\s+([,.!?;:])', r'\1', text)
        
        # Ajout d'espace après la ponctuation si nécessaire
        text = re.sub(r'([,.!?;:])([^\s\d])', r'\1 \2', text)
        
        return text

class ProductTextProcessor(TextProcessor):
    """Processeur de texte spécialisé pour les descriptions de produits"""
    
    # Patterns spécifiques aux produits
    BRAND_INDICATORS = ['marque', 'brand', 'fabricant', 'manufacturer']
    MODEL_INDICATORS = ['modèle', 'model', 'référence', 'ref', 'code']
    SPEC_SEPARATORS = ['-', '|', '/', '•', '·', '–', '—']
    
    @staticmethod
    def extract_product_features(text: str) -> Dict[str, List[str]]:
        """
        Extrait les caractéristiques clés d'un texte de produit.
        
        Returns:
            Dict avec les caractéristiques extraites par catégorie
        """
        features = {
            'dimensions': [],
            'prices': [],
            'specifications': [],
            'brands': [],
            'models': []
        }
        
        # Extraction des dimensions
        dimensions = TextProcessor.DIMENSION_PATTERN.findall(text)
        features['dimensions'] = [dim.strip() for dim in dimensions]
        
        # Extraction des prix
        prices = TextProcessor.PRICE_PATTERN.findall(text)
        features['prices'] = [price.strip() for price in prices]
        
        # Extraction des spécifications (valeurs numériques avec unités)
        spec_pattern = r'\d+[.,]?\d*\s*(?:v|w|a|kg|g|l|ml|bar|psi|rpm|°c|hz)\b'
        specs = re.findall(spec_pattern, text, re.IGNORECASE)
        features['specifications'] = [spec.strip() for spec in specs]
        
        return features
    
    @staticmethod
    def clean_product_title(title: str) -> str:
        """Nettoie spécifiquement un titre de produit"""
        if not title:
            return ""
        
        # Nettoyage de base
        title = TextProcessor.clean_text(
            title, 
            fix_encoding=True,
            remove_html=True,
            normalize_whitespace=True,
            max_length=200  # Limite pour les titres
        )
        
        # Suppression des codes produits en début/fin
        title = re.sub(r'^[A-Z0-9\-_]{6,}\s*[:\-]?\s*', '', title)
        title = re.sub(r'\s*[:\-]?\s*[A-Z0-9\-_]{6,}$', '', title)
        
        # Suppression des mentions de stock/disponibilité
        stock_pattern = r'\b(?:en stock|disponible|livraison|expédition|délai).*$'
        title = re.sub(stock_pattern, '', title, flags=re.IGNORECASE)
        
        return title.strip()
    
    @staticmethod
    def clean_product_description(description: str, max_length: int = 2000) -> str:
        """Nettoie spécifiquement une description de produit"""
        if not description:
            return ""
        
        # Nettoyage de base
        description = TextProcessor.clean_text(
            description,
            fix_encoding=True,
            remove_html=True,
            normalize_whitespace=True,
            max_length=max_length
        )
        
        # Suppression des sections non pertinentes
        unwanted_sections = [
            r'livraison.*?(?=\n|\.|$)',
            r'retour.*?(?=\n|\.|$)',
            r'garantie.*?(?=\n|\.|$)',
            r'condition.*?(?=\n|\.|$)',
            r'politique.*?(?=\n|\.|$)',
            r'avis.*?(?=\n|\.|$)',
            r'évaluation.*?(?=\n|\.|$)'
        ]
        
        for pattern in unwanted_sections:
            description = re.sub(pattern, '', description, flags=re.IGNORECASE | re.DOTALL)
        
        # Nettoyage des listes mal formatées
        description = re.sub(r'^[-•·]\s*', '', description, flags=re.MULTILINE)
        
        # Suppression des URLs
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        description = re.sub(url_pattern, '', description)
        
        return description.strip()
    
    @staticmethod
    def standardize_units(text: str) -> str:
        """Standardise les unités de mesure dans le texte"""
        unit_replacements = {
            # Longueur
            r'\b(\d+)\s*mm\b': r'\1mm',
            r'\b(\d+)\s*cm\b': r'\1cm',
            r'\b(\d+)\s*m\b(?!\w)': r'\1m',
            
            # Poids
            r'\b(\d+)\s*kg\b': r'\1kg',
            r'\b(\d+)\s*g\b(?!\w)': r'\1g',
            
            # Volume
            r'\b(\d+)\s*l\b(?!\w)': r'\1L',
            r'\b(\d+)\s*ml\b': r'\1mL',
            
            # Électrique
            r'\b(\d+)\s*v\b(?!\w)': r'\1V',
            r'\b(\d+)\s*w\b(?!\w)': r'\1W',
            r'\b(\d+)\s*a\b(?!\w)': r'\1A',
            
            # Pression
            r'\b(\d+)\s*bar\b': r'\1 bar',
            r'\b(\d+)\s*psi\b': r'\1 PSI',
        }
        
        for pattern, replacement in unit_replacements.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        
        return text

def clean_text(text: Any, **kwargs) -> str:
    """Fonction principale de nettoyage - interface simple"""
    return TextProcessor.clean_text(text, **kwargs)

def clean_product_text(title: str, description: str) -> Tuple[str, str]:
    """
    Nettoie à la fois le titre et la description d'un produit.
    
    Returns:
        Tuple (titre_nettoyé, description_nettoyée)
    """
    cleaned_title = ProductTextProcessor.clean_product_title(title)
    cleaned_description = ProductTextProcessor.clean_product_description(description)
    
    return cleaned_title, cleaned_description

def extract_keywords(text: str, min_length: int = 3, max_keywords: int = 20) -> List[str]:
    """
    Extrait les mots-clés importants d'un texte.
    
    Args:
        text: Texte source
        min_length: Longueur minimale des mots-clés
        max_keywords: Nombre maximum de mots-clés à retourner
    
    Returns:
        Liste des mots-clés extraits
    """
    if not text:
        return []
    
    # Nettoyage du texte
    clean = clean_text(text, remove_special_chars=True)
    
    # Suppression des mots vides (stop words) français et anglais
    stop_words = {
        'le', 'de', 'et', 'à', 'un', 'il', 'être', 'et', 'en', 'avoir', 'que', 'pour',
        'dans', 'ce', 'son', 'une', 'sur', 'avec', 'ne', 'se', 'pas', 'tout', 'plus',
        'par', 'grand', 'comme', 'dans', 'leur', 'bien', 'autre', 'après', 'premier',
        'temps', 'très', 'état', 'où', 'aller', 'voir', 'sans', 'deux', 'nous', 'ces',
        'the', 'be', 'to', 'of', 'and', 'a', 'in', 'that', 'have', 'i', 'it', 'for',
        'not', 'on', 'with', 'as', 'you', 'do', 'at', 'this', 'but', 'his', 'by',
        'from', 'they', 'we', 'say', 'her', 'she', 'or', 'an', 'will', 'my', 'one',
        'all', 'would', 'there', 'their', 'what', 'so', 'up', 'out', 'if', 'about'
    }
    
    # Extraction des mots
    words = re.findall(r'\b[a-zA-Zàâäéèêëïîôùûüÿç]+\b', clean.lower())
    
    # Filtrage et comptage
    filtered_words = [
        word for word in words 
        if len(word) >= min_length and word not in stop_words
    ]
    
    # Comptage des fréquences
    word_freq = {}
    for word in filtered_words:
        word_freq[word] = word_freq.get(word, 0) + 1
    
    # Tri par fréquence et retour des top mots-clés
    sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
    keywords = [word for word, freq in sorted_words[:max_keywords]]
    
    return keywords

def validate_product_text(title: str, description: str) -> Dict[str, Any]:
    """
    Valide la qualité d'un titre et description de produit.
    
    Returns:
        Dict avec les résultats de validation
    """
    validation = {
        'title_valid': True,
        'description_valid': True,
        'issues': [],
        'suggestions': []
    }
    
    # Validation du titre
    if not title or not title.strip():
        validation['title_valid'] = False
        validation['issues'].append("Titre manquant")
    elif len(title.strip()) < 10:
        validation['title_valid'] = False
        validation['issues'].append("Titre trop court (minimum 10 caractères)")
    elif len(title) > 200:
        validation['issues'].append("Titre très long (recommandé: < 200 caractères)")
        validation['suggestions'].append("Raccourcir le titre")
    
    # Validation de la description
    if not description or not description.strip():
        validation['description_valid'] = False
        validation['issues'].append("Description manquante")
    elif len(description.strip()) < 20:
        validation['description_valid'] = False
        validation['issues'].append("Description trop courte (minimum 20 caractères)")
    elif len(description) > 5000:
        validation['issues'].append("Description très longue (recommandé: < 5000 caractères)")
        validation['suggestions'].append("Raccourcir la description")
    
    # Vérifications de qualité
    if title and re.search(r'[A-Z]{5,}', title):
        validation['suggestions'].append("Éviter les majuscules excessives dans le titre")
    
    if description and len(re.findall(r'[.!?]', description)) == 0:
        validation['suggestions'].append("Ajouter de la ponctuation à la description")
    
    return validation