import re
from typing import Optional
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup

from app.models.schemas import DetectionMode, DetectionResponse
from app.services.language_detector import LanguageDetector
from app.services.redirect_tracker import RedirectTracker, fetch_html
from app.core.config import settings


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
        
        # Étape 1 : Vérification URL
        url_check = await self.check_url(url, track_redirect=False)
        if url_check.get('ok'):
            return DetectionResponse(
                ok=True,
                url=url,
                method='checkUrl'
            )
        
        # Étape 2 : Méthode forcée (si définie)
        if self.forced_method:
            lang_check = self.language_detector.detect_from_html_tags(content)
            if lang_check and lang_check.get('method') == self.forced_method and lang_check.get('value') == 'fr':
                return DetectionResponse(
                    ok=True,
                    url=url,
                    method=self.forced_method
                )
            return DetectionResponse(
                ok=False,
                url=url,
                method='Check_nok_forced'
            )
        
        # Étape 3 : Détection langue HTML
        lang_result = self.language_detector.detect_combined(content, use_nlp=False)
        if lang_result.get('detected') and lang_result.get('is_french'):
            # En mode COMPLETE, vérifier s'il existe des alternatives
            if mode == DetectionMode.COMPLETE:
                alternatives = self.detect_alternative_languages(content)
                if alternatives:
                    # Vérifier si l'alternative est différente de l'URL actuelle
                    parsed_current = urlparse(url)
                    for alt in alternatives:
                        parsed_alt = urlparse(alt)
                        if parsed_current.path != parsed_alt.path or parsed_current.query != parsed_alt.query:
                            return DetectionResponse(
                                ok=True,
                                url=alt,
                                method=lang_result['method'],
                                alternative_urls=alternatives
                            )
            
            return DetectionResponse(
                ok=True,
                url=url,
                method=lang_result['method'],
                confidence=lang_result.get('confidence')
            )
        
        # Étape 4 : Recherche liens alternatifs (mode COMPLETE uniquement)
        if mode == DetectionMode.COMPLETE:
            alternatives = self.detect_alternative_languages(content)
            if alternatives:
                return DetectionResponse(
                    ok=True,
                    url=alternatives[0],
                    method='alternative_link',
                    alternative_urls=alternatives
                )
        
        # Étape 5 : Détection NLP (si activée)
        if self.use_nlp_detection:
            nlp_result = self.language_detector.detect_from_text_content(content)
            if nlp_result and nlp_result.get('lang') == 'fr':
                confidence = nlp_result.get('confidence', 0)
                if confidence >= settings.NLP_MIN_CONFIDENCE:
                    return DetectionResponse(
                        ok=True,
                        url=url,
                        method='nlp_detection',
                        confidence=confidence
                    )
        
        return DetectionResponse(
            ok=False,
            url=url,
            method='Check_nok_v2'
        )
