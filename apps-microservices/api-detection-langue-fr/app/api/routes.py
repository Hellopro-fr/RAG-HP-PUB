import asyncio
import logging
import os
import time
from typing import Optional
from urllib.parse import urlparse, urlunparse
from fastapi import APIRouter, HTTPException

from app.models.schemas import (
    DetectionRequest,
    DetectionResponse,
    BatchDetectionRequest,
    BatchDetectionResponse,
    BatchItem,
    UrlCheckResponse,
    DetectionMode,
    DebugDetectionResponse
)
from app.core.domain_fr import DomainFR, domain_cache
from app.core.config import settings
from app.core.inflight_dedup import InflightDedup
from app.core.metrics import DEDUP_HITS, VALIDATION_VERDICTS, HOMEPAGE_FALLBACK_TRIGGERED
from app.services.redirect_tracker import fetch_html
from app.services.language_detector import detect_challenge_page
from app.services.page_validator import validate as validate_page, ValidationVerdict
from app.services.scraper import ScrapeResult

logger = logging.getLogger(__name__)

router = APIRouter()


_inflight_dedup = InflightDedup()
_INFLIGHT_DEDUP_ENABLED = os.getenv("INFLIGHT_DEDUP_ENABLED", "true").lower() == "true"


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


async def _detect_single_url(
    url: str,
    html_content: Optional[str] = None,
    proxy_url: Optional[str] = None,
    mode: DetectionMode = DetectionMode.COMPLETE,
    use_nlp_detection: bool = True,
    forced_method: Optional[str] = None,
    force_refresh: bool = False,
    homepage_fallback: bool = True,
) -> DetectionResponse:
    """Pipeline de détection FR pour une URL unique."""
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

        # [2] Fetch HTML (with inflight dedup unless force_refresh)
        if _INFLIGHT_DEDUP_ENABLED and not force_refresh:
            dedup_key = _normalize_url_for_dedup(url)
            prev_hits = _inflight_dedup.hits
            fetch_result = await _inflight_dedup.coalesce(
                dedup_key, lambda: fetch_html(url, proxy_url)
            )
            if _inflight_dedup.hits > prev_hits:
                DEDUP_HITS.inc(_inflight_dedup.hits - prev_hits)
        else:
            fetch_result = await fetch_html(url, proxy_url)

        if not fetch_result:
            return DetectionResponse(
                ok=False, url=url, method='fetch_failed',
                error='Impossible de récupérer le contenu HTML'
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
                            hp_key, lambda: fetch_html(homepage, proxy_url)
                        )
                    else:
                        hp_fetch = await fetch_html(homepage, proxy_url)

                    if not hp_fetch:
                        HOMEPAGE_FALLBACK_TRIGGERED.labels(outcome="network_failure").inc()
                        rejection = DetectionResponse(
                            ok=False, url=url, method=verdict.value,
                            error=f"Page invalide ({verdict.value}) — repli homepage a échoué (réseau)",
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
                            ok=False, url=url, method=verdict.value,
                            error=f"Page invalide ({verdict.value}) et page d'accueil également invalide ({hp_verdict.value})",
                        )
                        await domain_cache.set(
                            url, url, rejection.model_dump(),
                            ttl_override=_ttl_from_verdict(verdict.value),
                        )
                        return rejection

                    # Homepage valid → run challenge_page detection + DomainFR on homepage HTML
                    challenge = detect_challenge_page(hp_fetch.html)
                    if challenge:
                        rejection = DetectionResponse(
                            ok=False, url=homepage, method='challenge_page',
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
                    )
                    hp_result = await detector.check_page_if_french(hp_fetch.html, mode)
                    hp_result.analyzed_url = homepage
                    HOMEPAGE_FALLBACK_TRIGGERED.labels(outcome="success").inc()
                    logger.info(f"[FALLBACK] OK {url} via {homepage}")
                    await domain_cache.set(url, homepage, hp_result.model_dump())
                    return hp_result

                # No fallback (disabled, or url == homepage) → cache rejection + return
                rejection = DetectionResponse(
                    ok=False, url=url, method=verdict.value,
                    error=f"Page invalide ({verdict.value})",
                )
                await domain_cache.set(
                    url, url, rejection.model_dump(),
                    ttl_override=_ttl_from_verdict(verdict.value),
                )
                return rejection

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
    )
    result = await detector.check_page_if_french(html_content, mode)

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
        )
    except Exception as e:
        return DetectionResponse(
            ok=False, url=request.url, method='error', error=str(e)
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
    items_to_process = request.items

    total_items = len(items_to_process)
    start_time = time.time()

    logger.info(f"[BATCH] Debut traitement: {total_items} URLs, concurrence={request.max_concurrency}, mode={request.mode}")

    # Sémaphore pour limiter la concurrence
    semaphore = asyncio.Semaphore(request.max_concurrency)
    processed_count = 0
    count_lock = asyncio.Lock()

    async def _increment_count() -> int:
        """Incrémente processed_count de façon thread-safe et retourne la valeur."""
        nonlocal processed_count
        async with count_lock:
            processed_count += 1
            return processed_count

    async def _process_item_core(item: BatchItem) -> DetectionResponse:
        """Traitement d'un item avec logging batch (délègue la détection à _detect_single_url)."""
        url = item.url
        item_start = time.time()

        try:
            detection_mode = request.mode
            if detection_mode == DetectionMode.FIRST_MATCH:
                detection_mode = DetectionMode.COMPLETE
                logger.debug(f"[BATCH] Mode first_match → complete pour détection individuelle de {url}")

            result = await _detect_single_url(
                url=url,
                html_content=item.html_content,
                proxy_url=request.proxy_url,
                mode=detection_mode,
                use_nlp_detection=request.use_nlp_detection,
                force_refresh=request.force_refresh,
                homepage_fallback=request.homepage_fallback,
            )

            count = await _increment_count()
            duration_ms = round((time.time() - item_start) * 1000)
            status = "OK" if result.ok else "NOK"
            logger.info(f"[BATCH] [{count}/{total_items}] {status} {url} method={result.method} ({duration_ms}ms)")

            return result

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
            max_stagger = request.max_concurrency * 0.5
            await asyncio.sleep(min(index * 0.5, max_stagger))
        async with semaphore:
            try:
                return await asyncio.wait_for(_process_item_core(item), timeout=300)
            except asyncio.TimeoutError:
                count = await _increment_count()
                logger.error(f"[BATCH] [{count}/{total_items}] TIMEOUT {item.url} après 300s")
                return DetectionResponse(
                    ok=False, url=item.url, method='error',
                    error='Timeout global item (300s)'
                )

    # =========================================================================
    # Mode first_match : traitement groupé (séquentiel intra-groupe, concurrent inter-groupes)
    # =========================================================================
    if request.mode == DetectionMode.FIRST_MATCH:
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
                async with semaphore:
                    result = await _process_item_core(item)
                last_result = result
                if result.ok:
                    return (_with_group(result, group_key), [])
                if result.method in ('fetch_failed', 'challenge_page'):
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
                        retry_result = await _process_item_core(item)
                    if retry_result.ok:
                        group_results[i] = _with_group(retry_result, group_key)
                        logger.info(f"[BATCH][first_match] Pass 2 OK groupe '{group_key}' via {item.url}")
                        break
                    if retry_result.method not in ('fetch_failed', 'challenge_page'):
                        group_results[i] = _with_group(retry_result, group_key)
                        break
                except Exception as e:
                    logger.warning(f"[BATCH][first_match] Pass 2 ERROR groupe '{group_key}' {item.url}: {e}")

        results = group_results
        success_count = sum(1 for r in results if r.ok)
        error_count = sum(1 for r in results if r.method in ('error', 'fetch_failed', 'challenge_page'))
        failed_count = len(results) - success_count - error_count
        processing_time_ms = (time.time() - start_time) * 1000

        logger.info(
            f"[BATCH][first_match] Termine: {success_count} OK, {failed_count} non-FR, "
            f"{error_count} erreurs ({round(processing_time_ms)}ms total)"
        )

        return BatchDetectionResponse(
            total=len(results),
            success_count=success_count,
            failed_count=failed_count,
            error_count=error_count,
            results=results,
            processing_time_ms=round(processing_time_ms, 2)
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

    # Pass 2 : retry séquentiel des fetch_failed et challenge_page
    failed_indices = [
        i for i, r in enumerate(results)
        if r.method in ('fetch_failed', 'challenge_page')
    ]

    if failed_indices:
        logger.info(f"[BATCH] Pass 2: retry sequentiel de {len(failed_indices)} URLs en fetch_failed")

        retry_success = 0
        for retry_num, idx in enumerate(failed_indices, 1):
            item = items_to_process[idx]
            logger.info(f"[BATCH] Retry [{retry_num}/{len(failed_indices)}] {item.url}")

            await asyncio.sleep(2)

            try:
                async with semaphore:
                    retry_result = await _process_item_core(item)
                if retry_result.method not in ('fetch_failed', 'challenge_page'):
                    results[idx] = retry_result
                    retry_success += 1
                    logger.info(
                        f"[BATCH] Retry OK {item.url} "
                        f"(ok={retry_result.ok}, method={retry_result.method})"
                    )
                else:
                    logger.warning(f"[BATCH] Retry ECHEC {item.url} ({retry_result.method})")

            except Exception as e:
                logger.warning(f"[BATCH] Retry ERROR {item.url}: {e}")

        logger.info(f"[BATCH] Pass 2 termine: {retry_success}/{len(failed_indices)} recuperes")

    # Statistiques finales
    success_count = sum(1 for r in results if r.ok)
    error_count = sum(1 for r in results if r.method in ('error', 'fetch_failed', 'challenge_page'))
    failed_count = len(results) - success_count - error_count

    processing_time_ms = (time.time() - start_time) * 1000

    logger.info(
        f"[BATCH] Termine: {success_count} OK, {failed_count} non-FR, "
        f"{error_count} erreurs ({round(processing_time_ms)}ms total)"
    )

    return BatchDetectionResponse(
        total=len(results),
        success_count=success_count,
        failed_count=failed_count,
        error_count=error_count,
        results=list(results),
        processing_time_ms=round(processing_time_ms, 2)
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
            fetch_result = await fetch_html(request.url, request.proxy_url)
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
                        error='Impossible de recuperer le contenu HTML'
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
            challenge_detected=challenge
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
                debug_response.result.ok = False
                debug_response.result.method = verdict.value
                debug_response.result.error = f"Page invalide ({verdict.value})"

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
