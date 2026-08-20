import asyncio
import logging
import os
import random
import time
import uuid
from dataclasses import dataclass, field
from functools import partial
from typing import Optional
from urllib.parse import urlparse

from app.core.config import settings
from app.core.metrics import BROWSER_LAUNCH_DURATION, BROWSERS_UNCLOSED, TEARDOWN_ABANDONED

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


class _BoundedBrowserSemaphore:
    """Sémaphore de navigateurs dont l'ATTENTE est bornée.

    Pourquoi : ce permis est pris à l'INTÉRIEUR du `wait_for` de l'item
    (`routes.py:828`), alors que le sémaphore de lot est pris à l'extérieur
    (`:826`). Avec `ADMISSION_MAX_SLOTS` (8) au-dessus de
    `BROWSER_SEMAPHORE_SIZE` (4), les items en excès attendent donc ICI, sur
    leur propre budget — un item pouvait épuiser ses 300 s sans lancer un seul
    navigateur, et ne rapporter qu'un `error` sans étape.

    L'attente n'est PAS annulée à l'échéance, pour la raison qui vaut déjà pour
    `_close_or_abandon` : un permis accordé dans le même tick qu'une annulation
    serait perdu sur une version de Python dont `Semaphore.acquire` ne le rend
    pas. CPython 3.12 le rend (`self._value += 1` dans sa branche
    `CancelledError`) — l'image est `python:3.10-slim` et ce code ne doit pas
    dépendre de laquelle. On laisse donc l'acquisition courir, et un
    done-callback rend au pool le permis accordé trop tard.
    """

    def __init__(self, size: int) -> None:
        self._sem = asyncio.Semaphore(size)

    async def __aenter__(self) -> None:
        t = asyncio.ensure_future(self._sem.acquire())
        done, _pending = await asyncio.wait(
            {t}, timeout=settings.BROWSER_POOL_WAIT_S
        )
        if not done:
            t.add_done_callback(self._release_if_granted)
            raise TimeoutError(
                f"Timeout pool navigateurs — aucun créneau libre après "
                f"{settings.BROWSER_POOL_WAIT_S}s"
            )
        t.result()  # ne pas masquer un échec réel de l'acquisition
        return None

    async def __aexit__(self, *_exc) -> None:
        self._sem.release()

    def _release_if_granted(self, fut: asyncio.Future) -> None:
        """Un permis accordé après qu'on a cessé d'attendre retourne au pool."""
        if not fut.cancelled() and fut.exception() is None:
            self._sem.release()


_BROWSER_SEMAPHORE = _BoundedBrowserSemaphore(_BROWSER_SEMAPHORE_SIZE)


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

# Longueur max d'une cause publiée. Le message Playwright est multi-lignes et embarque
# le call-log complet : sans troncature on l'injecterait dans chaque réponse HTTP et
# dans le cache Redis.
FAILURE_CAUSE_MAX_LEN = 200


def _record_failure(sink: Optional[dict], stage: str, cause: str) -> None:
    """Publie la cause d'un échec dans le dict fourni par l'appelant.

    `stage` vient du SITE D'APPEL, jamais d'une analyse de `cause` : c'est ce qui
    garantit qu'aucun libellé d'erreur n'est présupposé (aucun code Gecko/Chromium
    n'est attesté en production — cf. spec §2.3).

    Premier écrivain gagne : dans un même appel, une erreur de navigation est la
    racine du « contenu trop court » qui suit, donc elle ne doit pas être écrasée.

    NE JAMAIS passer une valeur de proxy dans `cause` : elle contient un mot de
    passe et cette chaîne finit dans une réponse HTTP puis dans un mail opérateur.
    """
    if sink is None or 'cause' in sink:
        return
    lines = (cause or '').splitlines()
    sink['cause'] = (lines[0] if lines else '')[:FAILURE_CAUSE_MAX_LEN]
    sink['stage'] = stage


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
                timeout=settings.BROWSER_LAUNCH_TIMEOUT_S,
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
    browser = await asyncio.wait_for(
        playwright_instance.chromium.launch(
            headless=True,
            proxy=playwright_proxy,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-blink-features=AutomationControlled',
            ],
        ),
        timeout=settings.BROWSER_LAUNCH_TIMEOUT_S,
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


def _teardown_op(what: str) -> str:
    """Operation family of a teardown `what` string, for use as a metric label.

    `what` is built at the call site as "<op> <url>"; the URL must never reach a
    label (unbounded cardinality), so only the leading op survives:
    unroute_all / context.close / browser.close / playwright.stop.
    """
    return what.split(" ", 1)[0] or "unknown"


def _drain_orphan_exception(fut: asyncio.Future, what: str = "") -> None:
    """Read an abandoned task's exception once it completes, whichever path got there.

    Used by BOTH non-cancelling bounds: `_close_or_abandon` (teardown) and
    `_await_or_raise` (setup calls with no native timeout, added 2026-08-19).
    The `BROWSERS_UNCLOSED` clause below is gated on `_teardown_op(what) ==
    "browser.close"`, so the setup call sites — `playwright.start`,
    `new_context`, `cookie_consent`, `new_page`, `resource_blocking`,
    `page.content` — never touch that gauge.

    Without this, asyncio logs "Task exception was never retrieved" when the
    task is garbage-collected — the log flood observed in prod on 2026-08-03.
    A cancelled task must be skipped: `.exception()` re-raises CancelledError.
    Attached as a done-callback so it also covers the caller-cancelled path
    (see `_close_or_abandon`), not just the abandoned-after-timeout one.

    Also the ONLY place `BROWSERS_UNCLOSED` comes back down: a `browser.close`
    that settles WITHOUT RAISING — now or long after we stopped waiting for it —
    is the single observable we have that the browser is done. An abandoned close
    never settles, so the gauge stays up, which is the whole point.

    A close that settles by RAISING does not come down, and that is deliberate.
    `browser.close()` only returns after the driver confirms the browser is dead
    and its profile removed; a `TargetClosedError` means the pipe died first, so
    nothing was confirmed. This is the same reasoning `_teardown_targets` uses to
    keep a browser counted when it SKIPS the close on `is_connected()` false — a
    dead driver pipe is not proof the detached Firefox exited. Both paths say the
    same thing, so both must be treated the same way. Decrementing here would
    make the gauge under-report, i.e. err toward hiding the very overlap it
    exists to reveal.
    """
    if fut.cancelled():
        return
    exc = fut.exception()
    if _teardown_op(what) == "browser.close" and exc is None:
        BROWSERS_UNCLOSED.dec()
    if exc is not None:
        logger.debug(f"tâche abandonnée en échec ({what}): {exc!r}")


async def _close_or_abandon(coro, timeout: float, what: str = "") -> None:
    """Await a browser teardown coroutine, but ABANDON it if it exceeds `timeout`.

    A close() on a dead browser pipe ignores asyncio cancellation, so wait_for
    (cancel-then-await) would itself hang. asyncio.wait() returns on timeout
    WITHOUT cancelling; we simply stop waiting and leave the task detached. This
    lets the caller escape `finally` and release its semaphore slot.

    What abandoning costs (corrected 2026-08-17 — an earlier version of this
    docstring claimed "its OS process is already gone, so it leaks nothing
    meaningful", which was a belief, not a fact): abandoning a `browser.close`
    means the browser's death was never confirmed, and neither was the removal
    of its profile directory. This service tracks no PID and never kills
    anything, and `p.stop()` only closes the driver pipe then waits for the
    driver to exit on its own — the driver gives itself 30s before a hard exit,
    ignores SIGINT, and launches Firefox DETACHED, so even killing the driver
    would not kill the browser. An abandoned teardown can therefore leave a live
    browser behind. How many, and how often, is NOT known — hence the
    `TEARDOWN_ABANDONED` counter here and the `BROWSERS_UNCLOSED` gauge.

    Do NOT "fix" this by raising the timeout. The cost is FOUR sequential awaits
    on one scrape path — `unroute_all`, `context.close`, `browser.close`, then
    `playwright.stop` — so raising 10s to 30s turns a 40s worst case into 120s,
    exactly the stall abandoning exists to avoid. (Corrected 2026-08-17: an
    earlier wording said "all five abandon sites, a pool of 4". Both numbers were
    beside the point — five is the file-level count of call sites, of which the
    two `p.stop()` ones are mutually exclusive, and the pool size never enters the
    multiplication at all. The conclusion held; the arithmetic did not, and it had
    been copied into four notes.) Deciding otherwise needs the per-browser
    resident cost and the real abandon frequency, neither of which is measured.

    The drain callback is attached BEFORE the await, so all three ways this
    can end are covered: fast failure (done before timeout, exception read via
    the callback), abandoned (task keeps running after we stop waiting, callback
    fires whenever it eventually settles), and caller-cancelled (a CancelledError
    delivered to us while suspended in asyncio.wait propagates out immediately,
    but the callback is already attached to `t` and still fires later)."""
    t = asyncio.ensure_future(coro)
    t.add_done_callback(partial(_drain_orphan_exception, what=what))
    done, _pending = await asyncio.wait({t}, timeout=timeout)
    if not done:
        TEARDOWN_ABANDONED.labels(op=_teardown_op(what)).inc()
        logger.warning(f"scraper teardown abandoned after {timeout}s: {what}")


async def _await_or_raise(coro, timeout: float, what: str):
    """Borne un `await` qui n'a AUCUN timeout natif, et rend son résultat.

    Frère de `_close_or_abandon`, même forme NON ANNULANTE et pour la même
    raison : `asyncio.wait` laisse la tâche en dépassement continuer au lieu de
    l'annuler. Annuler un appel Playwright en pleine conversation protocolaire
    est précisément ce qui a orphelinné le callback de `page.goto` et produit le
    flood « Future exception was never retrieved » — une borne ne doit pas
    rouvrir ça.

    Différence avec `_close_or_abandon` : ici il y a un résultat à livrer, donc
    on LÈVE quand le budget est épuisé.

    Le message contient délibérément « Timeout » :
    `redirect_tracker._VARIANT_POINTLESS_ERRORS` teste ce jeton pour décider si
    les variantes d'URL valent la peine. Un navigateur qui ne répond pas n'est
    pas réparé en basculant http/https ou www — sans le jeton, chacun de ces
    échecs réarmerait trois navigations supplémentaires.

    Pourquoi ces appels en ont besoin : aucune de `Browser.new_context`,
    `BrowserContext.new_page`, `BrowserContext.add_cookies`, `Page.route` ni
    `Page.content` n'accepte de `timeout` (signatures du playwright installé), et
    `set_default_timeout` ne régit que « all methods accepting a timeout
    option » — il n'en bornait donc aucune.
    """
    t = asyncio.ensure_future(coro)
    t.add_done_callback(partial(_drain_orphan_exception, what=what))
    done, _pending = await asyncio.wait({t}, timeout=timeout)
    if not done:
        logger.warning(f"scraper étape abandonnée après {timeout}s: {what}")
        raise TimeoutError(f"Timeout {what} — pas de réponse après {timeout}s")
    return t.result()


async def _teardown_targets(page, context, browser, url: str) -> None:
    """Tear down page/context/browser, skipping targets that are already dead.

    On a failed scrape the targets are usually gone, so every op would raise
    TargetClosedError — each burning up to TEARDOWN_TIMEOUT_S, and `unroute_all`
    on a dead page additionally makes Playwright schedule its internal
    _update_interceptor_patterns task (the large repeated traceback in the
    2026-08-03 logs). `is_closed()` / `is_connected()` are synchronous in the
    Python API, so the guards cannot hang.

    Runs inside a `finally`: never let anything propagate, or the original
    scrape error would be masked.

    Note for `BROWSERS_UNCLOSED`: when `browser.is_connected()` is already false
    the close is skipped, so nothing ever settles and the gauge stays up for that
    browser — deliberately. A dead driver pipe is no evidence that the detached
    Firefox process exited.
    """
    try:
        # Drain in-flight route callbacks before tearing down the page.
        # Suppresses TargetClosedError flood from _route_handler firing
        # on closed pages under concurrent load.
        # Also consult the browser: if the driver pipe dies, page.is_closed()
        # stays False (only the page's own close event flips it), so
        # unroute_all would still run and race a concurrent route callback.
        if page is not None and browser.is_connected() and not page.is_closed():
            await _close_or_abandon(
                page.unroute_all(behavior='ignoreErrors'),
                settings.TEARDOWN_TIMEOUT_S,
                f"unroute_all {url}",
            )
        # BrowserContext exposes no is_closed() in the Python API; if the
        # browser is gone the context is gone with it.
        if context is not None and browser.is_connected():
            await _close_or_abandon(
                context.close(), settings.TEARDOWN_TIMEOUT_S, f"context.close {url}"
            )
        if browser.is_connected():
            await _close_or_abandon(
                browser.close(), settings.TEARDOWN_TIMEOUT_S, f"browser.close {url}"
            )
    except Exception as teardown_err:
        logger.debug(f"teardown error for {url}: {teardown_err!r}")


async def scrape_html(
    url: str,
    timeout: int = 90,
    proxy: Optional[str] = None,
    error_sink: Optional[dict] = None,
) -> Optional[ScrapeResult]:
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
        error_sink: Dict optionnel où publier la cause d'un échec (clés 'cause'/'stage').
            None (défaut) = comportement inchangé, rien n'est écrit.

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
        _record_failure(error_sink, 'runtime', 'Playwright non installé')
        return None

    if not proxy:
        logger.error(f"Proxy obligatoire pour scrape_html: {url}")
        _record_failure(error_sink, 'proxy', 'Proxy obligatoire non fourni')
        return None

    playwright_proxy = _parse_proxy(proxy)
    if not playwright_proxy:
        logger.error(f"Proxy invalide pour {url}: {proxy}")
        # Volontairement SANS la valeur du proxy : elle contient le mot de passe.
        _record_failure(error_sink, 'proxy', 'Proxy invalide (format non reconnu)')
        return None

    async with _BROWSER_SEMAPHORE:
        # Résiduel assumé, même arbitrage que `_close_or_abandon` : un driver
        # qui finit par démarrer APRÈS l'abandon n'est pas récupéré (`p.stop()`
        # ne sera jamais appelé). Annuler serait pire — c'est le mode d'échec
        # qui a produit le flood de callbacks orphelins.
        p = await _await_or_raise(
            async_playwright().start(),
            settings.BROWSER_OP_TIMEOUT_S,
            f"playwright.start {url}",
        )
        try:
            browser, is_camoufox = await _launch_browser(p, playwright_proxy)
            # Counted here, decremented only when its close() settles
            # (`_drain_orphan_exception`) — an abandoned teardown keeps it up.
            BROWSERS_UNCLOSED.inc()
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

                # Ces quatre appels n'acceptent aucun timeout natif et
                # `set_default_timeout` ne les régit pas (cf. config.py) : sans
                # `_await_or_raise` ils étaient les seuls awaits du chemin que
                # rien ne bornait, et un blocage y consommait les 300 s de
                # l'item sans laisser d'étape. Les affectations restent
                # incrémentales : `finally` a besoin de `context`/`page` pour
                # démonter ce qui existe déjà.
                context = await _await_or_raise(
                    browser.new_context(**context_options),
                    settings.BROWSER_OP_TIMEOUT_S,
                    f"new_context {url}",
                )
                context.set_default_timeout(settings.BROWSER_OP_TIMEOUT_S * 1000)

                # Injection cookie de consentement (comme crawler-service)
                await _await_or_raise(
                    _inject_cookie_consent(context, url),
                    settings.BROWSER_OP_TIMEOUT_S,
                    f"cookie_consent {url}",
                )

                page = await _await_or_raise(
                    context.new_page(),
                    settings.BROWSER_OP_TIMEOUT_S,
                    f"new_page {url}",
                )

                # Blocage des ressources lourdes (comme crawler-service)
                await _await_or_raise(
                    _setup_resource_blocking(page),
                    settings.BROWSER_OP_TIMEOUT_S,
                    f"resource_blocking {url}",
                )

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
                    _record_failure(error_sink, 'navigation', err_str or type(nav_e).__name__)
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
                        content = await _await_or_raise(
                            page.content(),
                            settings.BROWSER_OP_TIMEOUT_S,
                            f"page.content {url}",
                        )
                        break
                    except TimeoutError:
                        # Un content() qui ne répond pas n'est PAS « contenu vide
                        # ou trop court » : le laisser remonter, sinon le
                        # _record_failure('content', …) plus bas publierait une
                        # cause fausse pour un blocage navigateur.
                        raise
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
                challenge_resolved = False
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

                        while (_time.time() - poll_start) < poll_timeout:
                            await page.wait_for_timeout(poll_interval * 1000)

                            # Bornés : la garde du `while` ne se réévalue qu'ENTRE
                            # deux tours, donc un content() bloqué ici rendait la
                            # boucle — et son plafond de 45 s — inopérante.
                            try:
                                content = await _await_or_raise(
                                    page.content(),
                                    settings.BROWSER_OP_TIMEOUT_S,
                                    f"page.content (poll challenge) {url}",
                                )
                            except Exception as poll_e:
                                # Le contexte peut être détruit pendant une navigation
                                logger.debug(f"Erreur content() pendant polling challenge pour {url}: {poll_e}")
                                await page.wait_for_timeout(1000)
                                try:
                                    content = await _await_or_raise(
                                        page.content(),
                                        settings.BROWSER_OP_TIMEOUT_S,
                                        f"page.content (poll retry) {url}",
                                    )
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
                                    content = await _await_or_raise(
                                        page.content(),
                                        settings.BROWSER_OP_TIMEOUT_S,
                                        f"page.content (post-challenge) {url}",
                                    )
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
                    # `response` vient du goto INITIAL : après résolution d'un
                    # challenge (navigation window.location.replace), son status
                    # 401/403 est périmé — le garder ferait rejeter la vraie
                    # page en HTTP_ERROR par validate_page malgré un contenu
                    # sain. challenge_resolved n'est vrai que si le body est
                    # passé de challenge → non-challenge.
                    status_code = 200 if challenge_resolved else (response.status if response else 0)
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
                    _record_failure(error_sink, 'content', 'Contenu vide ou trop court')
                    return None
            finally:
                await _teardown_targets(page, context, browser, url)
        finally:
            await _close_or_abandon(p.stop(), settings.TEARDOWN_TIMEOUT_S, f"playwright.stop {url}")


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
            # Même résiduel assumé que dans scrape_html : un driver qui démarre
            # après l'abandon n'est pas récupéré.
            p = await _await_or_raise(
                async_playwright().start(),
                settings.BROWSER_OP_TIMEOUT_S,
                f"playwright.start (redirects) {url}",
            )
            try:
                browser, is_camoufox = await _launch_browser(p, playwright_proxy)
                BROWSERS_UNCLOSED.inc()  # see scrape_html's launch site
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

                    # Mêmes bornes que scrape_html : aucun de ces quatre appels
                    # n'a de timeout natif (cf. config.py:BROWSER_OP_TIMEOUT_S).
                    context = await _await_or_raise(
                        browser.new_context(**context_options),
                        settings.BROWSER_OP_TIMEOUT_S,
                        f"new_context (redirects) {url}",
                    )
                    context.set_default_timeout(settings.BROWSER_OP_TIMEOUT_S * 1000)

                    await _await_or_raise(
                        _inject_cookie_consent(context, url),
                        settings.BROWSER_OP_TIMEOUT_S,
                        f"cookie_consent (redirects) {url}",
                    )

                    page = await _await_or_raise(
                        context.new_page(),
                        settings.BROWSER_OP_TIMEOUT_S,
                        f"new_page (redirects) {url}",
                    )
                    await _await_or_raise(
                        _setup_resource_blocking(page),
                        settings.BROWSER_OP_TIMEOUT_S,
                        f"resource_blocking (redirects) {url}",
                    )

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
                    await _teardown_targets(page, context, browser, url)
            finally:
                await _close_or_abandon(p.stop(), settings.TEARDOWN_TIMEOUT_S, f"playwright.stop {url}")

    except Exception as e:
        logger.error(f"Erreur suivi redirections Playwright pour {url}: {e}")
        # Inner finally block (above) has already closed context + browser.
        return {'success': False, 'error': str(e)}
