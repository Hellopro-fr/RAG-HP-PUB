import re
from typing import Optional
from bs4 import BeautifulSoup
from langdetect import detect, detect_langs, LangDetectException
import langid
from app.core.config import settings


class LanguageDetector:
    """
    Détecteur de langue combinant plusieurs méthodes :
    - Analyse des balises HTML (lang, meta)
    - Détection NLP par contenu textuel (langdetect + langid)
    """
    
    def __init__(self):
        # Configuration langid pour optimiser la détection français
        langid.set_languages(['fr', 'en', 'de', 'es', 'it', 'pt', 'nl'])
    
    def detect_from_html_tags(self, html: str) -> Optional[dict]:
        """
        Détecte la langue via les balises HTML.
        
        Priorité :
        1. <html lang="...">
        2. <meta property="og:locale">
        3. <meta name="LANGUAGE">
        4. <meta http-equiv="content-language">
        """
        if not html:
            return None
        
        # Nettoyer les commentaires conditionnels IE
        ie_comment_pattern = r'<!--\[if[^>]*>.*?<!\[endif\]-->'
        cleaned_html = re.sub(ie_comment_pattern, '', html, flags=re.DOTALL | re.IGNORECASE)
        
        # Priority 1: Check <html lang="..."> or <html xml:lang="...">
        html_lang_pattern = r'<html[^>]*\s(?:xml:)?lang=["\']?([a-zA-Z-]+)["\']?'
        match = re.search(html_lang_pattern, cleaned_html, re.IGNORECASE)
        if match:
            lang_value = match.group(1).split('-')[0].lower()
            return {
                'method': 'langHtml',
                'value': lang_value
            }
        
        # Priority 2: Check <meta property="og:locale">
        meta_locale_pattern = r'<meta[^>]*property=["\']og:locale["\'][^>]*content=["\']([a-zA-Z_-]+)["\']'
        match = re.search(meta_locale_pattern, cleaned_html, re.IGNORECASE)
        if match:
            lang_value = match.group(1).split('_')[0].split('-')[0].lower()
            return {
                'method': 'matchMeta',
                'value': lang_value
            }
        
        # Priority 2.1: Check reverse order <meta content="..." property="og:locale">
        meta_locale_pattern_rev = r'<meta[^>]*content=["\']([a-zA-Z_-]+)["\'][^>]*property=["\']og:locale["\']'
        match = re.search(meta_locale_pattern_rev, cleaned_html, re.IGNORECASE)
        if match:
            lang_value = match.group(1).split('_')[0].split('-')[0].lower()
            return {
                'method': 'matchMeta',
                'value': lang_value
            }
        
        # Priority 3: Check <meta name="LANGUAGE">
        meta_language_pattern = r'<meta[^>]*name=["\']LANGUAGE["\'][^>]*content=["\']([a-zA-Z-]+)["\']'
        match = re.search(meta_language_pattern, cleaned_html, re.IGNORECASE)
        if match:
            lang_value = match.group(1).split('-')[0].lower()
            return {
                'method': 'matchMeta',
                'value': lang_value
            }
        
        # Priority 4: Check <meta http-equiv="content-language">
        http_equiv_pattern = r'<meta[^>]*http-equiv=["\']content-language["\'][^>]*content=["\']([a-zA-Z-]+)["\']'
        match = re.search(http_equiv_pattern, cleaned_html, re.IGNORECASE)
        if match:
            lang_value = match.group(1).split('-')[0].lower()
            return {
                'method': 'matchHttpEquiv',
                'value': lang_value
            }
        
        return None
    
    def detect_from_text_content(self, html: str) -> Optional[dict]:
        """
        Détecte la langue par analyse NLP du contenu textuel visible.
        
        Utilise langdetect (Google) et langid (ML) avec vote majoritaire.
        """
        if not html:
            return None
        
        try:
            # Extraire le texte visible avec BeautifulSoup
            soup = BeautifulSoup(html, 'lxml')
            
            # Supprimer scripts, styles et autres éléments non visibles
            for element in soup(['script', 'style', 'meta', 'link', 'noscript', 'header', 'footer', 'nav']):
                element.decompose()
            
            text = soup.get_text(separator=' ', strip=True)
            
            # Vérifier longueur minimale
            if len(text) < settings.NLP_MIN_TEXT_LENGTH:
                return None
            
            # Limiter le texte analysé (performance)
            text = text[:5000]

            print("============== TEXT ============== \n")
            print(text)
            
            # Détection avec langdetect
            langdetect_result = None
            langdetect_confidence = 0.0
            try:
                langs = detect_langs(text)
                if langs:
                    langdetect_result = langs[0].lang
                    langdetect_confidence = langs[0].prob
            except LangDetectException:
                pass
            
            # Détection avec langid
            langid_result, langid_confidence = langid.classify(text)
            # Normaliser le score langid (il retourne un score négatif)
            langid_confidence = 1 / (1 + abs(langid_confidence))
            
            # Vote majoritaire avec pondération
            results = {}
            if langdetect_result:
                results[langdetect_result] = results.get(langdetect_result, 0) + langdetect_confidence
            if langid_result:
                results[langid_result] = results.get(langid_result, 0) + langid_confidence
            
            if not results:
                return None
            
            # Trouver la langue dominante
            best_lang = max(results, key=results.get)
            avg_confidence = results[best_lang] / (2 if langdetect_result and langid_result else 1)
            
            return {
                'method': 'nlp_detection',
                'lang': best_lang,
                'confidence': round(avg_confidence, 3),
                'details': {
                    'langdetect': {'lang': langdetect_result, 'confidence': round(langdetect_confidence, 3)} if langdetect_result else None,
                    'langid': {'lang': langid_result, 'confidence': round(langid_confidence, 3)} if langid_result else None
                }
            }
            
        except Exception as e:
            return None
    
    def detect_combined(self, html: str, use_nlp: bool = True) -> dict:
        """
        Combine toutes les méthodes de détection avec priorisation.
        
        Priorité :
        1. Balises HTML (plus fiable car déclaratif)
        2. Détection NLP (si activée)
        """
        # D'abord les balises HTML
        html_result = self.detect_from_html_tags(html)
        if html_result:
            return {
                'detected': True,
                'is_french': html_result['value'] == 'fr',
                'method': html_result['method'],
                'value': html_result['value'],
                'confidence': 1.0  # Confiance maximale pour les balises
            }
        
        # Ensuite NLP si activé
        if use_nlp:
            nlp_result = self.detect_from_text_content(html)
            if nlp_result and nlp_result['confidence'] >= settings.NLP_MIN_CONFIDENCE:
                return {
                    'detected': True,
                    'is_french': nlp_result['lang'] == 'fr',
                    'method': nlp_result['method'],
                    'value': nlp_result['lang'],
                    'confidence': nlp_result['confidence']
                }
        
        return {
            'detected': False,
            'is_french': False,
            'method': 'none',
            'value': None,
            'confidence': 0.0
        }
