import re
import logging
from typing import Optional
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup

from app.models.schemas import DetectionMode, DetectionResponse
from app.services.language_detector import LanguageDetector
from app.services.redirect_tracker import RedirectTracker, fetch_html
from app.core.config import settings

logger = logging.getLogger(__name__)


class DomainFR:
    """
    Classe principale de détection de sites francophones.
    
    Port de la classe PHP DomaineFr.php avec améliorations :
    - Architecture async
    - Détection NLP
    - Mode paramétrable (simple/complete)
    """
    
    def __init__(
        self,
        homepage: str,
        forced_method: Optional[str] = None,
        use_nlp_detection: bool = True
    ):
        self.homepage = homepage
        self.forced_method = forced_method
        self.use_nlp_detection = use_nlp_detection
        self.tracker = RedirectTracker()
        self.language_detector = LanguageDetector()
    
    @staticmethod
    def get_domain_from_url(url: str) -> str:
        """Extrait le nom de domaine principal d'une URL."""
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname or ''
            parts = hostname.split('.')
            if len(parts) >= 3:
                return parts[-2]
            return parts[0] if parts else url
        except Exception:
            return url
    
    @staticmethod
    def resolve_url(base_url: str, url: str) -> Optional[str]:
        """Résout une URL relative en URL absolue."""
        if not url:
            return None
        
        # URL déjà absolue
        if re.match(r'^https?://', url, re.IGNORECASE):
            return url
        
        try:
            return urljoin(base_url, url)
        except Exception:
            return None
    
    @staticmethod
    def _is_strong_french_url(url: str) -> bool:
        """
        Détermine si l'URL a un signal très fort de site français.
        
        Le TLD .fr est un signal extrêmement fiable : seules les entités
        ayant un lien avec la France peuvent enregistrer un .fr (AFNIC).
        """
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname or ''
            return hostname.endswith('.fr')
        except Exception:
            return False
    
    @staticmethod
    async def check_url(url: str, track_redirect: bool = True, proxy: Optional[str] = None) -> dict:
        """
        Vérifie si une URL indique explicitement une version française.
        
        Vérifie :
        - TLD .fr
        - Sous-domaine fr.
        - Segment /fr/ dans le path
        - Paramètre lang=fr dans la query string
        """
        try:
            parsed = urlparse(url)
            
            if not parsed.hostname:
                return {'ok': False, 'method': 'invalid_host'}
            
            hostname = parsed.hostname
            path = parsed.path or ''
            query = parsed.query or ''
            
            # Vérifier le TLD .fr et les sous-domaines FR
            if hostname.endswith('.fr') or re.match(r'^(fr|france|french|francais|français)\.', hostname, re.IGNORECASE):
                if not track_redirect:
                    return {'ok': True, 'method': 'direct_match'}
                
                # Vérifier avec redirections
                instance = DomainFR(url)
                new_url = f"{parsed.scheme}://{hostname}"
                redirections = await instance._handle_redirections(new_url, url, proxy=proxy)
                
                if redirections.get('ok'):
                    return await instance._recheck_url(url, redirections['url'])
                
                return redirections
            
            # Vérifier les segments de chemin
            if re.search(r'/(fr|france|french|francais|français|fr-fr|fr_fr)(/|$)', path, re.IGNORECASE):
                if not track_redirect:
                    return {'ok': True, 'method': 'pattern_match_path'}
                
                instance = DomainFR(url)
                redirections = await instance._handle_redirections(url, proxy=proxy)
                
                if redirections.get('ok'):
                    return await instance._recheck_url(url, redirections['url'])
                
                return redirections
            
            # Vérifier les paramètres de query
            if query:
                lang_params = ['lang', 'locale', 'language']
                for param in lang_params:
                    pattern = rf'(?:^|&){param}=(fr|france|french|francais|français)(?:&|$|-[A-Z]{{2}})'
                    if re.search(pattern, query, re.IGNORECASE):
                        return {'ok': True, 'method': 'pattern_match_query'}
            
            return {'ok': False, 'method': 'no_match'}
            
        except Exception as e:
            return {'ok': False, 'method': 'invalid_url', 'error': str(e)}
    
    async def _handle_redirections(
        self,
        url_to_track: str,
        url: Optional[str] = None,
        target_content_type: str = '',
        proxy: Optional[str] = None
    ) -> dict:
        """Gère les redirections HTTP."""
        if not url:
            url = url_to_track
        
        try:
            response = await self.tracker.get_url_redirection(url_to_track, proxy)
            
            if response.get('success') and response.get('status_code') == 200:
                result = {
                    'ok': True,
                    'url': response['final_url']
                }
                
                if target_content_type:
                    content_type = response.get('content_type', '')
                    if target_content_type in content_type:
                        return result
                    else:
                        return {'ok': False, 'url': url, 'method': 'wrong_content_type'}
                
                return result
            
            return {
                'ok': False,
                'method': 'redirect_failed',
                'url': url,
                'error': response.get('error')
            }
            
        except Exception as e:
            return {
                'ok': False,
                'method': 'all_redirections_failed',
                'url': url,
                'error': str(e)
            }
    
    async def _recheck_url(self, original_url: str, new_url: str) -> dict:
        """Revalide une URL après redirection."""
        if original_url == new_url:
            return {
                'ok': True,
                'method': 'no_redirect',
                'url': original_url
            }
        
        recheck = await self.check_url(new_url, track_redirect=False)
        recheck['original_url'] = original_url
        recheck['url'] = new_url
        return recheck
    
    def _check_base_domain(self, base_domain: str, actual_domain: str) -> bool:
        """Vérifie que deux domaines sont liés."""
        if not base_domain or not actual_domain:
            return False
        
        base_lower = base_domain.lower()
        actual_lower = actual_domain.lower()
        
        return base_lower in actual_lower or actual_lower in base_lower
    
    def detect_alternative_languages(self, content: str) -> list[str]:
        """
        Recherche des liens vers une version française.
        
        Détecte :
        - <link hreflang="fr">
        - <a href="...fr...">
        - <option value="fr">
        - Éléments avec data-lang="fr"
        """
        if not content:
            return []
        
        alternatives = []
        base_domain = self.get_domain_from_url(self.homepage)
        
        try:
            soup = BeautifulSoup(content, 'lxml')
            
            # 1. Recherche hreflang
            hreflang_links = soup.find_all(attrs={'hreflang': re.compile(r'^fr', re.IGNORECASE)})
            for link in hreflang_links:
                href = link.get('href')
                if href and href != '#':
                    resolved = self.resolve_url(self.homepage, href)
                    if resolved:
                        link_domain = self.get_domain_from_url(resolved)
                        if self._check_base_domain(base_domain, link_domain):
                            alternatives.append(resolved)
            
            # 2. Recherche data-lang="fr"
            data_lang_elements = soup.find_all(attrs={'data-lang': re.compile(r'^fr', re.IGNORECASE)})
            for elem in data_lang_elements:
                href = elem.get('href')
                if href and href != '#':
                    resolved = self.resolve_url(self.homepage, href)
                    if resolved:
                        link_domain = self.get_domain_from_url(resolved)
                        if self._check_base_domain(base_domain, link_domain):
                            alternatives.append(resolved)
            
            # 3. Recherche liens avec /fr/ ou lang=fr
            fr_pattern = re.compile(r'/(fr|fr-fr|fr_fr)(/|$)|lang=fr', re.IGNORECASE)
            for link in soup.find_all('a', href=True):
                href = link['href']
                if fr_pattern.search(href) and 'mailto:' not in href:
                    resolved = self.resolve_url(self.homepage, href)
                    if resolved:
                        link_domain = self.get_domain_from_url(resolved)
                        if self._check_base_domain(base_domain, link_domain):
                            if resolved not in alternatives:
                                alternatives.append(resolved)
            
            # 4. Recherche options avec value fr
            for option in soup.find_all('option'):
                value = option.get('value', '')
                if re.search(r'(^|/)fr(/|$)|lang=fr', value, re.IGNORECASE):
                    resolved = self.resolve_url(self.homepage, value)
                    if resolved and resolved not in alternatives:
                        alternatives.append(resolved)
            
        except Exception:
            pass
        
        return alternatives[:5]  # Limiter à 5 alternatives
    
    async def check_page_if_french(
        self,
        content: str,
        mode: DetectionMode = DetectionMode.COMPLETE
    ) -> DetectionResponse:
        """
        Vérifie si une page est en français ou dispose d'une version française.
        
        Logique de décision avec niveaux de signal URL :
        
        Signal FORT (TLD .fr) :
          → Accepté comme français sauf si NLP détecte ACTIVEMENT une autre langue
            avec haute confiance (>0.9)
        
        Signal MODÉRÉ (path /fr/, lang=fr, sous-domaine fr.) :
          → Nécessite que NLP confirme ou au minimum ne contredise pas
        
        Signal ABSENT :
          → NLP obligatoire pour confirmer
        
        Args:
            content: Contenu HTML de la page
            mode: Mode de détection (simple ou complete)
        
        Returns:
            DetectionResponse avec le résultat
        """
        url = self.homepage
        
        if not url or not content:
            return DetectionResponse(
                ok=False,
                url=url or '',
                method='info_vide'
            )
        
        # Étape 1 : Vérification URL (TLD .fr, /fr/, lang=fr)
        url_check = await self.check_url(url, track_redirect=False)
        url_indicates_french = url_check.get('ok', False)
        url_method = url_check.get('method', '')
        is_strong_url = self._is_strong_french_url(url)
        
        # Étape 2 : Méthode forcée (si définie)
        if self.forced_method:
            lang_check = self.language_detector.detect_from_html_tags(content)
            if lang_check and lang_check.get('method') == self.forced_method and lang_check.get('value') == 'fr':
                # Confirmation NLP obligatoire même avec méthode forcée
                nlp_result = self.language_detector.detect_from_text_content_fasttext(content)
                if nlp_result is None:
                    nlp_result = self.language_detector.detect_from_text_content(content)

                if nlp_result and nlp_result.get('lang') == 'fr':
                    return DetectionResponse(
                        ok=True,
                        url=url,
                        method=f"{self.forced_method}+nlp_confirmed",
                        confidence=nlp_result.get('confidence')
                    )
            return DetectionResponse(
                ok=False,
                url=url,
                method='Check_nok_forced'
            )
        
        # Étape 3 : Détection langue HTML (balises <html lang>, meta, etc.)
        lang_result = self.language_detector.detect_combined(content, use_nlp=False)
        html_indicates_french = lang_result.get('detected') and lang_result.get('is_french')
        html_method = lang_result.get('method', '')
        
        # Étape 4 : Vérification NLP (fastText prioritaire)
        # Si fastText échoue (modèle absent), fallback langdetect+langid.
        # Si fastText détecte non-FR avec faible confiance, cross-check avec langdetect+langid.
        nlp_result = self.language_detector.detect_from_text_content_fasttext(content)

        if nlp_result is None:
            # Fallback : fastText indisponible (modèle absent ou texte trop court)
            logger.info("fastText indisponible, fallback vers langdetect+langid")
            nlp_result = self.language_detector.detect_from_text_content(content)
        elif nlp_result.get('lang') != 'fr' and nlp_result.get('confidence', 0) < 0.75:
            # fastText détecte non-FR avec faible confiance → cross-check obligatoire
            # Cas typique : sites e-commerce FR avec noms de produits, termes techniques anglais
            logger.info(
                f"fastText peu confiant ({nlp_result.get('lang')}={nlp_result.get('confidence', 0):.3f}), "
                "cross-check avec langdetect+langid"
            )
            secondary_result = self.language_detector.detect_from_text_content(content)
            if secondary_result and secondary_result.get('lang') == 'fr':
                # langdetect+langid détecte FR → on fait confiance au cross-check
                logger.info(
                    f"Cross-check langdetect+langid confirme FR "
                    f"(confiance={secondary_result.get('confidence', 0):.3f}) — "
                    f"fastText avait détecté {nlp_result.get('lang')}"
                )
                nlp_result = secondary_result

        logger.debug(f"NLP RESULT: {nlp_result}")

        nlp_lang = nlp_result.get('lang') if nlp_result else None
        nlp_confidence = nlp_result.get('confidence', 0) if nlp_result else 0.0
        nlp_available = nlp_result is not None
        
        # Catégorisation fine du résultat NLP
        nlp_confirms_french = nlp_available and nlp_lang == 'fr' and nlp_confidence >= settings.NLP_MIN_CONFIDENCE
        nlp_soft_french = nlp_available and nlp_lang == 'fr' and nlp_confidence < settings.NLP_MIN_CONFIDENCE
        nlp_contradicts_french = nlp_available and nlp_lang is not None and nlp_lang != 'fr'
        nlp_strongly_contradicts = nlp_contradicts_french and nlp_confidence > 0.9
        
        # Étape 5 : Recherche liens alternatifs (mode COMPLETE uniquement)
        alternatives = []
        if mode == DetectionMode.COMPLETE:
            alternatives = self.detect_alternative_languages(content)
        
        # ====================================================================
        # LOGIQUE DE DÉCISION FINALE
        # ====================================================================
        
        # Cas 1 : NLP confirme pleinement le français
        if nlp_confirms_french:
            methods = []
            if url_indicates_french:
                methods.append(url_method)
            if html_indicates_french:
                methods.append(html_method)
            methods.append('nlp_confirmed')
            
            return DetectionResponse(
                ok=True,
                url=url,
                method='+'.join(methods),
                confidence=nlp_confidence,
                alternative_urls=alternatives
            )
        
        # Cas 2 : TLD .fr (signal FORT) — accepté sauf contradiction NLP forte
        if is_strong_url:
            # Sous-cas 2a : NLP contredit fortement (>0.9 confiance dans une autre langue)
            # → Rare mais possible (ex: site .fr en anglais)
            if nlp_strongly_contradicts:
                logger.info(
                    f"TLD .fr mais NLP détecte {nlp_lang} avec confiance {nlp_confidence:.3f} — rejet"
                )
                return DetectionResponse(
                    ok=False,
                    url=url,
                    method='nlp_override_tld_fr',
                    confidence=nlp_confidence,
                    alternative_urls=alternatives,
                    error=f"TLD .fr mais contenu détecté comme {nlp_lang} ({nlp_confidence:.0%})"
                )
            
            # Sous-cas 2b : NLP soft-confirme, ou NLP indisponible, ou NLP faiblement contredit
            # → Le TLD .fr est un signal suffisamment fort pour valider
            methods = [url_method]
            if html_indicates_french:
                methods.append(html_method)
            
            if nlp_soft_french:
                methods.append('nlp_soft_confirmed')
                confidence = nlp_confidence
            elif not nlp_available:
                methods.append('nlp_skipped')
                confidence = 0.7
            elif nlp_contradicts_french:
                methods.append(f'nlp_weak_disagree_{nlp_lang}')
                confidence = 0.6
            else:
                methods.append('tld_trusted')
                confidence = 0.8
            
            return DetectionResponse(
                ok=True,
                url=url,
                method='+'.join(methods),
                confidence=confidence,
                alternative_urls=alternatives
            )
        
        # Cas 3 : Signal URL modéré (/fr/, lang=fr, sous-domaine) + NLP soft FR
        if url_indicates_french and nlp_soft_french:
            methods = [url_method, 'nlp_soft_confirmed']
            if html_indicates_french:
                methods.insert(1, html_method)
            
            return DetectionResponse(
                ok=True,
                url=url,
                method='+'.join(methods),
                confidence=nlp_confidence,
                alternative_urls=alternatives
            )
        
        # Cas 4 : HTML indique FR + NLP soft FR (mais URL neutre)
        if html_indicates_french and nlp_soft_french:
            return DetectionResponse(
                ok=True,
                url=url,
                method=f"{html_method}+nlp_soft_confirmed",
                confidence=nlp_confidence,
                alternative_urls=alternatives
            )
        
        # Cas 5 : NLP indisponible + HTML ou URL modéré indique FR
        if not nlp_available and (html_indicates_french or url_indicates_french):
            methods = []
            if url_indicates_french:
                methods.append(url_method)
            if html_indicates_french:
                methods.append(html_method)
            methods.append('nlp_skipped')
            
            return DetectionResponse(
                ok=True,
                url=url,
                method='+'.join(methods),
                confidence=0.6,
                alternative_urls=alternatives
            )
        
        # Cas 6 : Liens alternatifs trouvés mais page actuelle pas confirmée FR
        if alternatives:
            return DetectionResponse(
                ok=False,
                url=url,
                method='alternative_link_needs_verification',
                alternative_urls=alternatives,
                confidence=nlp_confidence if nlp_result else None,
                error="Page actuelle non française, mais des liens alternatifs FR existent"
            )
        
        # Cas 7 : NLP disponible mais ne confirme pas, malgré indicateurs HTML/URL
        if nlp_available and (html_indicates_french or url_indicates_french):
            return DetectionResponse(
                ok=False,
                url=url,
                method='nlp_not_confirmed',
                confidence=nlp_confidence if nlp_result else None,
                error=f"Indicateurs trouvés ({html_method or url_method}) mais NLP détecte: {nlp_lang or 'N/A'}"
            )
        
        # Cas 8 : Dernier recours — signal lexical français
        # Si les moteurs NLP échouent (contenu mixte, noms de produits, etc.)
        # mais que le texte contient clairement des mots français exclusifs,
        # on accepte avec une confiance réduite.
        try:
            soup_check = BeautifulSoup(content, 'lxml')
            for el in soup_check(['script', 'style', 'meta', 'link', 'noscript']):
                el.decompose()
            visible_text = soup_check.get_text(separator=' ', strip=True)
            
            if len(visible_text) >= 50:
                french_signal = self.language_detector._compute_french_signal(visible_text)
                logger.debug(f"Lexical French signal (last resort): {french_signal:.3f}")
                
                if french_signal > 0.3:
                    return DetectionResponse(
                        ok=True,
                        url=url,
                        method='french_lexical_signal',
                        confidence=round(min(0.7, french_signal), 3),
                        alternative_urls=alternatives
                    )
        except Exception as e:
            logger.warning(f"Erreur signal lexical: {e}")
        
        # Cas 9 : Aucun indicateur français trouvé
        return DetectionResponse(
            ok=False,
            url=url,
            method='Check_nok_v2'
        )
