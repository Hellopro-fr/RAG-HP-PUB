import { UrlConsolidator } from './UrlConsolidator.js';
import { StatsManager } from './StatsManager.js';
import { JsonlWriter } from './JsonlWriter.js';
import { PushedSet } from './PushedSet.js';
import { rightTrimSlash, processUrl } from '../functions.js';
import { hasIgnoredExtensionForSeed } from '../seedExtensionFilter.js';

/**
 * Result returned by checkUrl for each processed page.
 */
export interface CheckUrlResult {
    action: 'deleted' | 'redirected' | 'new_url' | 'confirmed' | 'ignored';
    url: string;
    source: string;
    reason?: string;
    destination?: string;
}

/**
 * FORBIDDEN_PARAMS — duplicated from routes.ts to avoid circular imports.
 * Used for eligibility checks. Ignored-extension knowledge instead lives in
 * seedExtensionFilter.ts (single source of truth, imported below).
 */

// IMPORTANT: Keep in sync with FORBIDDEN_PARAMS in routes.ts
const FORBIDDEN_PARAMS = [
    // === SORTING & ORDERING ===
    'sort', 'sort_by', 'order', 'dir',

    // === PAGINATION ===
    'limit', 'resultsPerPage', 'per_page', 'items',
    'offset', 'start',

    // === DISPLAY / VIEW MODE ===
    'view', 'mode', 'display', 'productListView',

    // === SEARCH (user-initiated, infinite variations) ===
    'search', 'query',

    // === PRICE & FILTER FACETS ===
    'filter', 'price', 'price_min', 'price_max',

    // === DATE FILTERS ===
    'year', 'month', 'day', 'date', 'from', 'to',

    // === FACET PREFIXES (startsWith match) ===
    'size_', 'taille_', 'color_', 'couleur_',
    'price_', 'prix_', 'brand_', 'marque_', 'type_', 'vendor_',
];

/**
 * UpdateChecker — Centralized check_url engine for Update Mode.
 *
 * Implements the decision matrix:
 *
 *                    ┌─────────────┬────────────────────────────┐
 *                    │ Source =    │ Source = Other              │
 *                    │ Dataset     │ (rq / ru / discovered)     │
 * ┌──────────────────┼─────────────┼────────────────────────────┤
 * │ HTTP Error       │ +deleted    │ Ignore                     │
 * │ (non 2xx)        │             │                            │
 * ├──────────────────┼─────────────┼────────────────────────────┤
 * │ Redirect (3xx)   │ Dest in DS? │ Dest in DS? Yes: ignore    │
 * │ url != loadedUrl │ Yes: noop   │ No: eligible? → +new_url   │
 * │                  │ No: +redir  │                            │
 * ├──────────────────┼─────────────┼────────────────────────────┤
 * │ Success (2xx)    │ Eligible?   │ Eligible? Yes → +new_url   │
 * │ url == loadedUrl │ No: +del    │ No → Ignore                │
 * │                  │ Yes: OK     │                            │
 * └──────────────────┴─────────────┴────────────────────────────┘
 *
 * Eligibility = French + ignoredExtensions + FORBIDDEN_PARAMS
 */
export class UpdateChecker {
    private consolidator: UrlConsolidator;
    private statsManager: StatsManager;
    private jsonlWriter: JsonlWriter | null;
    private pushedSet: PushedSet | null;

    // JSONL filenames
    static readonly DELETED_FILE = 'deleted_urls.jsonl';
    static readonly REDIRECTED_FILE = 'redirected_urls.jsonl';
    static readonly NEW_URLS_FILE = 'new_urls.jsonl';

    constructor(
        consolidator: UrlConsolidator,
        statsManager: StatsManager,
        jsonlWriter: JsonlWriter | null = null,
        pushedSet: PushedSet | null = null,
    ) {
        this.consolidator = consolidator;
        this.statsManager = statsManager;
        this.jsonlWriter = jsonlWriter;
        this.pushedSet = pushedSet;
    }

    /**
     * Check if a URL contains any forbidden query parameter.
     *
     * Pure check — no side effects. The `filtered_qm` stat is now incremented
     * centrally in routes.ts for every URL containing '?', which already covers
     * URLs with a forbidden param. Double-counting here would inflate the counter.
     */
    private hasForbiddenParams(url: string): boolean {
        try {
            const urlObj = new URL(url);
            const keys = Array.from(urlObj.searchParams.keys());
            for (const param of FORBIDDEN_PARAMS) {
                if (keys.some(key => key === param || key.startsWith(param))) {
                    return true;
                }
            }
            return false;
        } catch {
            return false;
        }
    }

    /**
     * Check if a URL is eligible to be in/enter the Dataset.
     * Criteria (all 3 must pass):
     *   1. Not an ignored extension
     *   2. No forbidden parameters
     *   3. French content (requires pageContent for full check)
     *
     * @param url - The URL to check
     * @param isFrenchContent - Whether the page content was detected as French (from DomainFR)
     */
    isEligible(url: string, isFrenchContent: boolean): boolean {
        // Check 1: Extension
        if (hasIgnoredExtensionForSeed(url)) {
            return false;
        }

        // Check 2: Forbidden params
        if (this.hasForbiddenParams(url)) {
            return false;
        }

        // Check 3: French content
        return isFrenchContent;
    }

    /**
     * Comment cette URL correspond-elle au dataset précédent : exacte, repliée au / final
     * près, ou aucune ?
     *
     * Le repli est nécessaire parce que l'URL stockée vient du dataset précédent tandis que
     * l'URL présentée vient du lien tel qu'écrit dans la page : rien ne garantit la même
     * orthographe. C'est déjà la convention de tout l'aval — `isRedirect` compare en
     * `rightTrimSlash` quelques lignes plus bas, et la soustraction d'orphelins du BO fait
     * `trim($url, "/")` sur ses deux côtés.
     *
     * ⚠ Le repli vit ICI, en lecture, et JAMAIS dans le set `update_dataset:<crawlId>` : ce set
     * est aussi SCANNÉ (UrlConsolidator.ts:214) pour produire la liste d'amorçage, et il arbitre
     * le dédoublonnage des phases 2 et 3. Y stocker des URLs sans leur / final ferait amorcer
     * des URLs modifiées.
     *
     * ⚠ Le helper est privé plutôt qu'une méthode du consolidateur parce que cinq suites de
     * test simulent celui-ci par un objet littéral ne portant que `isInDataset` : élargir son
     * API les casserait toutes en « not a function », pour un seul appelant.
     *
     * ⚠ `isInDataset` échoue OUVERT (catch → false, UrlConsolidator.ts:107-109). Un incident
     * Redis fait donc sous-compter `accounted` — même sens qu'avant ce correctif, aucune
     * régression, mais ce n'est pas une garantie.
     *
     * ⚠⚠ Le retour distingue 'exact' de 'folded' — et non un simple booléen — parce que CASE 1
     * (revue finale de branche) ne peut pas traiter les deux pareil : un statut HTTP recueilli
     * sur une orthographe n'établit rien sur l'autre. Voir le commentaire à l'appel dans CASE 1.
     */
    private async datasetMatch(url: string): Promise<'exact' | 'folded' | 'none'> {
        if (await this.consolidator.isInDataset(url)) {
            return 'exact';
        }
        const alt = url.endsWith('/') ? url.slice(0, -1) : url + '/';
        if (await this.consolidator.isInDataset(alt)) {
            return 'folded';
        }
        return 'none';
    }

    /**
     * Main decision engine method. Called from routes.ts for each processed page in update mode.
     *
     * @param originalUrl - request.url (the URL as it was in the queue)
     * @param loadedUrl - request.loadedUrl (the final URL after any browser redirects)
     * @param source - The origin source of the URL (dataset / request_queue / request_url / discovered)
     * @param httpStatus - HTTP response status code
     * @param isFrenchContent - Whether the page content is French (from DomainFR)
     */
    async checkUrl(
        originalUrl: string,
        loadedUrl: string,
        source: string,
        httpStatus: number,
        isFrenchContent: boolean,
    ): Promise<CheckUrlResult> {
        // PushedSet guard — if a prior attempt already emitted for this URL,
        // skip all side effects (writeJsonl + statsManager.increment).
        if (this.pushedSet && !(await this.pushedSet.tryClaim(originalUrl))) {
            return { action: 'ignored', url: originalUrl, source, reason: 'already_pushed' };
        }

        // La provenance ne peut PAS reposer sur userData.source : la copie DÉCOUVERTE d'une
        // URL du dataset est enfilée ~65 ms avant l'amorce Phase 2 (mesuré sur atox.fr :
        // enqueueLinks à 16:00:51.018, [PHASE 2] à 16:00:51.083), et c'est structurel — Phase 2
        // attend que la page d'accueil soit traitée pour connaître les chemins régionaux. La
        // requête survivante porte donc source='discovered'. On demande au consolidateur, qui
        // sait. Le ternaire court-circuite : aucun aller-retour Redis ajouté quand source suffit —
        // mais l'épinglage du uniqueKey (Tâche 0) supprime justement la requête qui portait
        // source='dataset' : Crawlee garde le userData du PREMIER inserant, et c'est la copie
        // DÉCOUVERTE, enfilée 65 ms plus tôt, qui survit. Pour la population que ce lot vise,
        // le court-circuit ne tire donc plus JAMAIS — `datasetMatch()` est le SEUL chemin qui
        // crédite ces pages, et le retirer réintroduirait tout le défaut, épinglage ou pas.
        const match = source === 'dataset' ? 'exact' : await this.datasetMatch(originalUrl);
        const isFromDataset = match !== 'none';
        const isHttpError = httpStatus >= 400 || httpStatus === 0;
        const isRedirect = rightTrimSlash(originalUrl) !== rightTrimSlash(loadedUrl);

        // ═══════════════════════════════════════════
        //  CASE 1: HTTP Error (non 2xx/3xx)
        // ═══════════════════════════════════════════
        if (isHttpError) {
            // CASE 1 asks "has this resource disappeared?" — a 'folded' match only proves
            // some spelling of this URL was in the dataset, never that THIS spelling shares
            // the OTHER spelling's HTTP status. Gate on 'exact', not `isFromDataset`: dataset
            // has /a, a page links /a/ (never in the dataset), a strict-routing server 404s
            // on /a/ while /a is alive — folding here would emit `deleted` for /a/ AND
            // `confirmed` for /a in the SAME run, two contradictory verdicts for one page.
            // A folded match falls through to the non-dataset branch below (`ignored /
            // non_dataset_error`) — no errors/errors_unprocessed either: those feed the
            // errorRate numerator this same wave is already trying not to inflate further.
            // CASE 2/3 keep the fold — a 200 or a redirect on the folded spelling DOES teach
            // us something about the page; only "this resource is GONE" does not survive it.
            // ⛔ Do not widen this back to `isFromDataset`: CASE 1 was deliberately narrowed to
            // 404/410 after incident 1320-402 (63 anti-bot 403s → 59 false fiche deletions) —
            // this gate is the same principle applied to URL identity instead of HTTP status.
            if (match === 'exact') {
                await this.statsManager.increment("errors");
                // Off-book half of `errors`: this URL threw on the HTTP status policy
                // (routes.ts) or exhausted its retries (failedRequestHandler), so it
                // never reached increment("processed"). The error-rate breaker needs it
                // in its denominator, or the ratio is not a proportion — see
                // errorRateBreaker.ts. CASE 3 below is NOT counted here: a 2xx
                // not_eligible URL is already inside `processed`.
                await this.statsManager.increment("errors_unprocessed");
                // A deletion claim requires a server verdict that the resource is
                // GONE: 404/410 only. 401/403/407/429/5xx/status-0 are blocks or
                // outages — the page may be alive (incident 1320-402: 63 anti-bot
                // 403s became 59 false fiche deletions BO-side). Those still count
                // as errors (health/circuit-breaker unchanged) but emit NO deleted
                // event; a truly dead URL will 404 on a later MAJ.
                if (httpStatus === 404 || httpStatus === 410) {
                    const result: CheckUrlResult = {
                        action: 'deleted',
                        url: originalUrl,
                        source,
                        reason: `http_error_${httpStatus}`,
                    };
                    await this.writeJsonl(UpdateChecker.DELETED_FILE, result);
                    await this.statsManager.increment("accounted");
                    return result;
                }
                return { action: 'ignored', url: originalUrl, source, reason: `unverified_http_error_${httpStatus}` };
            } else {
                // Non-dataset URL error → just ignore, don't track
                return { action: 'ignored', url: originalUrl, source, reason: 'non_dataset_error' };
            }
        }

        // ═══════════════════════════════════════════
        //  CASE 2: Redirect (loaded URL differs from original)
        // ═══════════════════════════════════════════
        if (isRedirect) {
            const destInDataset = await this.consolidator.isInDataset(loadedUrl);

            if (isFromDataset) {
                if (destInDataset) {
                    // Redirect to another Dataset URL → destination already tracked.
                    // Still RECORD the mapping: the BO needs old→new to retire the old
                    // fiche, and the signal must be repeatable across MAJs (a missed
                    // one-shot delivery = permanent divergence, incident 1079-327).
                    // No 'redirects' increment — that counter feeds the circuit breaker.
                    await this.writeJsonl(UpdateChecker.REDIRECTED_FILE, {
                        action: 'redirected',
                        url: originalUrl,
                        source,
                        destination: loadedUrl,
                        reason: 'redirect_to_existing',
                    });
                    // Crédit conditionnel à l'orthographe exacte : l'exacte est de toute façon
                    // seedée et comptée pour son propre compte (Tâche 0) — créditer aussi la
                    // repliée doublerait la même entrée du dataset précédent et pourrait porter
                    // `coverage` au-dessus de 1. Voir le docblock de `datasetMatch()` ci-dessus.
                    if (match === 'exact') {
                        await this.statsManager.increment("accounted");
                    }
                    return { action: 'confirmed', url: originalUrl, source, reason: 'redirect_to_existing' };
                } else {
                    // Redirect to a URL NOT in Dataset → track the redirection
                    await this.statsManager.increment("redirects");
                    const result: CheckUrlResult = {
                        action: 'redirected',
                        url: originalUrl,
                        source,
                        destination: loadedUrl,
                    };
                    await this.writeJsonl(UpdateChecker.REDIRECTED_FILE, result);
                    // Même garde que ci-dessus : crédit réservé à l'orthographe exacte.
                    if (match === 'exact') {
                        await this.statsManager.increment("accounted");
                    }
                    return result;
                }
            } else {
                // Non-dataset URL redirected
                if (destInDataset) {
                    // Redirects to an existing Dataset URL → ignored for counters, but
                    // RECORD the mapping (repeatable signal — request_queue re-seeds the
                    // old URL every MAJ; this lets the BO retire a leftover old fiche).
                    await this.writeJsonl(UpdateChecker.REDIRECTED_FILE, {
                        action: 'redirected',
                        url: originalUrl,
                        source,
                        destination: loadedUrl,
                        reason: 'redirect_to_existing_dataset',
                    });
                    return { action: 'ignored', url: originalUrl, source, reason: 'redirect_to_existing_dataset' };
                } else {
                    // Redirects to a new URL — check eligibility of the DESTINATION
                    if (this.isEligible(loadedUrl, isFrenchContent)) {
                        await this.statsManager.increment("new_urls");
                        const result: CheckUrlResult = {
                            action: 'new_url',
                            url: loadedUrl,
                            source,
                            reason: 'redirect_eligible_destination',
                        };
                        await this.writeJsonl(UpdateChecker.NEW_URLS_FILE, result);
                        return result;
                    }
                    return { action: 'ignored', url: originalUrl, source, reason: 'redirect_ineligible_destination' };
                }
            }
        }

        // ═══════════════════════════════════════════
        //  CASE 3: Success (2xx, no redirect)
        // ═══════════════════════════════════════════
        if (isFromDataset) {
            // Dataset URL, 2xx, same URL → check if still eligible
            if (this.isEligible(loadedUrl, isFrenchContent)) {
                // Confirmed: URL is still valid in Dataset
                // Crédit conditionnel à l'orthographe exacte (même garde que CASE 2) : la
                // repliée n'écrit aucun JSONL ici, donc sans le crédit c'est un no-op — exactement
                // ce qu'on veut, l'exacte étant déjà seedée et comptée pour son propre compte.
                if (match === 'exact') {
                    await this.statsManager.increment("accounted");
                }
                return { action: 'confirmed', url: originalUrl, source };
            } else {
                // No longer eligible → mark as deleted
                await this.statsManager.increment("errors");
                const result: CheckUrlResult = {
                    action: 'deleted',
                    url: originalUrl,
                    source,
                    reason: 'not_eligible',
                };
                await this.writeJsonl(UpdateChecker.DELETED_FILE, result);
                // L'événement `deleted` s'écrit pour les deux orthographes — l'inéligibilité est
                // un jugement sur le CONTENU, valable pour l'une comme pour l'autre, contrairement
                // au statut HTTP de CASE 1. Seul le crédit reste réservé à l'orthographe exacte.
                if (match === 'exact') {
                    await this.statsManager.increment("accounted");
                }
                return result;
            }
        } else {
            // Non-dataset URL, 2xx → check if eligible for insertion
            if (this.isEligible(loadedUrl, isFrenchContent)) {
                await this.statsManager.increment("new_urls");
                const result: CheckUrlResult = {
                    action: 'new_url',
                    url: loadedUrl,
                    source,
                    reason: 'eligible_new_content',
                };
                await this.writeJsonl(UpdateChecker.NEW_URLS_FILE, result);
                return result;
            }
            return { action: 'ignored', url: originalUrl, source, reason: 'not_eligible' };
        }
    }

    /**
     * Write a JSONL line if the writer is available.
     */
    private async writeJsonl(filename: string, data: CheckUrlResult): Promise<void> {
        if (this.jsonlWriter) {
            try {
                await this.jsonlWriter.writeLine(filename, {
                    url: data.url,
                    source: data.source,
                    action: data.action,
                    reason: data.reason || undefined,
                    destination: data.destination || undefined,
                    timestamp: new Date().toISOString(),
                });
            } catch (e) {
                console.error(`[UpdateChecker] Failed to write JSONL to ${filename}: ${e}`);
            }
        }
    }
}
