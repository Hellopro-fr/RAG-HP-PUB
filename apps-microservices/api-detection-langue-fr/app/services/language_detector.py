import re
import logging
from typing import Optional
from bs4 import BeautifulSoup
from langdetect import detect, detect_langs, LangDetectException
import langid
from app.core.config import settings

logger = logging.getLogger(__name__)


class LanguageDetector:
    """
    Détecteur de langue combinant plusieurs méthodes :
    - Analyse des balises HTML (lang, meta)
    - Détection NLP par contenu textuel (langdetect + langid)
    """
    # Mots fonctionnels exclusivement français (à fort poids discriminant)
    # Ces mots n'existent PAS en espagnol, portugais, italien ou anglais
    FRENCH_EXCLUSIVE_STOPWORDS = {
        'nous', 'vous', 'sont', 'avec', 'dans', 'pour', 'mais', 'comme',
        'entre', 'aussi', 'très', 'cette', 'leurs', 'dont', 'depuis',
        'encore', 'après', 'sous', 'chez', 'jusqu', 'toujours', 'peut',
        'même', 'être', 'fait', 'tout', 'tous', 'plus', 'avoir',
        'notre', 'votre', 'leurs', 'quelques', 'chaque', 'plusieurs'
    }
    
    # Mots partagés avec d'autres langues romanes (à faible poids)
    FRENCH_SHARED_STOPWORDS = {
        'le', 'la', 'les', 'de', 'des', 'un', 'une', 'du',
        'sur', 'par', 'sans', 'est', 'et', 'ou', 'si', 'ce',
        'ces', 'au', 'aux', 'qui', 'que', 'où'
    }
    

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
    
    
    def _compute_french_signal(self, text: str) -> float:
        """
        Calcule un score basé sur la présence de mots fonctionnels français.
        Retourne un score entre 0 et 1.
        
        Utilise deux niveaux de poids :
        - Mots exclusivement français (poids fort)
        - Mots partagés avec autres langues romanes (poids faible)
        """
        text_lower = text.lower()
        words = re.findall(r'\b\w+\b', text_lower)
        
        if len(words) < 10:
            return 0.0
        
        # Compter les mots exclusivement français (poids fort)
        exclusive_count = sum(1 for word in words if word in self.FRENCH_EXCLUSIVE_STOPWORDS)
        
        # Compter les mots partagés (poids faible)
        shared_count = sum(1 for word in words if word in self.FRENCH_SHARED_STOPWORDS)
        
        # Score pondéré : exclusifs comptent double
        weighted_count = (exclusive_count * 2.0) + (shared_count * 0.5)
        
        # Ratio pondéré
        french_ratio = weighted_count / len(words)
        
        # Normaliser avec un multiplicateur réduit (×10 au lieu de ×20)
        # Si >10% de mots français pondérés → signal fort
        return min(1.0, french_ratio * 10)
    
    def detect_from_text_content(self, html: str) -> Optional[dict]:
        """
        Détecte la langue par analyse NLP du contenu textuel visible.
        
        Utilise langdetect (Google) et langid (ML) avec vote majoritaire amélioré.
        """
        if not html:
            return None
        
        try:
            # Extraire le texte visible avec BeautifulSoup
            soup = BeautifulSoup(html, 'lxml')
            
            # Supprimer scripts, styles et autres éléments non visibles
            # Note: on garde header, footer, nav car ils peuvent contenir du contenu pertinent
            for element in soup(['script', 'style', 'meta', 'link', 'noscript']):
                element.decompose()
            
            text = soup.get_text(separator=' ', strip=True)
            
            # Vérifier longueur minimale
            if len(text) < settings.NLP_MIN_TEXT_LENGTH:
                return None
            
            # Limiter le texte analysé (performance)
            text = text[:5000]
            
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
            langid_result, langid_score = langid.classify(text)
            # Normaliser le score langid avec sigmoid
            # langid retourne des log-probabilités normalisées entre -inf et 0
            # On utilise un sigmoid pour une normalisation plus réaliste
            import math
            langid_confidence = 1.0 / (1.0 + math.exp(-langid_score - 10))
            langid_confidence = max(0.0, min(1.0, langid_confidence))
            
            # Signal français par analyse lexicale
            french_signal = self._compute_french_signal(text)
            
            logger.debug(f"French signal: {french_signal:.3f}")
            logger.debug(f"Langdetect: {langdetect_result} ({langdetect_confidence:.3f})")
            logger.debug(f"Langid: {langid_result} ({langid_confidence:.3f})")
            
            # Vote pondéré amélioré
            results = {}
            
            # Langdetect avec poids modéré (peut être trompé par mots techniques)
            if langdetect_result:
                results[langdetect_result] = results.get(langdetect_result, 0) + (langdetect_confidence * 0.4)
            
            # Langid avec poids renforcé (meilleur sur textes techniques)
            if langid_result:
                results[langid_result] = results.get(langid_result, 0) + (langid_confidence * 0.6)
            
            # Bonus français UNIQUEMENT si signal lexical très fort (seuil relevé à 0.5)
            # et avec un poids réduit (0.3 au lieu de 0.5)
            if french_signal > 0.5:
                results['fr'] = results.get('fr', 0) + (french_signal * 0.3)
            
            if not results:
                return None
            
            # Trouver la langue dominante
            best_lang = max(results, key=results.get)
            
            # Calculer la confiance finale
            total_weight = sum(results.values())
            confidence = results[best_lang] / total_weight if total_weight > 0 else 0
            
            # Détails pour debugging
            details = {
                'langdetect': {'lang': langdetect_result, 'confidence': round(langdetect_confidence, 3)} if langdetect_result else None,
                'langid': {'lang': langid_result, 'confidence': round(langid_confidence, 3)} if langid_result else None,
                'french_signal': round(french_signal, 3),
                'weighted_scores': {k: round(v, 3) for k, v in results.items()}
            }
            
            return {
                'method': 'nlp_detection',
                'lang': best_lang,
                'confidence': round(confidence, 3),
                'details': details
            }
            
        except Exception as e:
            logger.error(f"Erreur détection langue: {e}")
            return None
    
    def detect_from_text_content_fasttext(self, html: str) -> Optional[dict]:
        """
        Détecte la langue par analyse NLP du contenu textuel visible.
        
        Utilise fastText (modèle lid.176.bin de Facebook) pour la détection.
        Retourne le même format que detect_from_text_content pour compatibilité.
        """
        if not html:
            return None
        
        try:
            import fasttext
            import os
            
            # Chemin vers le modèle fastText (à configurer via settings si besoin)
            model_path = getattr(settings, 'FASTTEXT_MODEL_PATH', None) or os.path.join(
                os.path.dirname(__file__), '..', '..', 'models', 'lid.176.bin'
            )
            
            # Charger le modèle (lazy loading)
            if not hasattr(self, '_fasttext_model'):
                if not os.path.exists(model_path):
                    logger.warning(f"Modèle fastText non trouvé: {model_path}")
                    return None
                self._fasttext_model = fasttext.load_model(model_path)
            
            # Extraire le texte visible avec BeautifulSoup
            soup = BeautifulSoup(html, 'lxml')
            
            # Supprimer scripts, styles et autres éléments non visibles
            # Harmonisé avec detect_from_text_content (même liste d'éléments)
            for element in soup(['script', 'style', 'meta', 'link', 'noscript']):
                element.decompose()
            
            text = soup.get_text(separator=' ', strip=True)
            
            # Vérifier longueur minimale
            if len(text) < settings.NLP_MIN_TEXT_LENGTH:
                return None
            
            # Limiter le texte analysé (performance)
            text = text[:5000]
            
            # Nettoyer le texte (fastText n'aime pas les sauts de ligne)
            text_clean = ' '.join(text.split())
            
            # Prédiction fastText
            predictions = self._fasttext_model.predict(text_clean, k=3)
            labels, scores = predictions
            
            # Extraire la langue principale (format: __label__fr)
            main_lang = labels[0].replace('__label__', '')
            main_confidence = float(scores[0])
            
            # Signal français par analyse lexicale
            french_signal = self._compute_french_signal(text)
            
            logger.debug(f"[FastText] Main lang: {main_lang} ({main_confidence:.3f})")
            logger.debug(f"[FastText] French signal: {french_signal:.3f}")
            
            # Détails pour debugging
            details = {
                'fasttext': {
                    'predictions': [
                        {'lang': l.replace('__label__', ''), 'confidence': round(float(s), 3)}
                        for l, s in zip(labels, scores)
                    ]
                },
                'french_signal': round(french_signal, 3)
            }
            
            # Confiance finale basée sur fastText uniquement
            # Le signal lexical sert UNIQUEMENT à renforcer un résultat français déjà détecté
            # Il ne doit JAMAIS forcer un changement de langue détectée
            final_confidence = main_confidence
            final_lang = main_lang
            
            if main_lang == 'fr' and french_signal > 0.3:
                # Bonus de confiance modéré si signal lexical confirme le français
                final_confidence = min(1.0, main_confidence + french_signal * 0.1)
            
            return {
                'method': 'nlp_detection_fasttext',
                'lang': final_lang,
                'confidence': round(final_confidence, 3),
                'details': details
            }
            
        except ImportError:
            logger.error("fastText non installé. Installez-le avec: pip install fasttext")
            return None
        except Exception as e:
            logger.error(f"Erreur détection fastText: {e}")
            return None
    
    def detect_combined(self, html: str, use_nlp: bool = True) -> dict:
        """
        Combine toutes les méthodes de détection avec priorisation.
        
        Logique :
        1. Détecte via balises HTML
        2. Détecte via NLP (si activé)
        3. Croisement des résultats :
           - Si HTML et NLP sont d'accord → résultat avec confiance haute
           - Si HTML dit FR mais NLP dit non → NLP prime (contenu réel)
           - Si NLP seul → résultat avec confiance NLP
           - Si HTML seul (NLP indisponible) → résultat avec confiance réduite
        """
        # Étape 1 : Analyse des balises HTML
        html_result = self.detect_from_html_tags(html)
        html_lang = html_result['value'] if html_result else None
        html_method = html_result['method'] if html_result else None
        
        # Étape 2 : Analyse NLP (si activée)
        nlp_result = None
        if use_nlp:
            nlp_result = self.detect_from_text_content_fasttext(html)
        
        nlp_lang = nlp_result['lang'] if nlp_result else None
        nlp_confidence = nlp_result['confidence'] if nlp_result else 0.0
        
        # Étape 3 : Croisement des résultats
        
        # Cas A : HTML et NLP disponibles
        if html_lang and nlp_result:
            if html_lang == nlp_lang:
                # Accord total → confiance maximale
                return {
                    'detected': True,
                    'is_french': html_lang == 'fr',
                    'method': f"{html_method}+nlp_confirmed",
                    'value': html_lang,
                    'confidence': max(nlp_confidence, 0.9)
                }
            else:
                # Désaccord → NLP prime car c'est le contenu réel
                logger.info(
                    f"Désaccord HTML ({html_lang}) vs NLP ({nlp_lang}). "
                    f"NLP prime avec confiance {nlp_confidence:.3f}"
                )
                return {
                    'detected': True,
                    'is_french': nlp_lang == 'fr',
                    'method': f"nlp_override_{html_method}",
                    'value': nlp_lang,
                    'confidence': nlp_confidence
                }
        
        # Cas B : NLP seul (pas de balise HTML)
        if nlp_result and nlp_confidence >= settings.NLP_MIN_CONFIDENCE:
            return {
                'detected': True,
                'is_french': nlp_lang == 'fr',
                'method': 'nlp_only',
                'value': nlp_lang,
                'confidence': nlp_confidence
            }
        
        # Cas C : HTML seul (NLP indisponible — texte trop court ou erreur)
        if html_lang and not nlp_result:
            return {
                'detected': True,
                'is_french': html_lang == 'fr',
                'method': f"{html_method}+nlp_skipped",
                'value': html_lang,
                'confidence': 0.6  # Confiance réduite car non confirmé par NLP
            }
        
        # Cas D : Rien détecté
        return {
            'detected': False,
            'is_french': False,
            'method': 'none',
            'value': None,
            'confidence': 0.0
        }
