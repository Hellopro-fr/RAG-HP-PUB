import asyncio
import logging
import os
import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

from app.core.config import settings
from app.core.metrics import BROWSER_LAUNCH_DURATION

try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


@dataclass
class ScrapeResult:
    """Result of a Playwright scrape: HTML body + final URL + HTTP status + headers.

    status_code is 0 when Playwright returned no Response object (rare —
    happens when navigation aborts before any response is received).
    """
    html: str
    final_url: str
    status_code: int
    content_type: str = ""
    headers: dict = field(default_factory=dict)


def build_proxy_url(base_proxy: str, session_id: Optional[str] = None, country: Optional[str] = 'FR') -> str:
    """
    Construit une URL proxy Apify avec ciblage pays et session sticky optionnelle.

    Country targeting : cible les IPs du pays spécifié (meilleure compatibilité).
    Session sticky (optionnelle) : garantit la même IP pour toute la durée d'une session.
    À utiliser uniquement pour la résolution de challenges (Cloudflare) qui nécessite
    une IP stable. Pour le fetching normal, laisser session_id=None et laisser
    Apify utiliser sa rotation intelligente (IP la plus anciennement utilisée par hostname).

    Note sur les sessions Apify datacenter :
    - Les sessions persistent 26h (renouvelées à chaque requête)
    - Chaque session verrouille une IP du pool partagé
    - Le pool est limité par plan → éviter de créer trop de sessions

    Format Apify :
      - Sans session ni country : http://auto:{password}@proxy.apify.com:8000
      - Avec country seul : http://country-FR:{password}@proxy.apify.com:8000
      - Avec session seule : http://session-{id}:{password}@proxy.apify.com:8000
      - Avec les deux : http://country-FR,session-{id}:{password}@proxy.apify.com:8000

    Args:
        base_proxy: URL proxy de base (format: http://auto:{password}@proxy.apify.com:8000)
        session_id: Identifiant de session sticky. None = pas de session (rotation auto Apify).
        country: Code pays ISO 2 lettres (défaut: 'FR'). None pour désactiver.

    Returns:
        URL proxy modifiée avec country et/ou session.
    """
    try:
        parsed = urlparse(base_proxy)
        password = parsed.password

        if not password:
            logger.warning(f"Pas de mot de passe dans l'URL proxy, retour proxy de base")
            return base_proxy

        # Construire le username avec country et/ou session
        username_parts = []
        if country:
            username_parts.append(f"country-{country}")
        if session_id:
            username_parts.append(f"session-{session_id}")

        # Si aucun paramètre, utiliser 'auto' (rotation intelligente Apify)
        username = ','.join(username_parts) if username_parts else 'auto'

        # Masquer le mot de passe dans les logs
        masked = f"{parsed.scheme}://{username}:****@{parsed.hostname}:{parsed.port}"
        logger.warning(f"[PROXY] URL construite: {masked}")

        return f"{parsed.scheme}://{username}:{password}@{parsed.hostname}:{parsed.port}"

    except Exception as e:
        logger.warning(f"Erreur construction proxy URL: {e}, retour proxy de base")
        return base_proxy

# Sémaphore global limitant le nombre de navigateurs Playwright simultanés.
# Taille configurable via BROWSER_SEMAPHORE_SIZE env var (défaut: 10).
# Chaque Camoufox/Chromium consomme ~300-500 MB — ne pas dépasser la capacité du container.
_BROWSER_SEMAPHORE_SIZE = int(os.getenv("BROWSER_SEMAPHORE_SIZE", "10"))
_BROWSER_SEMAPHORE = asyncio.Semaphore(_BROWSER_SEMAPHORE_SIZE)


# Pool de User-Agents réalistes — rotation aléatoire à chaque requête
# Aligné sur la configuration du crawler-service (Firefox, Chrome, Safari × Windows, macOS, Linux)
_USER_AGENTS = [
    # Chrome — Windows
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    # Chrome — macOS
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    # Chrome — Linux
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    # Firefox — Windows
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
    # Firefox — macOS
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0',
    # Firefox — Linux
    'Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0',
    # Safari — macOS
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
]

# Extensions de fichiers lourds à bloquer (aligné sur crawler-service)
_BLOCKED_RESOURCE_EXTENSIONS = (
    '.pdf', '.zip', '.rar', '.doc', '.docx', '.xls', '.xlsx',
    '.exe', '.bin', '.iso', '.dmg', '.7z', '.bz2', '.tar', '.xz',
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tif', '.tiff', '.webp', '.svg', '.ico',
    '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v',
    '.mp3', '.wav', '.ogg', '.aac', '.mid',
    '.ppt', '.pptx', '.apk', '.css', '.rss',
)


# Erreurs de navigation permanentes — extraction partielle inutile (aucun contenu chargé).
# Re-raise vers fetch_html pour classification (variant-eligible vs fatal) et fallback Phase 2.
_PERMANENT_NAV_ERRORS = (
    'ERR_CONNECTION_REFUSED',
    'ERR_NAME_NOT_RESOLVED',
    'ERR_SSL_PROTOCOL_ERROR',
    'ERR_CERT_DATE_INVALID',
)

# Import de la détection de challenge centralisée (évite la duplication)
from app.services.language_detector import detect_challenge_page as _detect_challenge_page


def _parse_proxy(proxy: str) -> Optional[dict]:
    """
    Convertit une URL proxy httpx vers le format Playwright.

    Args:
        proxy: URL proxy au format http://user:pass@host:port

    Returns:
        Dict Playwright proxy ou None en cas d'erreur
    """
    try:
        parsed = urlparse(proxy)
        playwright_proxy = {"server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"}
        if parsed.username:
            playwright_proxy["username"] = parsed.username
        if parsed.password:
            playwright_proxy["password"] = parsed.password
        return playwright_proxy
    except Exception:
        logger.warning(f"Échec parsing URL proxy pour Playwright: {proxy}")
        return None


async def _launch_browser(playwright_instance, playwright_proxy: Optional[dict] = None):
    """
    Lance un navigateur Camoufox (stealth Firefox) ou Playwright Chromium (fallback).

    Camoufox gère le fingerprinting au niveau C++ du moteur Firefox :
    navigator.webdriver, WebGL, WebRTC, AudioContext, screen dimensions.
    Pas besoin de rotation User-Agent manuelle — Camoufox le fait nativement.

    Args:
        playwright_instance: Instance Playwright (depuis async_playwright())
        playwright_proxy: Dict proxy au format Playwright (optionnel pour Camoufox)

    Returns:
        Tuple (browser, is_camoufox: bool) — le browser est un objet Playwright standard.
    """
    if settings.CAMOUFOX_ENABLED:
        try:
            from camoufox import AsyncNewBrowser

            # Camoufox accepts proxy in the same Playwright dict format
            t0 = time.monotonic()
            browser = await asyncio.wait_for(
                AsyncNewBrowser(
                    playwright_instance,
                    headless=True,
                    proxy=playwright_proxy,
                    geoip=True,
                ),
                timeout=45,
            )
            BROWSER_LAUNCH_DURATION.labels(browser="camoufox").observe(time.monotonic() - t0)
            logger.info("Navigateur Camoufox (stealth Firefox) lancé")
            return browser, True

        except ImportError:
            logger.warning("Package camoufox non installé, fallback vers Chromium")
        except asyncio.TimeoutError:
            logger.warning("Timeout lancement Camoufox (45s), fallback vers Chromium")
        except Exception as e:
            logger.warning(f"Erreur lancement Camoufox: {e}, fallback vers Chromium")

    # Fallback: Playwright Chromium
    t0 = time.monotonic()
    browser = await playwright_instance.chromium.launch(
        headless=True,
        proxy=playwright_proxy,
        args=[
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-gpu',
            '--disable-blink-features=AutomationControlled',
        ],
    )
    BROWSER_LAUNCH_DURATION.labels(browser="chromium").observe(time.monotonic() - t0)
    logger.info("Navigateur Playwright Chromium lancé (fallback)")
    return browser, False


async def _setup_resource_blocking(page) -> None:
    """
    Configure le blocage des ressources lourdes sur une page Playwright.

    Bloque images, media, fonts, stylesheets et fichiers binaires —
    aligné sur la configuration du crawler-service pour réduire la
    bande passante et accélérer le chargement.
    """
    async def _route_handler(route):
        request = route.request
        resource_type = request.resource_type

        # Bloquer les types de ressources lourdes
        if resource_type in ('image', 'media', 'font', 'stylesheet'):
            await route.abort()
            return

        # Bloquer les fichiers binaires par extension
        req_url = request.url.lower()
        if any(req_url.endswith(ext) for ext in _BLOCKED_RESOURCE_EXTENSIONS):
            await route.abort()
            return

        # Bloquer les patterns connus du crawler-service
        if 'download.php' in req_url or 'imp=1' in req_url:
            await route.abort()
            return

        await route.continue_()

    await page.route('**/*', _route_handler)


async def _inject_cookie_consent(context, url: str) -> None:
    """
    Injecte un cookie de consentement accepté — aligné sur le crawler-service.

    Évite les bannières cookies qui peuvent masquer le contenu réel
    et biaiser la détection de langue.
    """
    try:
        parsed = urlparse(url)
        domain = parsed.hostname
        if domain:
            await context.add_cookies([{
                'name': 'cookieConsent',
                'value': 'accepted',
                'domain': domain,
                'path': '/',
            }])
    except Exception:
        pass


async def scrape_html(url: str, timeout: int = 90, proxy: Optional[str] = None) -> Optional[ScrapeResult]:
    """
    Récupère le contenu HTML d'une URL via Playwright avec proxy obligatoire.

    Configuration alignée sur le crawler-service :
    - Rotation de User-Agent (Firefox, Chrome, Safari × Windows, macOS, Linux)
    - Blocage des ressources lourdes (images, media, fonts, stylesheets)
    - Acceptation automatique des cookies
    - Attente networkidle pour le rendu JavaScript complet
    - Timeout de navigation à 90s (identique crawler-service)

    Args:
        url: URL à scraper
        timeout: Timeout en secondes pour le chargement de la page (défaut: 90)
        proxy: Proxy URL obligatoire (format: http://user:pass@host:port)

    Returns:
        ScrapeResult (html, final_url, status_code, content_type, headers) ou None en cas d'erreur.
        status_code est 0 si Playwright n'a retourné aucun objet Response.
        final_url est l'URL après redirections (peut différer de l'URL d'entrée).
    """
    if async_playwright is None:
        logger.error(
            "Playwright non installé. Installez-le avec: "
            "pip install playwright && python -m playwright install chromium"
        )
        return None

    if not proxy:
        logger.error(f"Proxy obligatoire pour scrape_html: {url}")
        return None

    playwright_proxy = _parse_proxy(proxy)
    if not playwright_proxy:
        logger.error(f"Proxy invalide pour {url}: {proxy}")
        return None

    async with _BROWSER_SEMAPHORE:
        async with async_playwright() as p:
            browser, is_camoufox = await _launch_browser(p, playwright_proxy)
            context = None
            page = None
            try:
                # Camoufox handles UA/fingerprinting at engine level — only set for Chromium
                context_options = {
                    'locale': 'fr-FR',
                    'ignore_https_errors': True,  # Gère ERR_CERT_DATE_INVALID, ERR_SSL_PROTOCOL_ERROR
                    'extra_http_headers': {
                        'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
                    },
                }
                if not is_camoufox:
                    context_options['user_agent'] = random.choice(_USER_AGENTS)

                context = await browser.new_context(**context_options)

                # Injection cookie de consentement (comme crawler-service)
                await _inject_cookie_consent(context, url)

                page = await context.new_page()

                # Blocage des ressources lourdes (comme crawler-service)
                await _setup_resource_blocking(page)

                # Navigation en deux phases :
                # Phase 1 : domcontentloaded avec timeout réduit à 30s
                #   Si un site ne retourne pas le HTML initial en 30s, 90s ne changera rien.
                #   Les pages Cloudflare challenge chargent en < 5s.
                # Phase 2 : networkidle avec timeout court (bonus JS rendering)
                nav_timeout = min(timeout, 30) * 1000  # Max 30s pour domcontentloaded
                response = None  # initialise avant le try pour rester en scope
                try:
                    response = await page.goto(url, wait_until='domcontentloaded', timeout=nav_timeout)
                except Exception as nav_e:
                    err_str = str(nav_e)
                    # Erreurs permanentes — re-raise pour que fetch_html puisse
                    # classifier l'erreur et basculer vers les variantes URL (Phase 2)
                    if any(err in err_str for err in _PERMANENT_NAV_ERRORS):
                        logger.error(f"Erreur navigation permanente pour {url}: {err_str.splitlines()[0]}")
                        raise  # finally block will close context + browser

                    # Erreurs transitoires (proxy, timeout) — on tente l'extraction partielle
                    logger.warning(f"Timeout/Erreur navigation pour {url} (extraction partielle tentée): {nav_e}")

                # Phase 2 : attendre networkidle avec un timeout court (5s bonus)
                try:
                    await page.wait_for_load_state('networkidle', timeout=5000)
                except Exception:
                    pass

                # Récupérer le HTML — avec retry si la page est en cours de navigation
                content = None
                for content_attempt in range(3):
                    try:
                        content = await page.content()
                        break
                    except Exception as content_e:
                        if 'navigating and changing the content' in str(content_e):
                            logger.warning(f"Page en navigation pour {url}, attente 1s (tentative {content_attempt + 1}/3)")
                            await page.wait_for_timeout(1000)
                        else:
                            logger.warning(f"Erreur page.content() pour {url}: {content_e}")
                            break

                # Phase 3 : Détection de page de challenge (Cloudflare, DataDome, etc.)
                # Si une page de challenge est détectée, poll le contenu toutes les 3s
                # en attendant que le challenge se résolve (redirection ou remplacement DOM).
                # Utilise un polling loop plutôt que wait_for_function car les challenges
                # Cloudflare font souvent une navigation complète (qui détruit le contexte JS).
                if content:
                    challenge_service = _detect_challenge_page(content)
                    if challenge_service:
                        logger.info(
                            f"Page de challenge {challenge_service} détectée pour {url}, "
                            f"polling résolution (max 45s, intervalle 3s)..."
                        )
                        import time as _time
                        poll_start = _time.time()
                        poll_timeout = 45  # secondes
                        poll_interval = 3  # secondes
                        challenge_resolved = False

                        while (_time.time() - poll_start) < poll_timeout:
                            await page.wait_for_timeout(poll_interval * 1000)

                            try:
                                content = await page.content()
                            except Exception as poll_e:
                                # Le contexte peut être détruit pendant une navigation
                                logger.debug(f"Erreur content() pendant polling challenge pour {url}: {poll_e}")
                                await page.wait_for_timeout(1000)
                                try:
                                    content = await page.content()
                                except Exception:
                                    continue

                            if not _detect_challenge_page(content):
                                challenge_resolved = True
                                elapsed = round(_time.time() - poll_start, 1)
                                logger.info(
                                    f"Challenge {challenge_service} résolu pour {url} "
                                    f"après {elapsed}s ({len(content)} caractères)"
                                )
                                # Attendre que le contenu soit stable
                                try:
                                    await page.wait_for_load_state('networkidle', timeout=5000)
                                except Exception:
                                    pass
                                # Re-extraire le contenu final
                                try:
                                    content = await page.content()
                                except Exception:
                                    pass
                                break
                            else:
                                elapsed = round(_time.time() - poll_start, 1)
                                logger.debug(
                                    f"Challenge toujours présent pour {url} ({elapsed}s/{poll_timeout}s)"
                                )

                        if not challenge_resolved:
                            logger.warning(
                                f"Timeout polling challenge {challenge_service} pour {url} "
                                f"après {poll_timeout}s"
                            )

                # Capturer l'URL finale (après redirections éventuelles)
                final_url = page.url

                # Do NOT close here — finally block handles it.
                if content and len(content) > 100:
                    if final_url != url:
                        logger.info(f"Scraping réussi pour {url} → {final_url} ({len(content)} caractères)")
                    else:
                        logger.info(f"Scraping réussi pour {url} ({len(content)} caractères)")
                    content_type = response.headers.get('content-type', '') if response else ''
                    status_code = response.status if response else 0
                    headers = dict(response.headers) if response else {}
                    return ScrapeResult(
                        html=content,
                        final_url=final_url,
                        status_code=status_code,
                        content_type=content_type,
                        headers=headers,
                    )
                else:
                    logger.warning(f"Contenu trop court pour {url}")
                    return None
            finally:
                # Drain in-flight route callbacks before tearing down the page.
                # Suppresses TargetClosedError flood from _route_handler firing
                # on closed pages under concurrent load.
                if page is not None:
                    try:
                        await page.unroute_all(behavior='ignoreErrors')
                    except Exception as unroute_err:
                        logger.debug(f"unroute_all failed for {url}: {unroute_err}")
                if context is not None:
                    try:
                        await context.close()
                    except Exception as ctx_err:
                        logger.debug(f"context.close failed for {url}: {ctx_err}")
                try:
                    await browser.close()
                except Exception as br_err:
                    logger.debug(f"browser.close failed for {url}: {br_err}")


async def scrape_html_with_redirects(
    url: str,
    timeout: int = 90,
    proxy: Optional[str] = None
) -> Optional[dict]:
    """
    Récupère le contenu HTML et suit les redirections via Playwright.

    Utilisé par RedirectTracker pour le suivi de redirections avec la
    même qualité de rendu que scrape_html.

    Args:
        url: URL à suivre
        timeout: Timeout en secondes (défaut: 90)
        proxy: Proxy URL obligatoire (format: http://user:pass@host:port)

    Returns:
        Dict avec success, final_url, status_code, content_type, redirects, html
        ou None en cas d'erreur critique.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.error("Playwright non installé.")
        return {'success': False, 'error': 'Playwright non installé'}

    if not proxy:
        return {'success': False, 'error': 'Proxy obligatoire'}

    playwright_proxy = _parse_proxy(proxy)
    if not playwright_proxy:
        return {'success': False, 'error': f'Proxy invalide: {proxy}'}

    redirects = []

    browser = None
    is_camoufox = False
    try:
        async with _BROWSER_SEMAPHORE:
            async with async_playwright() as p:
                browser, is_camoufox = await _launch_browser(p, playwright_proxy)
                context = None
                page = None
                try:
                    context_options = {
                        'locale': 'fr-FR',
                        'ignore_https_errors': True,  # Gère ERR_CERT_DATE_INVALID, ERR_SSL_PROTOCOL_ERROR
                        'extra_http_headers': {
                            'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
                        },
                    }
                    if not is_camoufox:
                        context_options['user_agent'] = random.choice(_USER_AGENTS)

                    context = await browser.new_context(**context_options)

                    await _inject_cookie_consent(context, url)

                    page = await context.new_page()
                    await _setup_resource_blocking(page)

                    # Capturer les redirections via événement response
                    def on_response(response):
                        status = response.status
                        if 300 <= status < 400:
                            redirects.append({
                                'url': response.url,
                                'status_code': status
                            })

                    page.on('response', on_response)

                    # Navigation deux phases (cohérent avec scrape_html)
                    nav_timeout = min(timeout, 30) * 1000  # Max 30s pour domcontentloaded
                    try:
                        response = await page.goto(url, wait_until='domcontentloaded', timeout=nav_timeout)
                    except Exception as nav_e:
                        err_str = str(nav_e)
                        if "ERR_CONNECTION_REFUSED" in err_str or "ERR_NAME_NOT_RESOLVED" in err_str:
                            # finally block will close context + browser
                            return {'success': False, 'error': f'Site inaccessible: {err_str}'}

                        logger.warning(f"Timeout/Erreur navigation pour {url}: {nav_e}")
                        response = None

                    # Phase 2 : bonus networkidle (5s)
                    try:
                        await page.wait_for_load_state('networkidle', timeout=5000)
                    except Exception:
                        pass

                    final_url = page.url
                    status_code = response.status if response else 0
                    content_type = ''
                    if response:
                        content_type = response.headers.get('content-type', '')

                    # Do NOT close here — finally block handles it.
                    return {
                        'success': True,
                        'final_url': final_url,
                        'status_code': status_code,
                        'content_type': content_type,
                        'redirects': redirects,
                    }
                finally:
                    # Drain in-flight route callbacks before tearing down the page.
                    # Suppresses TargetClosedError flood from _route_handler firing
                    # on closed pages under concurrent load.
                    if page is not None:
                        try:
                            await page.unroute_all(behavior='ignoreErrors')
                        except Exception as unroute_err:
                            logger.debug(f"unroute_all failed for {url}: {unroute_err}")
                    if context is not None:
                        try:
                            await context.close()
                        except Exception as ctx_err:
                            logger.debug(f"context.close failed for {url}: {ctx_err}")
                    try:
                        await browser.close()
                    except Exception as br_err:
                        logger.debug(f"browser.close failed for {url}: {br_err}")

    except Exception as e:
        logger.error(f"Erreur suivi redirections Playwright pour {url}: {e}")
        # Inner finally block (above) has already closed context + browser.
        return {'success': False, 'error': str(e)}
