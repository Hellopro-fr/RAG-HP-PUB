/**
 * Camoufox launch input for the crawler's default (Camoufox) browser path.
 *
 * Why this exists — the cryolor.com class of bug:
 * Multilingual sites frequently ship client-side language negotiation. Drupal's
 * `browser_language_detection` module, for example, reads `navigator.language`
 * and redirects a French page to the default-language root when the browser is
 * not French:
 *
 *     o = (navigator.languages?.[0] ?? navigator.language).substring(0, 2);
 *     if (o in redirections && o !== pageLang) window.location.href = redirections[o];
 *
 * Camoufox launched with only `{ headless: true }` leaves `navigator.language`
 * at the container's system default (typically `en-US` in Docker). On such a
 * site the crawler is bounced off the seeded `/fr` URL onto the English root and
 * then mis-detected as "not French". Pinning the locale to French keeps
 * `navigator.language` aligned with the French pages we crawl, matching what
 * api-detection-langue-fr already does (scraper.py: `locale = 'fr-FR'`).
 *
 * GeoIP is deliberately NOT enabled here: the crawler's Apify proxy is
 * auto-country, so IP-derived locale would be non-deterministic. An explicit
 * locale is the reliable choice.
 */
export const CRAWLER_BROWSER_LOCALE = 'fr-FR';

export interface CamoufoxLaunchInput {
    headless: boolean;
    /** First listed locale is used for the Intl API / navigator.language. */
    locale: string;
}

/**
 * Build the options passed to camoufox-js `launchOptions`. Always pins the
 * French locale so the crawler's browser advertises `navigator.language = fr`.
 */
export function buildCamoufoxLaunchInput(headless: boolean): CamoufoxLaunchInput {
    return { headless, locale: CRAWLER_BROWSER_LOCALE };
}
