import asyncio
import logging
import os
import time
from typing import Optional, Callable
from urllib.parse import urlparse, urlunparse
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.models.schemas import (
    DetectionRequest,
    DetectionResponse,
    BatchDetectionRequest,
    BatchDetectionResponse,
    BatchItem,
    BatchOpts,
    BatchCounts,
    UrlCheckResponse,
    DetectionMode,
    DebugDetectionResponse,
    AsyncBatchSubmitRequest,
    AsyncBatchSubmitResponse,
    AsyncBatchStatusResponse,
)
from app.core.async_jobs import _JobsDisabled, _JobsUnavailable, _JobCapacityExceeded, poll_status
from app.core.domain_fr import DomainFR, domain_cache
from app.core.config import settings
from app.core.inflight_dedup import InflightDedup
from app.core.metrics import VALIDATION_VERDICTS, HOMEPAGE_FALLBACK_TRIGGERED, ADMISSION_REJECTED, INFLIGHT_REQUESTS, VARIANT_RESCUE_OUTCOME
from app.services.redirect_tracker import fetch_html, _generate_url_variants
from app.services.language_detector import detect_challenge_page
from app.services.page_validator import (
    validate as validate_page,
    ValidationVerdict,
    find_stub_redirect_target,
    is_transient_http_status,
)
from app.services.scraper import ScrapeResult, scrape_html

logger = logging.getLogger(__name__)

router = APIRouter()


class _AdmissionRejected(Exception):
    """Raised when the route-level admission controller refuses a slot.

    Translated to HTTP 503 + Retry-After on single /detect and to an
    inline DetectionResponse(method='admission_rejected') on batch items.
    """


async def _fetch_with_admission(
    url: str,
    proxy_url: Optional[str],
    endpoint_label: str,
    error_sink: Optional[dict] = None,
):
    """Acquire a prod admission slot, run fetch_html, release.

    Raises _AdmissionRejected when the pool is saturated. Increments
    ADMISSION_REJECTED{endpoint=endpoint_label} on rejection.
    Increments INFLIGHT_REQUESTS while the fetch is in flight.

    Imported lazily from main to avoid a circular import (main imports
    routes via the router include).
    """
    from main import _prod_admission

    admitted = await _prod_admission.acquire()
    if not admitted:
        ADMISSION_REJECTED.labels(endpoint=endpoint_label).inc()
        raise _AdmissionRejected
    INFLIGHT_REQUESTS.inc()
    try:
        return await fetch_html(url, proxy_url, error_sink=error_sink)
    finally:
        INFLIGHT_REQUESTS.dec()
        await _prod_admission.release()


def _format_failure_detail(sink: Optional[dict]) -> Optional[str]:
    """Formate le sink d'échec en chaîne publiable, ou None si rien n'a été capturé."""
    cause = (sink or {}).get('cause')
    if not cause:
        return None
    return f"{(sink or {}).get('stage') or 'unknown'}: {cause}"


# Verdicts qu'une AUTRE FORME d'URL peut réparer. Ils ont en commun d'être nés
# d'un fetch RÉUSSI : la Phase 2 de fetch_html (permutation http/https,
# www/apex) ne s'est donc jamais exécutée, alors que c'est précisément le cas
# où elle répare. Les échecs de fetch ne figurent PAS ici — fetch_html a déjà
# permuté les variantes pour eux.
_VARIANT_RESCUE_METHODS = ('Check_nok_v2', 'fetch_empty_content')


async def _variant_rescue(
    url: str,
    proxy_url: Optional[str],
    mode: DetectionMode,
    use_nlp_detection: bool,
    forced_method: Optional[str],
    elapsed_s: float,
) -> Optional[DetectionResponse]:
    """Re-teste les formes http/https et www/apex de `url`, rend le premier
    verdict français obtenu.

    Rend `None` — donc « garde le verdict d'origine » — dans TOUS les autres
    cas : budget nul ou épuisé par l'item, aucune variante, sonde en échec,
    sonde en timeout, exception QUELCONQUE pendant l'analyse d'une variante,
    page invalide, page de challenge, aucune variante française. Un
    rattrapage ne doit jamais dégrader un verdict : le transformer en `error`
    par un timeout ou une exception serait pire que le faux négatif qu'il
    corrige, puisqu'`error` n'est ni re-tenté en Pass 2 ni porteur d'une cause.

    `elapsed_s` = temps déjà écoulé pour CET item (fetch primaire + validation
    + stub-hop éventuel) : le budget effectif est plafonné par ce qu'il reste
    avant _ITEM_WALL_CLOCK_S, pas seulement par VARIANT_RESCUE_BUDGET_S — sans
    ça, un item déjà proche des 300s du wait_for() appelant se ferait pousser
    par-dessus par le rattrapage lui-même.
    """
    budget = min(
        settings.VARIANT_RESCUE_BUDGET_S,
        _ITEM_WALL_CLOCK_S - elapsed_s - _RESCUE_MARGIN_S,
    )
    if budget <= 0:
        return None

    variants = _generate_url_variants(url)
    if not variants:
        return None

    deadline = time.monotonic() + budget
    for idx, variant in enumerate(variants):
        remaining = deadline - time.monotonic()
        if remaining < _MIN_PROBE_S:
            if idx == 0:
                # Rien à imputer aux sondes : aucune n'a encore tourné. Le
                # déficit vient du temps déjà brûlé par l'item lui-même
                # (fetch primaire + validation + stub-hop, `elapsed_s`) avant
                # même d'entrer dans cette boucle — message distinct pour ne
                # pas laisser croire à une sonde lente.
                logger.info(
                    f"[VARIANT-RESCUE] budget épuisé pour {url} avant la "
                    f"1re sonde (item déjà à {elapsed_s:.1f}s d'écoulé)"
                )
            else:
                logger.info(f"[VARIANT-RESCUE] budget épuisé pour {url}")
            VARIANT_RESCUE_OUTCOME.labels(outcome="budget_exhausted").inc()
            return None

        try:
            # Une SONDE, pas une cible primaire : un seul scrape_html, jamais la
            # cascade de fetch_html (3 tentatives x ~85s ne tient dans aucun
            # budget). Même patron que la sonde de confirmation du Cas 6
            # (domain_fr.py:1460-1463). Le wait_for est borné par le RESTE du
            # budget, pas par une constante : une variante lente ne peut donc
            # pas le dépasser à elle seule. `timeout=int(remaining)` fait
            # aussi suivre la borne de navigation INTERNE de scrape_html
            # (nav_timeout = min(timeout, 30), scraper.py) sur le temps
            # RÉELLEMENT disponible plutôt que sur son défaut de 90s.
            fetch = await asyncio.wait_for(
                scrape_html(
                    variant, timeout=int(remaining),
                    proxy=proxy_url or settings.APIFY_PROXY,
                ),
                timeout=remaining,
            )

            if not fetch or not fetch.html:
                continue

            if settings.INVALID_PAGE_DETECTION_ENABLED and validate_page(
                fetch, requested_url=variant
            ) != ValidationVerdict.VALID:
                # Le primaire rejette http_error/soft_404/redirected_to_home —
                # une variante ne doit pas ouvrir une porte que le chemin
                # normal ferme (ex. 404/500 au corps français, faux-positif).
                logger.info(f"[VARIANT-RESCUE] {variant} : page invalide, ignorée")
                continue

            challenge = detect_challenge_page(fetch.html)
            if challenge:
                logger.info(f"[VARIANT-RESCUE] {variant} : page {challenge}, ignorée")
                continue

            variant_final = fetch.final_url or variant
            # validate_alternatives=False, en dur : la question posée est « CETTE
            # forme d'URL est-elle française ? », pas « expose-t-elle une
            # alternative française ? » — la chasse aux alternatives a déjà eu lieu
            # sur la forme d'origine, avec le réglage de l'appelant. Sans ce faux,
            # la boucle du Cas 6 ouvrirait des navigateurs supplémentaires HORS du
            # budget (jusqu'à 120s par alternative), et l'annuler en pleine
            # navigation ré-ouvrirait le flood de callbacks orphelins que le commentaire
            # de domain_fr.py:1451-1459 documente.
            detector = DomainFR(
                homepage=variant_final,
                forced_method=forced_method,
                use_nlp_detection=use_nlp_detection,
                original_homepage=url,
                validate_alternatives=False,
            )
            candidate = await detector.check_page_if_french(fetch.html, mode)
            if not candidate.ok:
                continue

            # La chasse aux alternatives a déjà eu lieu sur la forme D'ORIGINE,
            # avec le réglage validate_alternatives de l'appelant — c'est
            # exactement l'argument derrière le validate_alternatives=False
            # forcé ci-dessus. Mais ce flag ne gate QUE la validation :
            # detect_alternative_languages tourne quand même (gaté sur
            # `mode == COMPLETE`, pas sur validate_alternatives) et résout ses
            # candidats contre self.homepage, qui pour une sonde est l'hôte de
            # la VARIANTE — les laisser fuiter exposerait des
            # alternative_urls sur un domaine possiblement différent, sans le
            # signaler. BO script_launch_crawl_csv.php branche sur la seule
            # PRÉSENCE de ce champ pour lancer un crawl sur l'URL qu'il
            # contient : les vider ici complète ce que
            # validate_alternatives=False avait déjà pour but.
            candidate.alternative_urls = []
            candidate.analyzed_url = variant_final
            candidate.method = f"{candidate.method}+variant_rescue"
            logger.info(
                f"[VARIANT-RESCUE] OK {url} via {variant_final} ({candidate.method})"
            )
            VARIANT_RESCUE_OUTCOME.labels(outcome="success").inc()
            return candidate
        except Exception as e:
            # Le try couvre TOUTE l'analyse de la variante (fetch + validation +
            # DomainFR/NLP), pas seulement le fetch : check_page_if_french tourne
            # BeautifulSoup et le stack NLP sur du HTML tiers arbitraire, et une
            # exception qui s'en échapperait remonterait jusqu'au handler batch
            # générique, qui transforme le Check_nok_v2 d'origine en method='error'
            # — exactement la dégradation que ce helper promet de ne jamais causer.
            # Y compris asyncio.TimeoutError : une sonde ratée n'est pas un
            # échec de la détection, c'est l'absence d'un rattrapage.
            # `Exception` et non `BaseException` : asyncio.CancelledError dérive
            # de BaseException depuis Python 3.8 et doit continuer à remonter —
            # un item annulé ne doit pas se présenter comme « aucune variante
            # française ».
            logger.info(f"[VARIANT-RESCUE] {variant} : sonde en échec ({e!r})")
            continue

    VARIANT_RESCUE_OUTCOME.labels(outcome="no_variant_french").inc()
    return None


_inflight_dedup = InflightDedup()
_INFLIGHT_DEDUP_ENABLED = os.getenv("INFLIGHT_DEDUP_ENABLED", "true").lower() == "true"

# Batch Pass 2 : méthodes transitoires re-tentées séquentiellement.
# http_error (404 & co.) / soft_404 / redirected_to_home restent définitifs
# (propriétés de la page, ne changent pas entre Pass 1 et Pass 2).
_PASS2_RETRYABLE_METHODS = (
    'fetch_failed', 'challenge_page', 'admission_rejected',
    'http_error_transient', 'fetch_empty_content',
)

# Plafond horloge par item, imposé par les quatre wait_for() du batch ci-dessus
# (Pass 1 process_single/process_group, Pass 2 séquentiel/first_match) qui
# transforment déjà un dépassement en method='error' ("Timeout global item
# (300s)"). Une seule constante remplace les quatre littéraux dupliqués — le
# rattrapage [4bis] doit connaître ce même plafond pour ne pas pousser un item
# par-dessus.
_ITEM_WALL_CLOCK_S = 300

# Marge retirée du temps restant avant de lancer le rattrapage : celui-ci doit
# se terminer confortablement avant le wait_for(_ITEM_WALL_CLOCK_S) de
# l'appelant, jamais pile à la limite.
_RESCUE_MARGIN_S = 15

# Sous ce seuil, une sonde a plus de chances d'être annulée en pleine
# navigation que de répondre — et une navigation annulée est la condition des
# callbacks de protocole orphelins documentée par domain_fr.py:1451-1459.
#
# Dérivation (scraper.py, scrape_html) — délibérément le PIRE cas, puisque
# c'est exactement ce que ce plancher existe pour empêcher :
#   settings.BROWSER_LAUNCH_TIMEOUT_S (45s, lancement Camoufox/Chromium, AVANT
#   toute navigation) + jusqu'à 30s de domcontentloaded (nav_timeout =
#   min(timeout, 30)) + la phase networkidle (bonus ~5s) + marge ≈ 80s.
# L'ancienne valeur (30) était déjà INFÉRIEURE au seul lancement navigateur —
# une sonde entrée avec 30s restants était donc quasi certaine d'être annulée
# en pleine navigation, exactement la condition que ce garde doit empêcher.
_MIN_PROBE_S = 80


def _normalize_url_for_dedup(url: str) -> str:
    """Normalize URL for dedup key: scheme + lowercase host + path + query."""
    try:
        p = urlparse(url)
        scheme = (p.scheme or "https").lower()
        host = (p.hostname or "").lower()
        path = (p.path or "/").rstrip("/") or "/"
        q = f"?{p.query}" if p.query else ""
        return f"{scheme}://{host}{path}{q}"
    except Exception:
        return url


def _homepage_of(url: str) -> str:
    """Build the root URL for a given URL (preserves scheme + host + port)."""
    p = urlparse(url)
    return urlunparse((p.scheme or "https", p.netloc, "/", "", "", ""))


def _is_homepage(url: str) -> bool:
    """True if URL has root path (no segments)."""
    p = urlparse(url)
    return (p.path or "/") in ("", "/")


def _ttl_from_verdict(verdict_value: str) -> int:
    """Map a verdict string to its cache TTL (settings-aware)."""
    if verdict_value == ValidationVerdict.SOFT_404.value:
        return settings.INVALID_PAGE_TTL_SOFT_S
    return settings.INVALID_PAGE_TTL_HARD_S


# =============================================================================
# Helpers partagés
# =============================================================================

def _build_challenge_error_msg(challenge: str) -> str:
    """Construit le message d'erreur pour une page de challenge/block."""
    if challenge == 'Cloudflare_blocked':
        return 'Contenu bloqué par Cloudflare WAF (IP rejetée par le pare-feu du site)'
    if challenge.startswith('HTTP_') and challenge.endswith('_blocked'):
        error_code = challenge.split('_')[1]
        return f'Contenu bloqué par le serveur (HTTP {error_code} — IP rejetée)'
    return f'Contenu bloqué par {challenge} (page de challenge/CAPTCHA détectée)'


def _with_group(result: DetectionResponse, group_key: str) -> DetectionResponse:
    """Clone un DetectionResponse en ajoutant/remplaçant le champ group."""
    return DetectionResponse(**{**result.model_dump(), 'group': group_key})


def _effective_batch_concurrency(items: list[BatchItem], requested: int) -> int:
    """Clamp serveur de la concurrence batch au pool d'admission.

    Une concurrence demandée > ADMISSION_MAX_SLOTS garantit des
    admission_rejected structurels à chaque chunk (ex. BO envoie 10 sur un
    déploiement à 8 slots). Le serveur connaît sa propre capacité — clamp ici
    plutôt que dans chaque caller. Les batchs 100% html_content (crawler) ne
    fetchent jamais → pas d'admission → pas de clamp.
    """
    if all(item.html_content is not None for item in items):
        return requested
    from main import _prod_admission  # lazy — même pattern que _fetch_with_admission
    return min(requested, _prod_admission.max_slots)


async def _detect_single_url(
    url: str,
    html_content: Optional[str] = None,
    proxy_url: Optional[str] = None,
    mode: DetectionMode = DetectionMode.COMPLETE,
    use_nlp_detection: bool = True,
    forced_method: Optional[str] = None,
    force_refresh: bool = False,
    homepage_fallback: bool = True,
    validate_alternatives: bool = True,
) -> DetectionResponse:
    """Pipeline de détection FR pour une URL unique."""
    t0 = time.monotonic()  # budget du rattrapage [4bis] = ce qui reste du plafond batch
    effective_url = url
    html_was_provided = html_content is not None
    fetch_result: Optional[ScrapeResult] = None

    if not html_was_provided:
        # [1] Cache lookup (domain-keyed)
        if not force_refresh:
            cached = await domain_cache.get(url)
            if cached:
                logger.info(f"Cache HIT {url}")
                # Cross-URL HIT awareness: domain key may have been seeded by a
                # different requested URL. Surface the originating URL.
                cached_req_url = cached.get("requested_url") or cached.get("url")
                if cached_req_url and cached_req_url != url and not cached.get("analyzed_url"):
                    cached["analyzed_url"] = cached_req_url
                return DetectionResponse(**cached)

        # [2] Fetch HTML (admission gate inside dedup leader; followers wait
        # on leader's future and do NOT acquire a slot).
        fetch_sink: dict = {}
        if _INFLIGHT_DEDUP_ENABLED and not force_refresh:
            dedup_key = _normalize_url_for_dedup(url)
            fetch_result = await _inflight_dedup.coalesce(
                dedup_key,
                lambda: _fetch_with_admission(url, proxy_url, "/api/v1/detect", error_sink=fetch_sink),
            )
        else:
            fetch_result = await _fetch_with_admission(
                url, proxy_url, "/api/v1/detect", error_sink=fetch_sink
            )

        if not fetch_result:
            # Limite connue : sous INFLIGHT_DEDUP_ENABLED, seul le leader
            # exécute la lambda ci-dessus et remplit fetch_sink — un follower
            # sur la même URL reçoit failure_detail=None (même cause, publiée
            # par le leader). Ne pas tenter de partager le sink entre coroutines.
            return DetectionResponse(
                ok=False, url=url, method='fetch_failed',
                error='Impossible de récupérer le contenu HTML',
                failure_detail=_format_failure_detail(fetch_sink),
            )

        html_content = fetch_result.html
        final_url = fetch_result.final_url
        if final_url and final_url != url:
            logger.info(f"Redirection: {url} → {final_url}")
            effective_url = final_url

        # [3] Validate page (skip if kill-switch off)
        if settings.INVALID_PAGE_DETECTION_ENABLED:
            verdict = validate_page(fetch_result, requested_url=url)
            VALIDATION_VERDICTS.labels(verdict=verdict.value).inc()
            if verdict != ValidationVerdict.VALID:
                logger.info(
                    f"[VALIDATE] {verdict.value} for {url} "
                    f"(status={fetch_result.status_code}, final={final_url})"
                )
                verdict_method = verdict.value
                verdict_ttl = _ttl_from_verdict(verdict.value)
                if verdict == ValidationVerdict.HTTP_ERROR:
                    # Un 4xx/5xx dont le corps est une page de challenge est un
                    # blocage WAF (rejouable via rotation proxy en Pass 2), pas
                    # une propriété de la page. Sans ce test, un 403 Cloudflare
                    # devient un http_error définitif caché 7 jours.
                    # Les verdicts génériques HTTP_xxx_blocked (simple page
                    # d'erreur au corps mince) sont exclus : un vrai 404 mince
                    # doit rester http_error définitif.
                    challenge = detect_challenge_page(fetch_result.html)
                    if challenge and not challenge.startswith('HTTP_'):
                        logger.warning(
                            f"Challenge/block {challenge} "
                            f"(HTTP {fetch_result.status_code}) pour {effective_url}"
                        )
                        return DetectionResponse(
                            ok=False, url=url, method='challenge_page',
                            error=_build_challenge_error_msg(challenge),
                        )
                    if is_transient_http_status(fetch_result.status_code):
                        # 401/403/407/408/425/429/5xx : conditions de fetch,
                        # pas un verdict définitif — retryable Pass 2, TTL 6h
                        # au lieu de 7 jours.
                        verdict_method = 'http_error_transient'
                        verdict_ttl = domain_cache.TTL_TRANSIENT
                # [5] Homepage fallback
                homepage = _homepage_of(url)
                want_fallback = (
                    homepage_fallback
                    and settings.HOMEPAGE_FALLBACK_ENABLED
                    and not _is_homepage(url)
                )
                if want_fallback:
                    logger.info(f"[FALLBACK] {url} → homepage {homepage}")
                    if _INFLIGHT_DEDUP_ENABLED and not force_refresh:
                        hp_key = _normalize_url_for_dedup(homepage)
                        hp_fetch = await _inflight_dedup.coalesce(
                            hp_key,
                            lambda: _fetch_with_admission(
                                homepage, proxy_url, "/api/v1/detect"
                            ),
                        )
                    else:
                        hp_fetch = await _fetch_with_admission(
                            homepage, proxy_url, "/api/v1/detect"
                        )

                    if not hp_fetch:
                        HOMEPAGE_FALLBACK_TRIGGERED.labels(outcome="network_failure").inc()
                        rejection = DetectionResponse(
                            ok=False, url=url, method=verdict_method,
                            error=f"Page invalide ({verdict_method}) — repli homepage a échoué (réseau)",
                        )
                        await domain_cache.set(
                            url, url, rejection.model_dump(),
                            ttl_override=domain_cache.TTL_TRANSIENT,
                        )
                        return rejection

                    hp_verdict = validate_page(hp_fetch, requested_url=homepage)
                    VALIDATION_VERDICTS.labels(verdict=hp_verdict.value).inc()
                    if hp_verdict != ValidationVerdict.VALID:
                        HOMEPAGE_FALLBACK_TRIGGERED.labels(outcome="rejected").inc()
                        logger.warning(
                            f"[FALLBACK] FAILED {url} (verdict={verdict.value}) "
                            f"and homepage {homepage} (verdict={hp_verdict.value})"
                        )
                        rejection = DetectionResponse(
                            ok=False, url=url, method=verdict_method,
                            error=f"Page invalide ({verdict_method}) et page d'accueil également invalide ({hp_verdict.value})",
                        )
                        await domain_cache.set(
                            url, url, rejection.model_dump(),
                            ttl_override=verdict_ttl,
                        )
                        return rejection

                    # Homepage valid → run challenge_page detection + DomainFR on homepage HTML
                    challenge = detect_challenge_page(hp_fetch.html)
                    if challenge:
                        rejection = DetectionResponse(
                            ok=False, url=url, method='challenge_page',
                            error=_build_challenge_error_msg(challenge),
                            analyzed_url=homepage,
                        )
                        await domain_cache.set(
                            url, homepage, rejection.model_dump(),
                        )
                        return rejection

                    detector = DomainFR(
                        homepage=homepage,
                        forced_method=forced_method,
                        use_nlp_detection=use_nlp_detection,
                        original_homepage=url,
                        validate_alternatives=validate_alternatives,
                    )
                    hp_result = await detector.check_page_if_french(hp_fetch.html, mode)
                    hp_result.analyzed_url = homepage
                    HOMEPAGE_FALLBACK_TRIGGERED.labels(outcome="success").inc()
                    logger.info(f"[FALLBACK] OK {url} via {homepage}")
                    await domain_cache.set(url, homepage, hp_result.model_dump())
                    return hp_result

                # No fallback (disabled, or url == homepage) → cache rejection + return
                rejection = DetectionResponse(
                    ok=False, url=url, method=verdict_method,
                    error=f"Page invalide ({verdict_method})",
                )
                await domain_cache.set(
                    url, url, rejection.model_dump(),
                    ttl_override=verdict_ttl,
                )
                return rejection

    # [3bis] Stub-page hop : page minuscule dont le seul rôle est de pointer
    # ailleurs (meta-refresh ou lien unique même hôte, ex. « Page has moved —
    # click here »). Sans ce saut, elle finit en fetch_empty_content alors que
    # le vrai site est à un clic. Un seul saut, jamais récursif ; en cas
    # d'échec du fetch cible, on continue avec le contenu stub.
    stub_target_used: Optional[str] = None
    if not html_was_provided and settings.STUB_PAGE_HOP_ENABLED:
        stub_target = find_stub_redirect_target(html_content, effective_url)
        if stub_target:
            logger.info(f"[STUB-HOP] {effective_url} → {stub_target}")
            try:
                hop_fetch = await _fetch_with_admission(
                    stub_target, proxy_url, "/api/v1/detect"
                )
            except _AdmissionRejected:
                # Saturation ne doit pas jeter le contenu déjà fetché : on
                # continue avec le stub plutôt que d'échouer l'item entier.
                logger.warning(f"[STUB-HOP] admission saturée pour {stub_target} — contenu stub conservé")
                hop_fetch = None
            if hop_fetch and validate_page(
                hop_fetch, requested_url=stub_target
            ) == ValidationVerdict.VALID:
                html_content = hop_fetch.html
                effective_url = hop_fetch.final_url or stub_target
                stub_target_used = effective_url
            else:
                logger.info(
                    f"[STUB-HOP] échec fetch/validation de {stub_target} — "
                    f"contenu stub conservé"
                )

    # [4] VALID path (or kill-switch off): existing flow — challenge + DomainFR
    challenge = detect_challenge_page(html_content)
    if challenge:
        logger.warning(f"Challenge/block {challenge} pour {effective_url}")
        return DetectionResponse(
            ok=False, url=effective_url, method='challenge_page',
            error=_build_challenge_error_msg(challenge),
        )

    detector = DomainFR(
        homepage=effective_url,
        forced_method=forced_method,
        use_nlp_detection=use_nlp_detection,
        original_homepage=url if effective_url != url else None,
        validate_alternatives=validate_alternatives,
    )
    result = await detector.check_page_if_french(html_content, mode)

    if stub_target_used and not result.analyzed_url:
        result.analyzed_url = stub_target_used

    # [4bis] Rattrapage par variante d'URL. `not html_was_provided` est
    # structurel : quand l'appelant fournit le HTML (crawler-service), aucun
    # fetch ne lui est dû et le rattrapage n'a pas de sens.
    if not html_was_provided and result.method in _VARIANT_RESCUE_METHODS:
        rescued = await _variant_rescue(
            url, proxy_url, mode, use_nlp_detection, forced_method,
            time.monotonic() - t0,
        )
        if rescued:
            result = rescued
            # L'URL analysée devient la graine de l'entrée de cache. PAS
            # « comme au repli homepage » (l'ancienne formulation ici était
            # fausse) : le résultat du repli homepage reste TOUJOURS sur le
            # même hôte que le domaine d'origine (sa propre racine), donc ne
            # sème jamais de seconde clé — le vrai miroir est la redirection
            # cross-domaine ORDINAIRE du fetch primaire (`effective_url =
            # final_url` ci-dessus, quand le domaine change en cours de
            # Phase 1). `domain_cache.set(url, effective_url, …)` (plus bas)
            # sème alors DEUX clés Redis dès que le domaine change :
            # `fr_detect:{domaine d'origine}` et `fr_detect:{domaine cible}`
            # (DomainCache.set, domain_fr.py:136-139, sur
            # `result_domain != input_domain`) — la seconde à `ok=True`/30j,
            # avec un payload dont `requested_url` nomme quand même le
            # domaine D'ORIGINE. La CLÉ ne reste donc PAS le domaine
            # d'origine pour un rattrapage cross-domaine : c'est exactement
            # le même comportement que la redirection ordinaire, pas un ajout
            # de ce rattrapage — voir le known-limit correspondant dans le
            # CLAUDE.md du service.
            effective_url = rescued.analyzed_url or effective_url

    if not html_was_provided:
        await domain_cache.set(url, effective_url, result.model_dump())

    return result


# =============================================================================
# Routes
# =============================================================================

@router.post("/detect", response_model=DetectionResponse)
async def detect_french(request: DetectionRequest) -> DetectionResponse:
    """
    Détecte si un site est en français ou dispose d'une version française.

    **Pipeline :** Cache Redis → Fetch HTML (Playwright + proxy) → Détection challenge →
    Analyse URL → Balises HTML → NLP (fastText + langdetect/langid) → Liens alternatifs →
    Matrice de décision (9 cas).

    **Modes :**
    - `simple` : URL + attribut lang HTML uniquement (rapide)
    - `complete` : + NLP + recherche liens alternatifs hreflang, data-lang, options (complet)

    **Cache :** Résultat caché par domaine (30j ok, 7j nok, 6h transitoire).
    Bypass via `force_refresh=true`. Skip automatique si `html_content` fourni.

    **Paramètres optionnels :**
    - `html_content` : HTML déjà disponible → skip fetch + skip cache
    - `proxy_url` : Proxy personnalisé (défaut: APIFY_PROXY)
    - `force_refresh` : Ignorer le cache et forcer une nouvelle détection
    - `forced_method` : Forcer une méthode de détection spécifique
    - `use_nlp_detection` : Active/désactive la détection NLP
    """
    if request.mode == DetectionMode.FIRST_MATCH:
        raise HTTPException(
            status_code=422,
            detail="Le mode 'first_match' n'est disponible que sur /detect-batch"
        )

    try:
        return await _detect_single_url(
            url=request.url,
            html_content=request.html_content,
            proxy_url=request.proxy_url,
            mode=request.mode,
            use_nlp_detection=request.use_nlp_detection,
            forced_method=request.forced_method,
            force_refresh=request.force_refresh,
            homepage_fallback=request.homepage_fallback,
            validate_alternatives=request.validate_alternatives,
        )
    except _AdmissionRejected:
        retry_after = os.getenv("ADMISSION_RETRY_AFTER_SECONDS", "30")
        raise HTTPException(
            status_code=503,
            detail={
                "detail": "Service temporarily saturated",
                "retry_after_seconds": int(retry_after),
            },
            headers={"Retry-After": retry_after},
        )
    except Exception as e:
        return DetectionResponse(
            ok=False, url=request.url, method='error', error=str(e)
        )


async def _run_batch_core(
    items: list[BatchItem],
    mode: DetectionMode,
    opts: BatchOpts,
    progress_cb: Optional[Callable[[int], None]] = None,
) -> tuple[list[DetectionResponse], BatchCounts]:
    """Shared 2-pass batch orchestration. Used by the sync /detect-batch route
    (progress_cb=None) and the async worker (throttled progress_cb). Behavior is
    identical to the former inline /detect-batch body."""
    items_to_process = items

    total_items = len(items_to_process)
    start_time = time.time()

    effective_concurrency = _effective_batch_concurrency(items_to_process, opts.max_concurrency)
    if effective_concurrency != opts.max_concurrency:
        logger.info(
            f"[BATCH] Concurrence clampée {opts.max_concurrency} → {effective_concurrency} "
            f"(ADMISSION_MAX_SLOTS)"
        )

    logger.info(f"[BATCH] Debut traitement: {total_items} URLs, concurrence={effective_concurrency}, mode={mode}")

    # Sémaphore pour limiter la concurrence
    semaphore = asyncio.Semaphore(effective_concurrency)
    processed_count = 0
    count_lock = asyncio.Lock()

    async def _increment_count() -> int:
        """Incrémente processed_count de façon thread-safe et retourne la valeur."""
        nonlocal processed_count
        async with count_lock:
            processed_count += 1
            if progress_cb is not None:
                progress_cb(min(processed_count, total_items))   # done must never exceed total
            return processed_count

    async def _process_item_core(
        item: BatchItem,
        force_refresh_override: Optional[bool] = None,
    ) -> DetectionResponse:
        """Traitement d'un item avec logging batch (délègue la détection à _detect_single_url).

        force_refresh_override : le Pass 2 force le bypass du cache en lecture —
        l'échec transitoire du Pass 1 vient d'y être écrit (TTL 6h) et
        transformerait le retry en no-op cache HIT.
        """
        url = item.url
        item_start = time.time()

        try:
            detection_mode = mode
            if detection_mode == DetectionMode.FIRST_MATCH:
                detection_mode = DetectionMode.COMPLETE
                logger.debug(f"[BATCH] Mode first_match → complete pour détection individuelle de {url}")

            result = await _detect_single_url(
                url=url,
                html_content=item.html_content,
                proxy_url=opts.proxy_url,
                mode=detection_mode,
                use_nlp_detection=opts.use_nlp_detection,
                force_refresh=(
                    opts.force_refresh
                    if force_refresh_override is None
                    else force_refresh_override
                ),
                homepage_fallback=opts.homepage_fallback,
                validate_alternatives=opts.validate_alternatives,
            )

            count = await _increment_count()
            duration_ms = round((time.time() - item_start) * 1000)
            status = "OK" if result.ok else "NOK"
            logger.info(f"[BATCH] [{count}/{total_items}] {status} {url} method={result.method} ({duration_ms}ms)")

            return result

        except _AdmissionRejected:
            count = await _increment_count()
            duration_ms = round((time.time() - item_start) * 1000)
            logger.warning(
                f"[BATCH] [{count}/{total_items}] ADMISSION_REJECTED {url} ({duration_ms}ms)"
            )
            return DetectionResponse(
                ok=False, url=url, method='admission_rejected',
                error='Service temporarily saturated',
            )
        except Exception as e:
            count = await _increment_count()
            duration_ms = round((time.time() - item_start) * 1000)
            logger.error(f"[BATCH] [{count}/{total_items}] ERROR {url}: {e} ({duration_ms}ms)")
            return DetectionResponse(
                ok=False, url=url, method='error', error=str(e)
            )

    async def process_single(index: int, item: BatchItem) -> DetectionResponse:
        # Stagger plafonné à une « vague » de concurrence (évite 49.5s pour item 99)
        if index > 0:
            max_stagger = effective_concurrency * 0.5
            await asyncio.sleep(min(index * 0.5, max_stagger))
        async with semaphore:
            try:
                return await asyncio.wait_for(_process_item_core(item), timeout=_ITEM_WALL_CLOCK_S)
            except asyncio.TimeoutError:
                count = await _increment_count()
                logger.error(f"[BATCH] [{count}/{total_items}] TIMEOUT {item.url} après {_ITEM_WALL_CLOCK_S}s")
                return DetectionResponse(
                    ok=False, url=item.url, method='error',
                    error=f'Timeout global item ({_ITEM_WALL_CLOCK_S}s)'
                )

    # =========================================================================
    # Mode first_match : traitement groupé (séquentiel intra-groupe, concurrent inter-groupes)
    # =========================================================================
    if mode == DetectionMode.FIRST_MATCH:
        # Tous les items reçoivent un groupe (implicite si absent)
        grouped: dict[str, list[BatchItem]] = {}
        group_order: list[str] = []

        for idx, item in enumerate(items_to_process):
            if item.group is not None:
                if item.group not in grouped:
                    grouped[item.group] = []
                    group_order.append(item.group)
                grouped[item.group].append(item)
            else:
                implicit_key = f"_ungrouped_{idx}"
                grouped[implicit_key] = [item]
                group_order.append(implicit_key)

        # W3 : process_group retourne un tuple (résultat, items échoués)
        # au lieu d'écrire dans un dict partagé — élimine le risque de concurrence
        async def process_group(
            group_key: str, group_items: list[BatchItem]
        ) -> tuple[DetectionResponse, list[BatchItem]]:
            """Séquentiel intra-groupe, stop au premier FR. Retourne (résultat, items échoués)."""
            # R1 : guard contre group_items vide
            if not group_items:
                return (
                    DetectionResponse(ok=False, url='', method='error', error='Empty group', group=group_key),
                    []
                )

            failed: list[BatchItem] = []
            last_result: Optional[DetectionResponse] = None

            for item in group_items:
                try:
                    async with semaphore:
                        result = await asyncio.wait_for(_process_item_core(item), timeout=_ITEM_WALL_CLOCK_S)
                except asyncio.TimeoutError:
                    result = DetectionResponse(
                        ok=False, url=item.url, method='error',
                        error=f'Timeout global item ({_ITEM_WALL_CLOCK_S}s)')
                last_result = result
                if result.ok:
                    return (_with_group(result, group_key), [])
                if result.method in _PASS2_RETRYABLE_METHODS:
                    failed.append(item)

            return (_with_group(last_result, group_key), failed)

        # Pass 1 : tous les groupes en parallèle
        raw_results = await asyncio.gather(*[
            process_group(key, grouped[key]) for key in group_order
        ])
        group_results = [r for r, _ in raw_results]
        group_failed = {group_order[i]: f for i, (_, f) in enumerate(raw_results)}

        pass1_duration = round((time.time() - start_time) * 1000)
        logger.info(f"[BATCH][first_match] Pass 1 termine en {pass1_duration}ms")

        # Pass 2 : retry séquentiel pour les groupes sans FR et ayant des fetch_failed
        for i, group_key in enumerate(group_order):
            if group_results[i].ok:
                continue
            retry_items = group_failed.get(group_key, [])
            if not retry_items:
                continue

            logger.info(f"[BATCH][first_match] Pass 2 groupe '{group_key}': retry {len(retry_items)} item(s)")
            for item in retry_items:
                await asyncio.sleep(2)
                try:
                    async with semaphore:
                        retry_result = await asyncio.wait_for(
                            _process_item_core(item, force_refresh_override=True),
                            timeout=_ITEM_WALL_CLOCK_S,
                        )
                    if retry_result.ok:
                        group_results[i] = _with_group(retry_result, group_key)
                        logger.info(f"[BATCH][first_match] Pass 2 OK groupe '{group_key}' via {item.url}")
                        break
                    if retry_result.method not in _PASS2_RETRYABLE_METHODS:
                        group_results[i] = _with_group(retry_result, group_key)
                        break
                except asyncio.TimeoutError:
                    logger.warning(f"[BATCH][first_match] Pass 2 TIMEOUT groupe '{group_key}' {item.url} après {_ITEM_WALL_CLOCK_S}s")
                except Exception as e:
                    logger.warning(f"[BATCH][first_match] Pass 2 ERROR groupe '{group_key}' {item.url}: {e}")

        results = group_results
        success_count = sum(1 for r in results if r.ok)
        error_count = sum(
            1 for r in results
            if r.method in ('error', 'fetch_failed', 'challenge_page', 'admission_rejected')
        )
        failed_count = len(results) - success_count - error_count
        processing_time_ms = (time.time() - start_time) * 1000

        logger.info(
            f"[BATCH][first_match] Termine: {success_count} OK, {failed_count} non-FR, "
            f"{error_count} erreurs ({round(processing_time_ms)}ms total)"
        )

        return results, BatchCounts(
            success_count=success_count, failed_count=failed_count, error_count=error_count
        )

    # =========================================================================
    # Mode complete / simple : traitement parallèle standard
    # =========================================================================

    # Pass 1 : traitement parallèle
    results = list(await asyncio.gather(*[
        process_single(i, item) for i, item in enumerate(items_to_process)
    ]))

    pass1_duration = round((time.time() - start_time) * 1000)
    pass1_ok = sum(1 for r in results if r.ok)
    pass1_fetch_failed = sum(1 for r in results if r.method == 'fetch_failed')
    pass1_challenge = sum(1 for r in results if r.method == 'challenge_page')
    logger.info(
        f"[BATCH] Pass 1 termine: {pass1_ok} OK, {pass1_fetch_failed} fetch_failed, "
        f"{pass1_challenge} challenge_page, "
        f"{total_items - pass1_ok - pass1_fetch_failed - pass1_challenge} autres ({pass1_duration}ms)"
    )

    # Pass 2 : retry séquentiel des méthodes transitoires
    failed_indices = [
        i for i, r in enumerate(results)
        if r.method in _PASS2_RETRYABLE_METHODS
    ]

    if failed_indices:
        logger.info(f"[BATCH] Pass 2: retry sequentiel de {len(failed_indices)} URLs en échec transitoire")

        retry_success = 0
        for retry_num, idx in enumerate(failed_indices, 1):
            item = items_to_process[idx]
            logger.info(f"[BATCH] Retry [{retry_num}/{len(failed_indices)}] {item.url}")

            await asyncio.sleep(2)

            try:
                async with semaphore:
                    # wait_for : sans borne, un retry suspendu bloquerait le
                    # batch entier (le Pass 1 est borné, le Pass 2 doit l'être).
                    retry_result = await asyncio.wait_for(
                        _process_item_core(item, force_refresh_override=True),
                        timeout=_ITEM_WALL_CLOCK_S,
                    )
                if retry_result.method not in _PASS2_RETRYABLE_METHODS:
                    results[idx] = retry_result
                    retry_success += 1
                    logger.info(
                        f"[BATCH] Retry OK {item.url} "
                        f"(ok={retry_result.ok}, method={retry_result.method})"
                    )
                else:
                    logger.warning(f"[BATCH] Retry ECHEC {item.url} ({retry_result.method})")

            except asyncio.TimeoutError:
                logger.warning(f"[BATCH] Retry TIMEOUT {item.url} après {_ITEM_WALL_CLOCK_S}s")
            except Exception as e:
                logger.warning(f"[BATCH] Retry ERROR {item.url}: {e}")

        logger.info(f"[BATCH] Pass 2 termine: {retry_success}/{len(failed_indices)} recuperes")

    # Statistiques finales
    success_count = sum(1 for r in results if r.ok)
    error_count = sum(
        1 for r in results
        if r.method in ('error', 'fetch_failed', 'challenge_page', 'admission_rejected')
    )
    failed_count = len(results) - success_count - error_count

    processing_time_ms = (time.time() - start_time) * 1000

    logger.info(
        f"[BATCH] Termine: {success_count} OK, {failed_count} non-FR, "
        f"{error_count} erreurs ({round(processing_time_ms)}ms total)"
    )

    return results, BatchCounts(
        success_count=success_count, failed_count=failed_count, error_count=error_count
    )


@router.post("/detect-batch", response_model=BatchDetectionResponse)
async def detect_french_batch(request: BatchDetectionRequest) -> BatchDetectionResponse:
    """
    Traitement par lot : détecte plusieurs URLs en parallèle.

    **Traitement 2-pass :**
    1. **Pass 1** — Traitement parallèle avec stagger (0.5s/item, plafonné à une vague de concurrence)
    2. **Pass 2** — Retry séquentiel (2s entre chaque) pour les `fetch_failed` et `challenge_page`

    **Mode `first_match` :** Traitement groupé — séquentiel intra-groupe (stop au premier FR),
    concurrent inter-groupes. Utile pour tester plusieurs URLs d'un même fournisseur.

    **Cache :** Chaque URL est vérifiée/stockée individuellement en cache Redis.
    `force_refresh=true` bypass le cache pour toutes les URLs du lot.

    **Paramètres :**
    - `items` : Liste d'objets {url, html_content?, group?} (max 100)
    - `mode` : simple, complete ou first_match
    - `max_concurrency` : Requêtes parallèles (1-50, défaut: 10)
    - `force_refresh` : Ignorer le cache pour toutes les URLs

    **Retourne** les résultats dans le même ordre que les données fournies.
    """
    start_time = time.time()
    opts = BatchOpts(
        proxy_url=request.proxy_url,
        use_nlp_detection=request.use_nlp_detection,
        force_refresh=request.force_refresh,
        max_concurrency=request.max_concurrency,
        homepage_fallback=request.homepage_fallback,
        validate_alternatives=request.validate_alternatives,
    )
    results, counts = await _run_batch_core(request.items, request.mode, opts)
    processing_time_ms = (time.time() - start_time) * 1000
    return BatchDetectionResponse(
        total=len(results),
        success_count=counts.success_count,
        failed_count=counts.failed_count,
        error_count=counts.error_count,
        results=list(results),
        processing_time_ms=round(processing_time_ms, 2),
    )


@router.get("/check-url", response_model=UrlCheckResponse)
async def check_url_only(url: str, track_redirect: bool = False) -> UrlCheckResponse:
    """
    Vérifie rapidement si une URL indique une version française.

    Analyse uniquement l'URL (TLD, path, query params) sans récupérer le contenu HTML.

    **Critères vérifiés:**
    - TLD `.fr`
    - Sous-domaine `fr.`
    - Segment `/fr/` dans le path
    - Paramètre `lang=fr` dans la query string
    """
    result = await DomainFR.check_url(url, track_redirect=track_redirect)

    return UrlCheckResponse(
        ok=result.get('ok', False),
        method=result.get('method', 'unknown'),
        url=result.get('url'),
        original_url=result.get('original_url')
    )


@router.post("/detect-debug", response_model=DebugDetectionResponse)
async def detect_french_debug(request: DetectionRequest) -> DebugDetectionResponse:
    """
    Version debug de /detect qui retourne le resultat + les informations
    detaillees de chaque etape du pipeline de detection.

    Utile pour diagnostiquer pourquoi une URL est detectee ou non comme francaise.

    Retourne :
    - **result** : Le resultat normal de detection (identique a /detect)
    - **debug.fetch** : Contenu recupere (longueur, apercu)
    - **debug.cleaning** : Texte apres nettoyage (longueur, apercu)
    - **debug.url_check** : Resultat du check URL (TLD, path, query)
    - **debug.html_tags** : Resultat de la detection par balises HTML
    - **debug.nlp** : Resultat NLP complet (langue, confiance, details)
    - **debug.alternatives** : URLs alternatives detectees
    - **debug.decision** : Cas de decision applique
    """
    try:
        html_content = request.html_content
        fetched_by = 'provided'
        effective_url = request.url
        redirected_from = None
        fetch_result: Optional[ScrapeResult] = None

        if not html_content:
            fetched_by = 'api'
            debug_fetch_sink: dict = {}
            fetch_result = await fetch_html(request.url, request.proxy_url, error_sink=debug_fetch_sink)
            if not fetch_result:
                from app.models.schemas import (
                    DebugInfo, DebugFetchInfo, DebugCleaningInfo,
                    DebugUrlCheckInfo, DebugHtmlTagsInfo, DebugNlpInfo,
                    DebugAlternativesInfo
                )
                return DebugDetectionResponse(
                    result=DetectionResponse(
                        ok=False,
                        url=request.url,
                        method='fetch_failed',
                        error='Impossible de recuperer le contenu HTML',
                        failure_detail=_format_failure_detail(debug_fetch_sink),
                    ),
                    debug=DebugInfo(
                        fetch=DebugFetchInfo(fetched_by='api', raw_html_length=0, raw_html_preview=''),
                        cleaning=DebugCleaningInfo(cleaned_text_length=0, cleaned_text_preview=''),
                        url_check=DebugUrlCheckInfo(ok=False, method='fetch_failed', is_strong_url=False),
                        html_tags=DebugHtmlTagsInfo(detected=False, is_french=False),
                        nlp=DebugNlpInfo(available=False),
                        alternatives=DebugAlternativesInfo(candidates_found=0),
                        decision='Fetch failed — no content to analyze'
                    )
                )
            html_content = fetch_result.html
            final_url = fetch_result.final_url
            if final_url and final_url != request.url:
                logger.info(f"[DEBUG] Redirection: {request.url} → {final_url}")
                redirected_from = request.url
                effective_url = final_url

        # Détecter page de challenge (info debug — ne bloque pas en mode debug)
        challenge = detect_challenge_page(html_content)
        if challenge:
            logger.warning(f"[DEBUG] Page de challenge {challenge} détectée pour {effective_url}")

        detector = DomainFR(
            homepage=effective_url,
            forced_method=request.forced_method,
            use_nlp_detection=request.use_nlp_detection,
            original_homepage=request.url if effective_url != request.url else None
        )

        debug_response = await detector.check_page_if_french_debug(
            html_content, request.mode, fetched_by=fetched_by,
            include_full_content=request.include_full_content,
            redirected_from=redirected_from,
            challenge_detected=challenge,
            http_status=fetch_result.status_code if fetch_result else None
        )

        # [VALIDATE] Run page validator in debug mode — no fallback, just override result fields.
        if settings.INVALID_PAGE_DETECTION_ENABLED and fetch_result is not None:
            verdict = validate_page(fetch_result, requested_url=request.url)
            VALIDATION_VERDICTS.labels(verdict=verdict.value).inc()
            if verdict != ValidationVerdict.VALID:
                logger.info(
                    f"[DEBUG][VALIDATE] {verdict.value} for {request.url} "
                    f"(status={fetch_result.status_code}, final={fetch_result.final_url})"
                )
                # Miroir de la reclassification prod de /detect (challenge gagne
                # sur le statut brut, statuts transitoires → http_error_transient).
                # Sans ce miroir, debug affiche 'http_error' là où prod répond
                # 'challenge_page'/'http_error_transient' — divergence fantôme.
                verdict_method = verdict.value
                if verdict == ValidationVerdict.HTTP_ERROR:
                    if challenge and not challenge.startswith('HTTP_'):
                        verdict_method = 'challenge_page'
                    elif is_transient_http_status(fetch_result.status_code):
                        verdict_method = 'http_error_transient'
                debug_response.result.ok = False
                debug_response.result.method = verdict_method
                debug_response.result.error = f"Page invalide ({verdict_method})"

        return debug_response

    except Exception as e:
        from app.models.schemas import (
            DebugInfo, DebugFetchInfo, DebugCleaningInfo,
            DebugUrlCheckInfo, DebugHtmlTagsInfo, DebugNlpInfo,
            DebugAlternativesInfo
        )
        return DebugDetectionResponse(
            result=DetectionResponse(
                ok=False,
                url=request.url,
                method='error',
                error=str(e)
            ),
            debug=DebugInfo(
                fetch=DebugFetchInfo(fetched_by='unknown', raw_html_length=0, raw_html_preview=''),
                cleaning=DebugCleaningInfo(cleaned_text_length=0, cleaned_text_preview=''),
                url_check=DebugUrlCheckInfo(ok=False, method='error', is_strong_url=False),
                html_tags=DebugHtmlTagsInfo(detected=False, is_french=False),
                nlp=DebugNlpInfo(available=False),
                alternatives=DebugAlternativesInfo(candidates_found=0),
                decision=f'Error: {str(e)}'
            )
        )


@router.get("/health")
async def health_check() -> dict:
    """
    Endpoint de santé pour monitoring.

    Retourne le statut de l'API et des informations de version.
    """
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "service": "detection-langue-api"
    }


def _poll_hint() -> int:
    return min(max(settings.HEARTBEAT_INTERVAL_S, 5), settings.ASYNC_POLL_HINT_MAX_S)


@router.post("/detect-batch-async")
async def submit_batch_async(request: AsyncBatchSubmitRequest, http_request: Request):
    """Submit a batch for async processing. Returns 202 + job_id (or 200 if the
    client_job_id maps to an existing job). Poll GET /detect-batch-async/{job_id}."""
    jm = http_request.app.state.job_manager
    try:
        job_id, status_code = await jm.submit(request)
    except _JobsDisabled:
        # permanent: NO Retry-After -> BO short-circuits. Must stay the ONLY
        # header-less 503 — the BO discriminates by header presence.
        raise HTTPException(status_code=503, detail={"detail": "Async jobs disabled", "retryable": False})
    except _JobsUnavailable:
        # transient (Redis restart, not the kill-switch): same Retry-After
        # treatment as capacity below, so the BO retries instead of aborting.
        ra = str(settings.ASYNC_SUBMIT_RETRY_AFTER_S)
        raise HTTPException(
            status_code=503,
            detail={"detail": "Job store unavailable", "retryable": True, "retry_after_seconds": int(ra)},
            headers={"Retry-After": ra},
        )
    except _JobCapacityExceeded:
        ra = str(settings.ASYNC_SUBMIT_RETRY_AFTER_S)
        raise HTTPException(
            status_code=503,
            detail={"detail": "Max active jobs reached", "retryable": True, "retry_after_seconds": int(ra)},
            headers={"Retry-After": ra},
        )
    body = AsyncBatchSubmitResponse(
        job_id=job_id, status="pending", total=len(request.items), poll_after_seconds=_poll_hint()
    )
    return JSONResponse(status_code=status_code, content=body.model_dump())


@router.get("/detect-batch-async/{job_id}", response_model=AsyncBatchStatusResponse)
async def poll_batch_async(job_id: str, http_request: Request) -> AsyncBatchStatusResponse:
    """Poll an async job. 404 if unknown/expired; 503+Retry-After if the job
    store itself is unreadable (Redis blip — see JobManager.store_ping).
    Computes 'stale' on read."""
    jm = http_request.app.state.job_manager
    rec = await jm.get_record(job_id)
    if not rec:
        # JobStore.get() degrades BOTH "no such key" and "Redis read failed"
        # to the same None (app/core/async_jobs.py). Ping to tell them apart:
        # a ping failure means "illisible", not "absent" — 503+Retry-After
        # (already handled correctly by the BO's poll loop) instead of 404
        # (the ONLY poll code that breaks the BO's retry loop and discards
        # the whole chunk). ponytail: the ping may borrow a different pool
        # connection than the failed read, so a single poisoned connection
        # can still read-fails-but-ping-succeeds -> 404 — this narrows the
        # window, it does not close it.
        if not await jm.store_ping():
            ra = str(settings.ASYNC_SUBMIT_RETRY_AFTER_S)
            raise HTTPException(
                status_code=503,
                detail={"detail": "Job store unavailable", "retryable": True, "retry_after_seconds": int(ra)},
                headers={"Retry-After": ra},
            )
        raise HTTPException(status_code=404, detail="Unknown or expired job_id")
    status = poll_status(rec, time.time(), settings.STALE_THRESHOLD_S)
    results = rec.get("results") if status in ("completed", "failed", "stale") else None
    return AsyncBatchStatusResponse(
        job_id=rec["job_id"], status=status, total=rec["total"], done=rec.get("done", 0),
        success_count=rec.get("success_count", 0), failed_count=rec.get("failed_count", 0),
        error_count=rec.get("error_count", 0), results=results,
        processing_time_ms=None, error=rec.get("error"), poll_after_seconds=_poll_hint(),
    )
