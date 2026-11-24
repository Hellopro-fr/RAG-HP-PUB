/**
 * A664 — bounded wait for a Magento Fotorama gallery before the page HTML is captured.
 *
 * Measured on inoxdesign.fr (local Camoufox bench, 2026-11-23, 15 captures per variant):
 * the gallery initialises AFTER network idle, so no network wait guarantees it
 * (networkidle capped at 30 s: 7/15 rendered). Waiting for the rendered frame gives 14/15
 * against 6/15 for the current code (p = 0.005). Only pages carrying the gallery
 * placeholder pay the wait. Fiche: banc_selecteurs_data/a664/mesure_rendu_galerie_2026-11-23.md
 */

export const GALLERY_PLACEHOLDER_SELECTOR = "[data-gallery-role=gallery-placeholder]";
export const GALLERY_RENDERED_SELECTOR = ".fotorama__stage__frame";

const DEFAULT_GALLERY_RENDER_WAIT_MS = 15000;

/** Minimal page surface used here (Playwright `Page` satisfies it). */
export interface GalleryWaitPage {
    evaluate(expression: string): Promise<unknown>;
    waitForSelector(
        selector: string,
        options: { state: "attached"; timeout: number },
    ): Promise<unknown>;
}

export type GalleryWaitResult = "disabled" | "skipped" | "rendered" | "timeout" | "error";

/**
 * Resolves GALLERY_RENDER_WAIT_MS: non-negative integer ms; 0 disables the wait.
 * Empty / non-numeric / negative → 15000.
 */
export function resolveGalleryRenderWaitMs(raw: string | undefined): number {
    const v = (raw ?? "").trim();
    if (v === "") return DEFAULT_GALLERY_RENDER_WAIT_MS;
    const n = Number(v);
    return Number.isFinite(n) && n >= 0 ? Math.floor(n) : DEFAULT_GALLERY_RENDER_WAIT_MS;
}

// Derived once at module load from the process environment.
export const GALLERY_RENDER_WAIT_MS: number =
    resolveGalleryRenderWaitMs(process.env.GALLERY_RENDER_WAIT_MS);

/**
 * If the page carries the gallery placeholder, waits up to `waitMs` for the first
 * rendered frame. Never throws: a timeout or a page error is swallowed, like the
 * `networkidle` wait of `waitAndScroll()`; the capture then proceeds as before.
 */
export async function waitForGalleryRender(
    page: GalleryWaitPage,
    url: string,
    log: { info(message: string): void },
    waitMs: number = GALLERY_RENDER_WAIT_MS,
): Promise<GalleryWaitResult> {
    if (waitMs <= 0) return "disabled";
    let hasPlaceholder: boolean;
    try {
        hasPlaceholder = Boolean(await page.evaluate(
            `!!document.querySelector(${JSON.stringify(GALLERY_PLACEHOLDER_SELECTOR)})`,
        ));
    } catch {
        return "error";
    }
    if (!hasPlaceholder) return "skipped";
    try {
        await page.waitForSelector(GALLERY_RENDERED_SELECTOR, { state: "attached", timeout: waitMs });
        return "rendered";
    } catch {
        log.info(`[gallery-wait] frame not rendered after ${waitMs}ms: ${url}`);
        return "timeout";
    }
}
