import asyncio
import logging
import time
from typing import Optional
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
from app.services.redirect_tracker import fetch_html
from app.services.language_detector import detect_challenge_page

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/detect", response_model=DetectionResponse)
async def detect_french(request: DetectionRequest) -> DetectionResponse:
    """
    Détecte si un site est en français ou dispose d'une version française.
    
    **Modes:**
    - `simple`: Vérifie URL + attribut lang HTML uniquement (comportement TypeScript)
    - `complete`: + recherche de liens alternatifs hreflang, options, etc. (comportement PHP)
    
    **Paramètres optionnels:**
    - `html_content`: Si le HTML est déjà disponible, évite une requête HTTP
    - `proxy_url`: Proxy à utiliser pour les requêtes
    - `forced_method`: Force une méthode de détection spécifique
    - `use_nlp_detection`: Active/désactive la détection NLP par contenu textuel
    """
    if request.mode == DetectionMode.FIRST_MATCH:
        raise HTTPException(
            status_code=422,
            detail="Le mode 'first_match' n'est disponible que sur /detect-batch"
        )

    try:
        # Récupérer le HTML si non fourni
        html_content = request.html_content
        effective_url = request.url

        if not html_content:
            # Vérification cache (seulement quand l'API récupère elle-même le HTML)
            cached = await domain_cache.get(request.url)
            if cached:
                logger.info(f"Cache HIT {request.url}")
                return DetectionResponse(**cached)

            fetch_result = await fetch_html(request.url, request.proxy_url)
            if not fetch_result:
                return DetectionResponse(
                    ok=False,
                    url=request.url,
                    method='fetch_failed',
                    error='Impossible de récupérer le contenu HTML'
                )
            html_content, final_url = fetch_result
            # Mettre à jour l'URL si Playwright a suivi une redirection
            if final_url and final_url != request.url:
                logger.info(f"Redirection détectée: {request.url} → {final_url}")
                effective_url = final_url

        # Vérifier si le contenu est une page de challenge ou block (Cloudflare, etc.)
        challenge = detect_challenge_page(html_content)
        if challenge:
            if challenge == 'Cloudflare_blocked':
                error_msg = 'Contenu bloqué par Cloudflare WAF (IP rejetée par le pare-feu du site)'
            elif challenge.startswith('HTTP_') and challenge.endswith('_blocked'):
                error_code = challenge.split('_')[1]
                error_msg = f'Contenu bloqué par le serveur (HTTP {error_code} — IP rejetée)'
            else:
                error_msg = f'Contenu bloqué par {challenge} (page de challenge/CAPTCHA détectée)'
            logger.warning(f"Page de challenge/block {challenge} détectée pour {effective_url}")
            return DetectionResponse(
                ok=False,
                url=effective_url,
                method='challenge_page',
                error=error_msg
            )

        # Créer le détecteur avec l'URL finale (après redirection éventuelle)
        # original_homepage conserve l'URL d'origine pour accepter les alternatives
        # qui pointent vers le domaine d'avant redirection (ex: trojanuv.com → trojantechnologies.com)
        detector = DomainFR(
            homepage=effective_url,
            forced_method=request.forced_method,
            use_nlp_detection=request.use_nlp_detection,
            original_homepage=request.url if effective_url != request.url else None
        )

        # Lancer la détection
        result = await detector.check_page_if_french(html_content, request.mode)

        # Stocker en cache (seulement si l'API a récupéré le HTML elle-même)
        if not request.html_content:
            await domain_cache.set(request.url, effective_url, result.model_dump())

        return result

    except Exception as e:
        return DetectionResponse(
            ok=False,
            url=request.url,
            method='error',
            error=str(e)
        )


@router.post("/detect-batch", response_model=BatchDetectionResponse)
async def detect_french_batch(request: BatchDetectionRequest) -> BatchDetectionResponse:
    """
    Traitement par lot : détecte plusieurs URLs en parallèle.
    
    **Paramètres:**
    - `urls`: [DEPRECATED] Liste d'URLs simples (max 100)
    - `items`: Liste d'objets contenant 'url' et optionnellement 'html_content' (recommandé)
    - `mode`: simple ou complete (appliqué à tous)
    - `max_concurrency`: Nombre de requêtes parallèles (1-50, défaut: 10)
    
    **Retourne** les résultats dans le même ordre que les données fournies.
    """
    # Unification des entrées (support rétro-compatible)
    items_to_process: list[BatchItem] = []
    
    if request.items:
        items_to_process.extend(request.items)
        
    if request.urls:
        items_to_process.extend([BatchItem(url=u, html_content=None) for u in request.urls])

    if not items_to_process:
        raise HTTPException(status_code=400, detail="La liste d'URLs/items ne peut pas être vide")
    
    if len(items_to_process) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 items par requête")
    
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
        """Traitement d'un item sans stagger delay (logique partagée)."""
        url = item.url
        item_start = time.time()

        try:
            html_content = item.html_content
            effective_url = url

            if not html_content:
                # Vérification cache (seulement quand l'API récupère elle-même le HTML)
                cached = await domain_cache.get(url)
                if cached:
                    logger.info(f"[BATCH] Cache HIT {url}")
                    await _increment_count()
                    return DetectionResponse(**cached)

                fetch_result = await fetch_html(url, request.proxy_url)
                if not fetch_result:
                    count = await _increment_count()
                    duration_ms = round((time.time() - item_start) * 1000)
                    logger.warning(f"[BATCH] [{count}/{total_items}] FETCH_FAILED {url} ({duration_ms}ms)")
                    return DetectionResponse(
                        ok=False,
                        url=url,
                        method='fetch_failed',
                        error='Impossible de récupérer le contenu HTML'
                    )
                html_content, final_url = fetch_result
                if final_url and final_url != url:
                    logger.info(f"[BATCH] Redirection: {url} → {final_url}")
                    effective_url = final_url

            # Vérifier si le contenu est une page de challenge ou block
            challenge = detect_challenge_page(html_content)
            if challenge:
                count = await _increment_count()
                duration_ms = round((time.time() - item_start) * 1000)
                logger.warning(f"[BATCH] [{count}/{total_items}] CHALLENGE_{challenge} {url} ({duration_ms}ms)")
                if challenge == 'Cloudflare_blocked':
                    error_msg = 'Contenu bloqué par Cloudflare WAF (IP rejetée par le pare-feu du site)'
                elif challenge.startswith('HTTP_') and challenge.endswith('_blocked'):
                    error_code = challenge.split('_')[1]
                    error_msg = f'Contenu bloqué par le serveur (HTTP {error_code} — IP rejetée)'
                else:
                    error_msg = f'Contenu bloqué par {challenge} (page de challenge/CAPTCHA détectée)'
                return DetectionResponse(
                    ok=False,
                    url=effective_url,
                    method='challenge_page',
                    error=error_msg
                )

            # Mode de détection : first_match utilise complete en interne par URL
            detection_mode = request.mode if request.mode != DetectionMode.FIRST_MATCH else DetectionMode.COMPLETE

            detector = DomainFR(
                homepage=effective_url,
                use_nlp_detection=request.use_nlp_detection,
                original_homepage=url if effective_url != url else None
            )

            result = await detector.check_page_if_french(html_content, detection_mode)

            # Stocker en cache (seulement si l'API a récupéré le HTML elle-même)
            if not item.html_content:
                await domain_cache.set(url, effective_url, result.model_dump())

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
                ok=False,
                url=url,
                method='error',
                error=str(e)
            )

    async def process_single(index: int, item: BatchItem) -> DetectionResponse:
        # Stagger delay : évite que tous les navigateurs frappent le proxy simultanément
        # Réduit la pression sur le proxy et le risque de déclencher des protections anti-bot
        if index > 0:
            await asyncio.sleep(index * 0.5)
        async with semaphore:
            return await _process_item_core(item)

    # =========================================================================
    # Mode first_match : traitement groupé (séquentiel intra-groupe, concurrent inter-groupes)
    # =========================================================================
    if request.mode == DetectionMode.FIRST_MATCH:
        # Partitionner items en groupes nommés et items sans groupe
        grouped: dict[str, list[BatchItem]] = {}
        ungrouped: list[BatchItem] = []
        group_order: list[str] = []  # ordre de première apparition des groupes

        for item in items_to_process:
            if item.group is not None:
                if item.group not in grouped:
                    grouped[item.group] = []
                    group_order.append(item.group)
                grouped[item.group].append(item)
            else:
                ungrouped.append(item)

        # failed_by_group : items fetch_failed/challenge_page par groupe (pour Pass 2)
        failed_by_group: dict[str, list[BatchItem]] = {}

        async def process_group(group_key: str, group_items: list[BatchItem]) -> DetectionResponse:
            """Traitement séquentiel : stop au premier FR. Concurrent avec autres groupes via semaphore."""
            failed: list[BatchItem] = []
            last_result: Optional[DetectionResponse] = None

            for item in group_items:
                async with semaphore:
                    result = await _process_item_core(item)
                last_result = result
                if result.ok:
                    return DetectionResponse(**{**result.model_dump(), 'group': group_key})
                if result.method in ('fetch_failed', 'challenge_page'):
                    failed.append(item)

            failed_by_group[group_key] = failed
            return DetectionResponse(**{**last_result.model_dump(), 'group': group_key})

        # Pass 1 : groupes en parallèle, items sans groupe en parallèle indépendant
        group_results: list[DetectionResponse] = list(await asyncio.gather(*[
            process_group(key, grouped[key]) for key in group_order
        ]))
        ungrouped_results: list[DetectionResponse] = list(await asyncio.gather(*[
            process_single(i, item) for i, item in enumerate(ungrouped)
        ]))

        pass1_duration = round((time.time() - start_time) * 1000)
        logger.info(f"[BATCH][first_match] Pass 1 termine en {pass1_duration}ms")

        # Pass 2 : retry séquentiel pour les groupes sans FR et ayant des fetch_failed
        for i, group_key in enumerate(group_order):
            if group_results[i].ok:
                continue
            retry_items = failed_by_group.get(group_key, [])
            if not retry_items:
                continue

            logger.info(f"[BATCH][first_match] Pass 2 groupe '{group_key}': retry {len(retry_items)} item(s)")
            for item in retry_items:
                await asyncio.sleep(2)
                try:
                    async with semaphore:
                        retry_result = await _process_item_core(item)
                    if retry_result.ok:
                        group_results[i] = DetectionResponse(**{**retry_result.model_dump(), 'group': group_key})
                        logger.info(f"[BATCH][first_match] Pass 2 OK groupe '{group_key}' via {item.url}")
                        break
                    if retry_result.method not in ('fetch_failed', 'challenge_page'):
                        group_results[i] = DetectionResponse(**{**retry_result.model_dump(), 'group': group_key})
                        break
                except Exception as e:
                    logger.warning(f"[BATCH][first_match] Pass 2 ERROR groupe '{group_key}' {item.url}: {e}")

        results = group_results + ungrouped_results
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
            html_content, final_url = fetch_result
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

        return await detector.check_page_if_french_debug(
            html_content, request.mode, fetched_by=fetched_by,
            include_full_content=request.include_full_content,
            redirected_from=redirected_from,
            challenge_detected=challenge
        )

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
        "version": "1.0.0",
        "service": "detection-langue-api"
    }
