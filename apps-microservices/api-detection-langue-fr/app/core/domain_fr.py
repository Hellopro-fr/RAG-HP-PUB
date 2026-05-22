import re
import json
import asyncio
import logging
import httpx
from typing import Optional
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup

from common_utils.redis import cache_service

from app.models.schemas import (
    DetectionMode, DetectionResponse, AlternativeUrl,
    DebugDetectionResponse, DebugInfo, DebugFetchInfo, DebugCleaningInfo,
    DebugUrlCheckInfo, DebugHtmlTagsInfo, DebugNlpInfo, DebugAlternativesInfo
)
from app.services.language_detector import LanguageDetector
from app.services.redirect_tracker import RedirectTracker, fetch_html
from app.core.config import settings

logger = logging.getLogger(__name__)


class DomainCache:
    """
    Cache Redis optionnel pour les résultats de détection FR par domaine.

    Règles :
    - Skip si html_content fourni (résultat page-level, pas domain-level)
    - Skip si force_refresh=True (bypass cache en lecture, écrit quand même)
    - Clé : fr_detect:{normalized_domain} (www. supprimé)
    - TTL ok=True → 30 jours, ok=False → 7 jours
    - Échecs transitoires (challenge_page, fetch_empty_content, etc.) → 6 heures
    - Erreurs critiques (fetch_failed, error) → jamais cachées
    - En cas d'indisponibilité Redis, dégrade silencieusement (pas d'exception)
    """

    TTL_OK = 30 * 24 * 3600          # 30 jours — résultats définitifs positifs
    TTL_NOK = 7 * 24 * 3600          # 7 jours — résultats définitifs négatifs
    TTL_TRANSIENT = 6 * 3600          # 6 heures — échecs transitoires (retry automatique)

    # Méthodes qui ne doivent JAMAIS être cachées (erreurs critiques + saturation)
    _NEVER_CACHE_METHODS = frozenset({'error', 'fetch_failed', 'admission_rejected'})

    # Méthodes transitoires : cachées avec TTL court (le site était peut-être temporairement down)
    _TRANSIENT_METHODS = frozenset({
        'challenge_page',               # Cloudflare/WAF — peut se résoudre
        'fetch_empty_content',           # Contenu vide — proxy ou site down
        'all_redirections_failed',       # Redirections échouées
        'info_vide',                     # URL ou contenu absent
    })

    def __init__(self) -> None:
        # _client/_initialized kept as instance attributes for backwards
        # compatibility with existing tests that pre-populate them (see
        # tests/test_domain_cache_ttl.py et al). When unset, _get_client()
        # falls back to the shared cache_service.redis_client.
        self._client = None
        self._initialized = False

    async def _get_client(self):
        """Return the shared async Redis client from common_utils.cache_service.

        Pool cap (REDIS_MAX_CONNECTIONS, default 20), CLIENT SETNAME identity,
        keepalive, and health checks are owned by the shared library. The
        lifespan in main.py calls init_redis_pool() at startup so the client
        is ready by the time the first request lands.

        See docs/superpowers/specs/2026-05-22-redis-common-utils-hardening-design.md
        """
        # Tests inject a mock client directly via cache._client + cache._initialized=True;
        # honor that for backwards compatibility.
        if self._initialized and self._client is not None:
            return self._client
        return cache_service.redis_client

    @staticmethod
    def _normalize_domain(url: str) -> Optional[str]:
        try:
            hostname = (urlparse(url).hostname or '').lower()
            domain = hostname.removeprefix('www.')
            return domain if domain else None
        except Exception:
            return None

    @staticmethod
    def _cache_key(domain: str) -> str:
        return f"fr_detect:{domain}"

    async def get(self, url: str) -> Optional[dict]:
        client = await self._get_client()
        if not client:
            return None
        try:
            domain = self._normalize_domain(url)
            if not domain:
                return None
            data = await client.get(self._cache_key(domain))
            if data:
                return json.loads(data)
        except Exception as e:
            logger.debug(f"Cache get error ({url}): {e}")
        return None

    async def set(
        self,
        input_url: str,
        result_url: str,
        result: dict,
        ttl_override: Optional[int] = None,
    ) -> None:
        """Stocke le résultat pour input_url ET result_url (si redirection).

        ttl_override: bypass the method-based TTL logic when provided. Used by
        the page validator orchestration to set per-verdict TTLs (7d for
        http_error / redirected_to_home, 6h for soft_404).

        The persisted payload always carries `requested_url = input_url`
        so cross-URL cache HITs (different path on the same domain) can
        surface the originating URL via DetectionResponse.analyzed_url.
        """
        client = await self._get_client()
        if not client:
            return
        method = result.get('method', '')
        if method in self._NEVER_CACHE_METHODS:
            return
        try:
            input_domain = self._normalize_domain(input_url)
            if not input_domain:
                return

            # Persist requested_url for cross-URL HIT awareness.
            result["requested_url"] = input_url

            # TTL: override > method-based logic.
            if ttl_override is not None:
                ttl = ttl_override
            elif method in self._TRANSIENT_METHODS or any(
                method.startswith(prefix) for prefix in ('HTTP_',)
            ):
                ttl = self.TTL_TRANSIENT
            elif result.get('ok'):
                ttl = self.TTL_OK
            else:
                ttl = self.TTL_NOK

            data = json.dumps(result)
            await client.setex(self._cache_key(input_domain), ttl, data)
            result_domain = self._normalize_domain(result_url)
            if result_domain and result_domain != input_domain:
                await client.setex(self._cache_key(result_domain), ttl, data)
        except Exception as e:
            logger.debug(f"Cache set error ({input_url}): {e}")


domain_cache = DomainCache()


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
        use_nlp_detection: bool = True,
        original_homepage: Optional[str] = None
    ):
        self.homepage = homepage
        self.original_homepage = original_homepage or homepage
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
        """
        Vérifie que deux domaines sont liés.

        Normalise les séparateurs (hyphens, underscores) avant comparaison
        pour gérer les cas où une entreprise utilise des variantes :
        Ex: stematjansen.com et stemat-jansen.fr → match
        """
        if not base_domain or not actual_domain:
            return False

        # Normalisation : lowercase + suppression hyphens et underscores
        base_norm = base_domain.lower().replace('-', '').replace('_', '')
        actual_norm = actual_domain.lower().replace('-', '').replace('_', '')

        return base_norm in actual_norm or actual_norm in base_norm

    @staticmethod
    def _is_valid_language_alternative(homepage_host: str, candidate_url: str) -> bool:
        """Return True only if candidate_url is plausibly a language variant of homepage.

        Cross-host candidates (different hostname): trusted unconditionally — webmasters
        legitimately declare external alternates via hreflang.

        Same-host candidates: must have a language-shaped first path segment matching
        ^[a-z]{2}([-_][a-z]{2,4})?$ (case-insensitive). Examples accepted:
          /fr, /fr/page, /fr-FR, /fr_FR/page, /en, /en-GB, /de, /de-DE, /pt-BR

        Same-host content paths (/, /nos-realisations, /produits, /a-propos,
        /l-entreprise, etc.) are rejected — these are jaunin.com-style webmaster
        errors where hreflang points at a content section instead of a language root.

        Malformed URLs return False.
        """
        if not candidate_url:
            return False
        try:
            parsed = urlparse(candidate_url)
        except Exception:
            return False

        if not parsed.scheme or not parsed.hostname:
            return False

        def _strip_www(h: str) -> str:
            return h.removeprefix('www.')

        candidate_host = _strip_www(parsed.hostname.lower())
        if candidate_host != _strip_www((homepage_host or '').lower()):
            # Cross-host: trusted (explicit webmaster declaration).
            return True

        segments = [s for s in (parsed.path or '').split('/') if s]
        if not segments:
            return False

        first_segment = segments[0]
        return bool(re.match(r'^[a-z]{2}([-_][a-z]{2,4})?$', first_segment, re.IGNORECASE))

    async def _validate_single_url(self, url: str) -> bool:
        """
        Validates that a URL is reachable and serves HTML content.

        Stratégie en deux phases :
        1. httpx (rapide, léger) — suffisant pour la plupart des sites
        2. Playwright (fallback) — pour les sites avec protection anti-bot
           qui bloquent les requêtes httpx mais acceptent les navigateurs
        """
        # Phase 1 : validation rapide via httpx
        try:
            async with httpx.AsyncClient(
                timeout=settings.HTTP_TIMEOUT,
                follow_redirects=True,
                verify=False,
                proxy=settings.APIFY_PROXY
            ) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    content_type = response.headers.get('content-type', '')
                    if 'text/html' in content_type or 'application/xhtml' in content_type:
                        return True
        except Exception:
            pass

        # Phase 2 : fallback Playwright pour les sites avec protection anti-bot
        try:
            from app.services.scraper import scrape_html
            effective_proxy = settings.APIFY_PROXY
            if effective_proxy:
                result = await scrape_html(url, proxy=effective_proxy)
                if result:
                    content = result.html
                    if content and len(content) > 100:
                        return True
        except Exception:
            pass

        return False

    async def _validate_alternative_urls(
        self,
        candidates: list[dict]
    ) -> list[AlternativeUrl]:
        """
        Validates candidate URLs in parallel with retry.

        For each candidate:
        1. Tries to validate the resolved URL (HTTP 200 + text/html)
        2. If failed and raw_href is relative (no leading / or http),
           retries with / prepended (matches PHP needEditUrl behavior)

        Args:
            candidates: List of dicts with keys: url, raw_href, method, reliability

        Returns:
            List of AlternativeUrl with validated=True/False
        """
        if not candidates:
            return []

        semaphore = asyncio.Semaphore(3)
        base_domain = self.get_domain_from_url(self.homepage)

        async def validate_with_retry(candidate: dict) -> AlternativeUrl:
            resolved_url = candidate['url']
            raw_href = candidate['raw_href']
            hreflang_val = candidate.get('hreflang_value', '')
            priority = self._french_region_priority(resolved_url, hreflang_val)

            async with semaphore:
                # First attempt: validate the resolved URL
                if await self._validate_single_url(resolved_url):
                    return AlternativeUrl(
                        url=resolved_url,
                        method=candidate['method'],
                        reliability=candidate['reliability'],
                        validated=True,
                        region_priority=priority
                    )

                # Retry with / prepended (PHP needEditUrl behavior)
                if (
                    raw_href
                    and not raw_href.startswith('/')
                    and not re.match(r'^https?://', raw_href)
                ):
                    retry_url = self.resolve_url(
                        self.homepage, '/' + raw_href
                    )
                    if retry_url and retry_url != resolved_url:
                        link_domain = self.get_domain_from_url(retry_url)
                        if self._check_base_domain(
                            base_domain, link_domain
                        ):
                            if await self._validate_single_url(retry_url):
                                retry_priority = self._french_region_priority(retry_url, hreflang_val)
                                return AlternativeUrl(
                                    url=retry_url,
                                    method=candidate['method'],
                                    reliability=candidate['reliability'],
                                    validated=True,
                                    region_priority=retry_priority
                                )

                # Validation failed — return as non-validated
                return AlternativeUrl(
                    url=resolved_url,
                    method=candidate['method'],
                    reliability='low',
                    validated=False,
                    region_priority=priority
                )

        results = await asyncio.gather(*[
            validate_with_retry(c) for c in candidates
        ])

        return [r for r in results if r is not None]

    @staticmethod
    def _compare_without_scheme(url1: str, url2: str) -> bool:
        """
        Compare two URLs ignoring scheme (http vs https) and trailing slashes.
        Port of PHP compareWithoutScheme().
        """
        try:
            p1 = urlparse(url1)
            p2 = urlparse(url2)
            return (
                (p1.hostname or '').lower() == (p2.hostname or '').lower()
                and (p1.path or '/').rstrip('/') == (p2.path or '/').rstrip('/')
                and (p1.query or '') == (p2.query or '')
                and (p1.fragment or '') == (p2.fragment or '')
            )
        except Exception:
            return url1 == url2

    def _is_self_url(self, resolved: Optional[str]) -> bool:
        """Check if a resolved URL points to the same page being tested."""
        if not resolved:
            return True
        return self._compare_without_scheme(resolved, self.homepage)

    @staticmethod
    def _french_region_priority(url: str, hreflang_value: str = '') -> int:
        """
        Determine la priorite regionale d'une URL francaise.

        Retourne:
            0 = France specifiquement (fr-FR, fr_FR, /fr/fr, /fr-fr)
            1 = Francais generique (/fr seul, hreflang="fr")
            2 = Autre region francophone (fr-CA, fr-BE, /dz/fr, /ca/fr, ca-fr, be-fr)

        Analyse dans l'ordre : hreflang > URL path > query params.
        Gere les formats normaux et inverses (fr-ca, ca-fr, /fr/dz, /dz/fr).
        """
        hreflang_lower = hreflang_value.strip().lower().replace('_', '-')
        url_lower = url.lower()

        # --- Analyse hreflang (signal le plus fiable) ---
        if hreflang_lower:
            # France : fr-fr
            if hreflang_lower in ('fr-fr',):
                return 0
            # Generique : fr seul
            if hreflang_lower == 'fr':
                return 1
            # Autre region : fr-XX ou XX-fr (ou XX != fr)
            parts = hreflang_lower.split('-')
            if len(parts) == 2:
                if parts[0] == 'fr' and parts[1] != 'fr':
                    return 2  # fr-ca, fr-be, fr-ch, etc.
                if parts[1] == 'fr' and parts[0] != 'fr':
                    return 2  # ca-fr, be-fr, etc.
            # Fallback: contient "fr" d'une maniere ou d'une autre
            return 1

        # --- Analyse URL path ---
        try:
            parsed = urlparse(url_lower)
            path = (parsed.path or '').strip('/')
            query = parsed.query or ''
            segments = [s for s in path.split('/') if s]

            # Patterns France dans le path : fr-fr, fr_fr
            if any(s in ('fr-fr', 'fr_fr') for s in segments):
                return 0

            # Pattern /fr/fr (deux segments fr consecutifs)
            for i in range(len(segments) - 1):
                if segments[i] == 'fr' and segments[i + 1] == 'fr':
                    return 0

            # Patterns autre region dans le path
            # Codes pays ISO 3166-1 alpha-2 courants (hors FR)
            non_france_codes = {
                'ca', 'be', 'ch', 'lu', 'mc', 'dz', 'ma', 'tn', 'sn', 'ci',
                'cm', 'cd', 'cg', 'mg', 'ht', 'ml', 'ne', 'bf', 'bj', 'tg',
                'gn', 'rw', 'bi', 'ga', 'cf', 'td', 'km', 'dj', 'mu', 'sc',
                'us', 'gb', 'uk', 'de', 'es', 'it', 'pt', 'nl', 'at', 'au',
                'nz', 'za', 'in', 'br', 'mx', 'ar', 'co', 'cl', 'pe', 'vn',
                'mea', 'apac', 'emea', 'latam', 'na',  # Codes regions
            }

            # Chercher des patterns XX/fr ou fr/XX ou XX-fr ou fr-XX dans le path
            for s in segments:
                # Segment combine : fr-ca, ca-fr, fr_be, be_fr
                parts = re.split(r'[-_]', s)
                if len(parts) == 2:
                    if parts[0] == 'fr' and parts[1] in non_france_codes:
                        return 2
                    if parts[1] == 'fr' and parts[0] in non_france_codes:
                        return 2

            # Chercher /XX/fr/ ou /fr/XX/ dans les segments adjacents
            for i in range(len(segments) - 1):
                pair = (segments[i], segments[i + 1])
                if pair[0] == 'fr' and pair[1] in non_france_codes:
                    return 2  # /fr/dz, /fr/ca
                if pair[1] == 'fr' and pair[0] in non_france_codes:
                    return 2  # /dz/fr, /ca/fr

            # Si /fr/ est seul (pas accompagne d'un code pays)
            if 'fr' in segments:
                return 1

            # --- Analyse query params ---
            if 'lang=fr-fr' in query or 'lang=fr_fr' in query:
                return 0
            if 'lang=fr' in query:
                # Verifier si c'est lang=fr-XX
                lang_match = re.search(r'lang=fr[-_](\w+)', query)
                if lang_match and lang_match.group(1).lower() != 'fr':
                    return 2
                return 1

        except Exception:
            pass

        # Defaut : generique
        return 1

    async def detect_alternative_languages(self, content: str) -> list[AlternativeUrl]:
        """
        Recherche des liens vers une version française, les valide et les tague.

        Collecte les alternatives depuis TOUTES les méthodes de découverte,
        chacune taguée avec sa méthode et son niveau de fiabilité.
        Les résultats sont triés par fiabilité (high > medium > low)
        et dédupliqués de manière agressive (normalisation d'URL).

        Niveaux de fiabilité :
        - high   : hreflang (déclaration explicite du webmaster, trusted sans HTTP)
        - medium : data-lang/data-gt-lang, liens <a>, options (validés via HTTP)
        - low    : non validé (échec HTTP ou pas de validation)

        L'URL en cours de test (self.homepage) est exclue des résultats.
        """
        if not content:
            return []

        base_domain = self.get_domain_from_url(self.homepage)
        homepage_parsed = urlparse(self.homepage)
        homepage_host = (homepage_parsed.hostname or '').lower()

        # Domaine original (avant redirection) — permet d'accepter les alternatives
        # qui pointent vers le domaine d'origine quand une redirection a changé le domaine.
        # Ex: trojanuv.com → trojantechnologies.com, alternative trouvée: trojanuv.com/fr/
        original_base_domain = self.get_domain_from_url(self.original_homepage)
        has_different_original = (original_base_domain != base_domain)

        seen_urls = set()
        all_alternatives: list[AlternativeUrl] = []
        candidates_to_validate: list[dict] = []

        def _resolve_and_check(href: str) -> Optional[str]:
            """Resolve a href and check domain match + not self URL.
            Accepts URLs matching either the current domain or the original domain (before redirect).
            """
            resolved = self.resolve_url(self.homepage, href)
            if not resolved or self._is_self_url(resolved):
                return None
            link_domain = self.get_domain_from_url(resolved)
            # Vérifier contre le domaine actuel (après redirection)
            if self._check_base_domain(base_domain, link_domain):
                return resolved
            # Vérifier contre le domaine original (avant redirection)
            if has_different_original and self._check_base_domain(original_base_domain, link_domain):
                return resolved
            return None

        def _normalize_url(url: str) -> str:
            """Normalize URL for deduplication (lowercase host, strip trailing /)."""
            try:
                p = urlparse(url)
                base = f"{p.scheme}://{(p.hostname or '').lower()}{(p.path or '/').rstrip('/')}"
                return base + (f"?{p.query}" if p.query else "")
            except Exception:
                return url

        def _add_trusted(resolved: str, method: str, hreflang_value: str = ''):
            """Add a trusted (hreflang) alternative — no HTTP validation needed."""
            normalized = _normalize_url(resolved)
            if normalized not in seen_urls:
                seen_urls.add(normalized)
                priority = self._french_region_priority(resolved, hreflang_value)
                all_alternatives.append(AlternativeUrl(
                    url=resolved,
                    method=method,
                    reliability='high',
                    validated=True,
                    region_priority=priority
                ))

        def _queue_candidate(resolved: str, raw_href: str, method: str, hreflang_value: str = ''):
            """Queue a candidate for HTTP validation."""
            normalized = _normalize_url(resolved)
            if normalized not in seen_urls:
                seen_urls.add(normalized)
                candidates_to_validate.append({
                    'url': resolved,
                    'raw_href': raw_href,
                    'method': method,
                    'reliability': 'medium',
                    'hreflang_value': hreflang_value
                })

        try:
            soup = BeautifulSoup(content, 'lxml')

            # 1. Hreflang (trusted, high reliability)
            # Prioritaire: starts with "fr" (fr, fr-FR, fr-BE)
            # Secondaire: contains "fr" anywhere (be-fr, ca-fr)
            # Note: PAS de vérification de domaine pour hreflang — c'est une déclaration
            # explicite du webmaster. Si le site déclare un hreflang vers un autre domaine,
            # on fait confiance (ex: trojantechnologies.com → trojanuv.com/fr/).
            for regex in [re.compile(r'^fr', re.IGNORECASE), re.compile(r'fr', re.IGNORECASE)]:
                for link in soup.find_all(attrs={'hreflang': regex}):
                    href = link.get('href')
                    hreflang_val = link.get('hreflang', '')
                    if href and href != '#':
                        resolved = self.resolve_url(self.homepage, href)
                        if resolved and not self._is_self_url(resolved):
                            if not self._is_valid_language_alternative(homepage_host, resolved):
                                logger.debug(
                                    f"hreflang rejected (non-language-shaped target): {resolved}"
                                )
                                continue
                            _add_trusted(resolved, 'hreflang', hreflang_value=hreflang_val)

            # 2. data-lang et data-gt-lang (need validation, medium reliability)
            for attr_name in ['data-lang', 'data-gt-lang']:
                method_name = attr_name.replace('-', '_')
                for regex in [re.compile(r'^fr', re.IGNORECASE), re.compile(r'fr', re.IGNORECASE)]:
                    for elem in soup.find_all(attrs={attr_name: regex}):
                        href = elem.get('href')
                        lang_val = elem.get(attr_name, '')
                        if href and href != '#':
                            resolved = _resolve_and_check(href)
                            if resolved:
                                if not self._is_valid_language_alternative(homepage_host, resolved):
                                    logger.debug(
                                        f"{attr_name} rejected (non-language-shaped target): {resolved}"
                                    )
                                    continue
                                _queue_candidate(resolved, href, method_name, hreflang_value=lang_val)

            # 3. Liens <a> avec /fr/ ou lang=fr (need validation, medium reliability)
            fr_pattern = re.compile(
                r'/(fr|fr-fr|fr_fr)(/|$)|lang=fr', re.IGNORECASE
            )
            for link in soup.find_all('a', href=True):
                href = link['href']
                if fr_pattern.search(href) and 'mailto:' not in href:
                    resolved = _resolve_and_check(href)
                    if resolved:
                        _queue_candidate(resolved, href, 'link_pattern')

            # 4. Options <option> avec value fr (need validation, medium reliability)
            # Scanne les <select>/<option> pour :
            #   a) Patterns /fr/ ou lang=fr dans l'URL
            #   b) Domaines .fr apparentés (ex: soprema.fr dans un select de soprema-international.com)
            #   c) Sous-domaines français (ex: fr.domain.com)
            for option in soup.find_all('option'):
                value = option.get('value', '')
                if not value or not value.strip():
                    continue

                # 4a. Pattern /fr/ ou lang=fr
                if re.search(
                    r'(^|/)fr(/|$)|lang=fr', value, re.IGNORECASE
                ):
                    resolved = _resolve_and_check(value)
                    if resolved:
                        _queue_candidate(resolved, value, 'option_tag')
                    continue

                # 4b. Domaine .fr apparenté (même logique que Method 5 mais pour <option>)
                try:
                    opt_parsed = urlparse(value)
                    opt_host = (opt_parsed.hostname or '').lower()
                    if opt_host and opt_host.endswith('.fr') and opt_host != homepage_host:
                        opt_base = self.get_domain_from_url(value)
                        if self._check_base_domain(base_domain, opt_base):
                            resolved = _resolve_and_check(value)
                            if resolved:
                                _queue_candidate(resolved, value, 'option_domain_fr')
                            continue
                except Exception:
                    pass

                # 4c. Sous-domaine français (même logique que Method 6 mais pour <option>)
                try:
                    opt_parsed = urlparse(value)
                    opt_host = (opt_parsed.hostname or '').lower()
                    if opt_host and opt_host != homepage_host:
                        fr_sub_match = re.match(
                            r'^(fr|french|francais|français|france)\.', opt_host, re.IGNORECASE
                        )
                        if fr_sub_match:
                            opt_base = self.get_domain_from_url(value)
                            if self._check_base_domain(base_domain, opt_base):
                                resolved = _resolve_and_check(value)
                                if resolved:
                                    _queue_candidate(resolved, value, 'option_subdomain_fr')
                except Exception:
                    pass

            # 5. Liens <a> pointant vers un domaine .fr apparenté
            # Ex: essity.com → essity.fr (même base de domaine avec TLD .fr)
            # Ne capture que les liens vers des domaines .fr qui partagent le même
            # nom de domaine principal (évite les faux positifs vers des .fr sans rapport)
            # Note: homepage_parsed et homepage_host sont définis en haut de la méthode
            if not homepage_host.endswith('.fr'):
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    if 'mailto:' in href:
                        continue
                    try:
                        link_parsed = urlparse(href)
                        link_host = (link_parsed.hostname or '').lower()
                        if link_host.endswith('.fr') and link_host != homepage_host:
                            # Vérifier que le domaine principal est le même
                            # Ex: essity.com et essity.fr partagent "essity"
                            link_base = self.get_domain_from_url(href)
                            if self._check_base_domain(base_domain, link_base):
                                resolved = _resolve_and_check(href)
                                if resolved:
                                    _queue_candidate(resolved, href, 'domain_fr_link')
                    except Exception:
                        continue

            # 6. Liens <a> pointant vers un sous-domaine français
            # Ex: swann-morton.com → fr.swann-morton.com
            # Capture les patterns : fr.domain.com, french.domain.com,
            # francais.domain.com, france.domain.com
            fr_subdomain_pattern = re.compile(
                r'^(fr|french|francais|français|france)\.', re.IGNORECASE
            )
            homepage_has_fr_subdomain = bool(fr_subdomain_pattern.match(homepage_host))
            if not homepage_has_fr_subdomain:
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    if 'mailto:' in href:
                        continue
                    try:
                        link_parsed = urlparse(href)
                        link_host = (link_parsed.hostname or '').lower()
                        if link_host and link_host != homepage_host and fr_subdomain_pattern.match(link_host):
                            link_base = self.get_domain_from_url(href)
                            if self._check_base_domain(base_domain, link_base):
                                resolved = _resolve_and_check(href)
                                if resolved:
                                    _queue_candidate(resolved, href, 'subdomain_fr')
                    except Exception:
                        continue

        except Exception:
            pass

        # Validate candidates via HTTP (parallel, max 3 concurrent)
        validated_results = await self._validate_alternative_urls(candidates_to_validate)
        all_alternatives.extend(validated_results)

        # Sort by: 1) reliability (high > medium > low), 2) region priority (France > generic > other)
        reliability_order = {'high': 0, 'medium': 1, 'low': 2}
        all_alternatives.sort(key=lambda a: (
            reliability_order.get(a.reliability, 3),
            a.region_priority
        ))

        return all_alternatives[:10]
    
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
        # Logique alignée sur le pipeline normal (Cases 2a/2b/4/5) :
        # - HTML tag confirme FR → signal fort (comme TLD .fr dans Case 2)
        # - NLP confirme → ACCEPT (Case 1)
        # - NLP soft/indisponible/faible contradiction → ACCEPT avec confiance réduite
        # - NLP contredit fortement (>0.9) → REJECT (Case 2a)
        if self.forced_method:
            lang_check = self.language_detector.detect_from_html_tags(content)
            if lang_check and lang_check.get('method') == self.forced_method and lang_check.get('value') == 'fr':
                # NLP avec cross-check (même logique que le pipeline normal, lignes 897-918)
                nlp_result = self.language_detector.detect_from_text_content_fasttext(content)

                if nlp_result is None:
                    nlp_result = self.language_detector.detect_from_text_content(content)
                elif nlp_result.get('lang') != 'fr' and nlp_result.get('confidence', 0) < 0.75:
                    secondary = self.language_detector.detect_from_text_content(content)
                    if secondary and secondary.get('lang') == 'fr':
                        logger.info(
                            f"[forced_method] Cross-check langdetect+langid confirme FR "
                            f"(confiance={secondary.get('confidence', 0):.3f}) — "
                            f"fastText avait détecté {nlp_result.get('lang')}"
                        )
                        nlp_result = secondary

                nlp_lang = nlp_result.get('lang') if nlp_result else None
                nlp_confidence = nlp_result.get('confidence', 0) if nlp_result else 0.0

                if nlp_result and nlp_lang == 'fr' and nlp_confidence >= settings.NLP_MIN_CONFIDENCE:
                    return DetectionResponse(
                        ok=True,
                        url=url,
                        method=f"{self.forced_method}+nlp_confirmed",
                        confidence=nlp_confidence
                    )
                elif nlp_result and nlp_lang == 'fr':
                    return DetectionResponse(
                        ok=True,
                        url=url,
                        method=f"{self.forced_method}+nlp_soft_confirmed",
                        confidence=nlp_confidence
                    )
                elif nlp_result is None:
                    return DetectionResponse(
                        ok=True,
                        url=url,
                        method=f"{self.forced_method}+nlp_skipped",
                        confidence=0.6
                    )
                elif nlp_lang != 'fr' and nlp_confidence >= 0.9:
                    logger.info(
                        f"[forced_method] HTML {self.forced_method}=fr mais NLP détecte "
                        f"{nlp_lang} avec confiance {nlp_confidence:.3f} — rejet"
                    )
                    return DetectionResponse(
                        ok=False,
                        url=url,
                        method='Check_nok_forced',
                        confidence=nlp_confidence,
                        error=f"HTML {self.forced_method} indique FR mais contenu détecté comme {nlp_lang} ({nlp_confidence:.0%})"
                    )
                else:
                    logger.info(
                        f"[forced_method] HTML {self.forced_method}=fr, NLP faiblement contredit "
                        f"({nlp_lang}={nlp_confidence:.3f}) — accepté avec confiance réduite"
                    )
                    return DetectionResponse(
                        ok=True,
                        url=url,
                        method=f"{self.forced_method}+nlp_weak_disagree_{nlp_lang}",
                        confidence=0.6
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
            alternatives = await self.detect_alternative_languages(content)
        
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

            # Guard : si NLP est indisponible PARCE QUE le contenu est vide/trop court,
            # c'est un signe que le site est inaccessible (502, erreur proxy, etc.).
            # Ne PAS faire confiance au TLD dans ce cas.
            if not nlp_available:
                try:
                    soup_check = BeautifulSoup(content, 'lxml')
                    for el in soup_check(['script', 'style', 'meta', 'link', 'noscript']):
                        el.decompose()
                    visible_text = soup_check.get_text(separator=' ', strip=True)
                except Exception:
                    visible_text = ''

                if len(visible_text) < settings.NLP_MIN_TEXT_LENGTH:
                    return DetectionResponse(
                        ok=False,
                        url=url,
                        method='fetch_empty_content',
                        alternative_urls=alternatives,
                        error=f"TLD .fr mais contenu insuffisant ({len(visible_text)} caractères) — site probablement inaccessible"
                    )

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
        
        # Cas 6 : Liens alternatifs français validés/trusted trouvés
        # Exécute la détection complète (fetch + NLP) sur les meilleures alternatives
        # pour confirmer qu'elles sont réellement en français, pas juste accessibles.
        reliable_alternatives = [a for a in alternatives if a.validated]
        if reliable_alternatives:
            challenge_blocked_count = 0
            challenge_blocked_service = None
            fetch_failed_count = 0

            for alt_candidate in reliable_alternatives:
                try:
                    alt_content_result = await asyncio.wait_for(
                        fetch_html(alt_candidate.url), timeout=120
                    )
                    if not alt_content_result:
                        logger.warning(f"Impossible de récupérer le contenu de l'alternative {alt_candidate.url}")
                        fetch_failed_count += 1
                        continue

                    alt_content = alt_content_result.html
                    alt_final_url = alt_content_result.final_url

                    # Vérifier que ce n'est pas une page de challenge
                    from app.services.language_detector import detect_challenge_page
                    challenge_service = detect_challenge_page(alt_content)
                    if challenge_service:
                        logger.warning(f"Page de challenge {challenge_service} détectée sur l'alternative {alt_candidate.url}")
                        challenge_blocked_count += 1
                        challenge_blocked_service = challenge_service
                        continue

                    # Détection HTML tags sur l'alternative
                    alt_html_result = self.language_detector.detect_combined(alt_content, use_nlp=False)
                    alt_html_french = alt_html_result.get('detected') and alt_html_result.get('is_french')

                    # Détection NLP sur l'alternative
                    alt_nlp = self.language_detector.detect_from_text_content_fasttext(alt_content)
                    if alt_nlp is None:
                        alt_nlp = self.language_detector.detect_from_text_content(alt_content)

                    alt_nlp_lang = alt_nlp.get('lang') if alt_nlp else None
                    alt_nlp_confidence = alt_nlp.get('confidence', 0) if alt_nlp else 0.0
                    alt_nlp_french = alt_nlp_lang == 'fr' and alt_nlp_confidence >= settings.NLP_MIN_CONFIDENCE

                    if alt_nlp_french:
                        # Alternative confirmée française par NLP
                        alt_method_parts = [f'alternative_{alt_candidate.method}']
                        if alt_html_french:
                            alt_method_parts.append('html_confirmed')
                        alt_method_parts.append('nlp_confirmed')

                        logger.info(
                            f"Alternative {alt_candidate.url} confirmée française "
                            f"(NLP: {alt_nlp_lang} {alt_nlp_confidence:.3f})"
                        )
                        return DetectionResponse(
                            ok=True,
                            url=alt_final_url or alt_candidate.url,
                            method='+'.join(alt_method_parts),
                            alternative_urls=alternatives,
                            confidence=alt_nlp_confidence
                        )
                    elif alt_html_french:
                        # HTML dit français mais NLP ne confirme pas (texte court ?)
                        # Accepté avec confiance réduite
                        logger.info(
                            f"Alternative {alt_candidate.url} détectée française par HTML "
                            f"(NLP indisponible ou non confirmé)"
                        )
                        return DetectionResponse(
                            ok=True,
                            url=alt_final_url or alt_candidate.url,
                            method=f'alternative_{alt_candidate.method}+html_confirmed+nlp_skipped',
                            alternative_urls=alternatives,
                            confidence=0.6
                        )
                    else:
                        logger.info(
                            f"Alternative {alt_candidate.url} non confirmée française "
                            f"(NLP: {alt_nlp_lang} {alt_nlp_confidence:.3f}), "
                            f"essai suivant..."
                        )
                        continue

                except asyncio.TimeoutError:
                    logger.warning(f"Timeout fetch alternative {alt_candidate.url} (120s)")
                    fetch_failed_count += 1
                    continue
                except Exception as alt_e:
                    logger.warning(f"Erreur vérification alternative {alt_candidate.url}: {alt_e}")
                    fetch_failed_count += 1
                    continue

            # Si toutes les alternatives ont échoué (challenge + fetch failures),
            # retourner une erreur spécifique au lieu de Check_nok_v2
            total_failures = challenge_blocked_count + fetch_failed_count
            if total_failures > 0 and total_failures == len(reliable_alternatives):
                # Déterminer le type d'erreur principal
                if challenge_blocked_count > 0 and challenge_blocked_count >= fetch_failed_count:
                    if challenge_blocked_service == 'Cloudflare_blocked':
                        error_msg = 'Alternative(s) française(s) trouvée(s) mais bloquée(s) par Cloudflare WAF'
                    else:
                        error_msg = f'Alternative(s) française(s) trouvée(s) mais bloquée(s) par {challenge_blocked_service}'
                    method = 'challenge_page'
                else:
                    error_msg = "Alternative(s) française(s) trouvée(s) mais impossible de récupérer le contenu"
                    method = 'fetch_failed'

                logger.warning(
                    f"Toutes les alternatives ({len(reliable_alternatives)}) inaccessibles pour {url} "
                    f"(challenge: {challenge_blocked_count}, fetch_failed: {fetch_failed_count})"
                )
                return DetectionResponse(
                    ok=False,
                    url=url,
                    method=method,
                    alternative_urls=alternatives,
                    error=error_msg
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
        # Uniquement si NLP n'est pas disponible (texte trop court, modèle absent).
        # Si NLP a détecté une autre langue, le signal lexical ne doit JAMAIS
        # outrepasser le NLP — sinon des sites allemands/espagnols/etc. avec
        # quelques mots français (navigation, footer) seraient faussement détectés.
        if not nlp_available:
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

    async def check_page_if_french_debug(
        self,
        content: str,
        mode: DetectionMode = DetectionMode.COMPLETE,
        fetched_by: str = 'api',
        include_full_content: bool = False,
        redirected_from: Optional[str] = None,
        challenge_detected: Optional[str] = None
    ) -> DebugDetectionResponse:
        """
        Version debug de check_page_if_french qui collecte les informations
        de chaque etape du pipeline pour diagnostic.

        Args:
            content: Contenu HTML de la page
            mode: Mode de detection (simple ou complete)
            fetched_by: 'api' si recupere par Playwright, 'provided' si fourni
            include_full_content: Si True, inclut le HTML complet et le texte nettoye complet
            redirected_from: URL d'origine avant redirection (None si pas de redirection)
            challenge_detected: Nom du service de protection anti-bot detecte (None si contenu reel)

        Returns:
            DebugDetectionResponse avec le resultat + infos debug
        """
        url = self.homepage

        # --- Debug: Fetch info ---
        debug_fetch = DebugFetchInfo(
            fetched_by=fetched_by,
            raw_html_length=len(content) if content else 0,
            raw_html_preview=(content[:500] if content else ''),
            raw_html_full=content if (include_full_content and content) else None,
            redirected_from=redirected_from,
            challenge_detected=challenge_detected
        )

        # --- Debug: Cleaning info ---
        cleaned_text = self.language_detector.clean_html_to_text(content) if content else None
        debug_cleaning = DebugCleaningInfo(
            cleaned_text_length=len(cleaned_text) if cleaned_text else 0,
            cleaned_text_preview=(cleaned_text[:500] if cleaned_text else ''),
            cleaned_text_full=cleaned_text if (include_full_content and cleaned_text) else None
        )

        # --- Etape 1: URL check ---
        url_check = await self.check_url(url, track_redirect=False)
        url_indicates_french = url_check.get('ok', False)
        url_method = url_check.get('method', '')
        is_strong_url = self._is_strong_french_url(url)

        debug_url_check = DebugUrlCheckInfo(
            ok=url_indicates_french,
            method=url_method,
            is_strong_url=is_strong_url
        )

        # --- Etape 2: HTML tags ---
        lang_result = self.language_detector.detect_combined(content, use_nlp=False) if content else {}
        html_indicates_french = lang_result.get('detected') and lang_result.get('is_french')
        html_method = lang_result.get('method', '')

        debug_html_tags = DebugHtmlTagsInfo(
            detected=bool(lang_result.get('detected')),
            is_french=bool(html_indicates_french),
            method=html_method or None,
            value=lang_result.get('value')
        )

        # --- Etape 3: NLP ---
        nlp_result = None
        if content:
            nlp_result = self.language_detector.detect_from_text_content_fasttext(content)

            if nlp_result is None:
                nlp_result = self.language_detector.detect_from_text_content(content)
            elif nlp_result.get('lang') != 'fr' and nlp_result.get('confidence', 0) < 0.75:
                secondary_result = self.language_detector.detect_from_text_content(content)
                if secondary_result and secondary_result.get('lang') == 'fr':
                    nlp_result = secondary_result

        nlp_lang = nlp_result.get('lang') if nlp_result else None
        nlp_confidence = nlp_result.get('confidence', 0) if nlp_result else 0.0
        nlp_available = nlp_result is not None

        nlp_confirms_french = nlp_available and nlp_lang == 'fr' and nlp_confidence >= settings.NLP_MIN_CONFIDENCE
        nlp_soft_french = nlp_available and nlp_lang == 'fr' and nlp_confidence < settings.NLP_MIN_CONFIDENCE
        nlp_contradicts_french = nlp_available and nlp_lang is not None and nlp_lang != 'fr'
        nlp_strongly_contradicts = nlp_contradicts_french and nlp_confidence > 0.9

        debug_nlp = DebugNlpInfo(
            available=nlp_available,
            lang=nlp_lang,
            confidence=nlp_confidence if nlp_available else None,
            method=nlp_result.get('method') if nlp_result else None,
            details=nlp_result.get('details') if nlp_result else None,
            confirms_french=nlp_confirms_french,
            soft_french=nlp_soft_french,
            contradicts_french=nlp_contradicts_french,
            strongly_contradicts=nlp_strongly_contradicts
        )

        # --- Etape 4: Alternatives ---
        alternatives = []
        if mode == DetectionMode.COMPLETE and content:
            alternatives = await self.detect_alternative_languages(content)

        debug_alternatives = DebugAlternativesInfo(
            candidates_found=len(alternatives),
            candidates=alternatives
        )

        # --- Run actual detection to get the result ---
        # Si une page de challenge a été détectée, on override le résultat
        # pour éviter un faux positif (le contenu analysé est celui du challenge, pas du site)
        if challenge_detected:
            result = DetectionResponse(
                ok=False,
                url=url,
                method='challenge_page',
                error=f'Contenu bloqué par {challenge_detected} (page de challenge/CAPTCHA détectée)'
            )
            decision = f"Challenge page detected ({challenge_detected}) — result overridden to ok=false"
        else:
            result = await self.check_page_if_french(content, mode)

            # --- Determine which decision case was applied ---
            decision = self._identify_decision_case(
                nlp_confirms_french, is_strong_url, nlp_strongly_contradicts,
                nlp_soft_french, nlp_available, nlp_contradicts_french,
                url_indicates_french, html_indicates_french, alternatives,
                result
            )

        debug_info = DebugInfo(
            fetch=debug_fetch,
            cleaning=debug_cleaning,
            url_check=debug_url_check,
            html_tags=debug_html_tags,
            nlp=debug_nlp,
            alternatives=debug_alternatives,
            decision=decision
        )

        return DebugDetectionResponse(
            result=result,
            debug=debug_info
        )

    @staticmethod
    def _identify_decision_case(
        nlp_confirms_french: bool,
        is_strong_url: bool,
        nlp_strongly_contradicts: bool,
        nlp_soft_french: bool,
        nlp_available: bool,
        nlp_contradicts_french: bool,
        url_indicates_french: bool,
        html_indicates_french: bool,
        alternatives: list,
        result: DetectionResponse
    ) -> str:
        """Identifie le cas de decision applique pour le debug."""
        method = result.method

        if nlp_confirms_french:
            return "Case 1: NLP confirms French"

        if is_strong_url:
            if nlp_strongly_contradicts:
                return "Case 2a: TLD .fr but NLP strongly contradicts"
            return "Case 2b: TLD .fr trusted (NLP soft/skipped/weak disagree)"

        if url_indicates_french and nlp_soft_french:
            return "Case 3: Moderate URL signal + NLP soft French"

        if html_indicates_french and nlp_soft_french:
            return "Case 4: HTML indicates French + NLP soft French"

        if not nlp_available and (html_indicates_french or url_indicates_french):
            return "Case 5: NLP unavailable + HTML/URL signals"

        reliable_alts = [a for a in alternatives if a.validated]
        if reliable_alts:
            return f"Case 6: Alternative French URL found ({reliable_alts[0].method})"

        if nlp_available and (html_indicates_french or url_indicates_french):
            return "Case 7: NLP does not confirm despite HTML/URL indicators"

        if not nlp_available and 'french_lexical_signal' in method:
            return "Case 8: Last resort — French lexical signal (NLP unavailable)"

        return "Case 9: No French indicators found"
