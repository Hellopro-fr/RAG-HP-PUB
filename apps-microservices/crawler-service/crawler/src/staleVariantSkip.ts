/**
 * Sentinel for queue-purge component A: thrown from a preNavigationHook so a
 * stale (already-superseded-by-a-committed-skip-decision) queued variant is
 * dropped BEFORE page.goto — no HTTP fetch. Extends NonRetryableError so Crawlee
 * does not retry it. failedRequestHandler recognises it by the "StaleVariantSkip"
 * marker in request.errorMessages and counts it as purged_prenav.
 */
import { NonRetryableError } from "crawlee";

export const QUEUE_PURGE_ENABLED =
    (process.env.QUEUE_PURGE_ENABLED ?? "false").toLowerCase() === "true";

// failedRequestHandler recognises the sentinel by this marker inside the
// stringified request.errorMessages (the handler receives no error object).
// Single source of truth so a class rename can't silently break accounting.
export const STALE_VARIANT_SKIP_MARKER = "StaleVariantSkip";

export class StaleVariantSkip extends NonRetryableError {
    readonly stripped: string;
    constructor(url: string, stripped: string) {
        super(`${STALE_VARIANT_SKIP_MARKER}: ${url} -> ${stripped}`);
        this.name = STALE_VARIANT_SKIP_MARKER;
        this.stripped = stripped;
    }
}
