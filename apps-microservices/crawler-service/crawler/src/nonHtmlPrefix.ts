// apps-microservices/crawler-service/crawler/src/nonHtmlPrefix.ts
/**
 * R23 (2): non-HTML prefix learning — pure decision module.
 *
 * Learns, per `host + parent directory`, the prefixes that only ever serve non-HTML
 * (marsaleix `/image/<token>` served as image/* with no extension), so the crawler stops
 * replaying them. No I/O, no env read at load time: the mode and the parameters are
 * resolved by the caller from the environment and passed in. Spec:
 * docs/superpowers/specs/2026-10-16-crawler-nonhtml-prefix-learning-design.md
 */
import { posix } from "node:path";
import { hasIgnoredExtensionForSeed } from "./seedExtensionFilter.js";

export type NonHtmlPrefixMode = "off" | "shadow" | "on";

/** Anything but "shadow" / "on" (trimmed, case-folded) is "off" — undefined, "" and unknown included. */
export function resolveNonHtmlPrefixMode(raw: string | undefined): NonHtmlPrefixMode {
    const v = (raw ?? "").trim().toLowerCase();
    return v === "shadow" || v === "on" ? v : "off";
}

/**
 * Positive integer from an env string. Empty, non-integer or <= 0 falls back: an empty
 * variable must never read as 0 (the `resolveTimeoutMaxRetries("")` trap, httpStatusPolicy.ts).
 */
export function resolvePositiveInt(raw: string | undefined, fallback: number): number {
    const v = (raw ?? "").trim();
    if (!/^\d+$/.test(v)) return fallback;
    const n = Number(v);
    return n > 0 ? n : fallback;
}

export interface NonHtmlPrefixParams {
    minNonHtml: number;
    probes: number;
    isolatedMax: number;
}

export const NONHTML_PREFIX_DEFAULTS: NonHtmlPrefixParams = {
    minNonHtml: 5,
    probes: 3,
    isolatedMax: 10000,
};

export function resolveNonHtmlPrefixParams(env: Record<string, string | undefined>): NonHtmlPrefixParams {
    return {
        minNonHtml: resolvePositiveInt(env.NONHTML_PREFIX_MIN, NONHTML_PREFIX_DEFAULTS.minNonHtml),
        probes: resolvePositiveInt(env.NONHTML_PREFIX_PROBES, NONHTML_PREFIX_DEFAULTS.probes),
        isolatedMax: resolvePositiveInt(env.NONHTML_ISOLATED_MAX, NONHTML_PREFIX_DEFAULTS.isolatedMax),
    };
}

/** Queue identity: trailing slashes dropped (same rule as `rightTrimSlash`, functions.ts). */
export function normalizeUrlIdentity(url: string): string {
    return url.replace(/\/+$/, "");
}

/**
 * `host + parent directory of the path`. Query and fragment are ignored. Invalid URL or a
 * parent directory that is the root (`/telechargement?id=12`) gives null: such a URL has
 * no prefix to learn and is handled as an isolated URL.
 */
export function prefixKey(url: string): string | null {
    let u: URL;
    try {
        u = new URL(url);
    } catch {
        return null;
    }
    const dir = posix.dirname(u.pathname);
    if (dir === "/" || dir === ".") return null;
    return `${u.host}${dir}`;
}

export interface Probation {
    admitted: number;
    probeUrl: string | null;
    resolved: boolean;
}

export interface PrefixEntry {
    nonHtml: number;
    sawHtml: boolean;
    confirmed: boolean;
    confirmedAt: string | null;
    probation: Probation | null;
}

export interface NonHtmlPrefixState {
    params: NonHtmlPrefixParams;
    prefixes: Map<string, PrefixEntry>;
    isolated: Set<string>;
    loadedIsolated: Set<string>;
}

export function createNonHtmlPrefixState(params: NonHtmlPrefixParams): NonHtmlPrefixState {
    return { params, prefixes: new Map(), isolated: new Set(), loadedIsolated: new Set() };
}

/** A key blocks once confirmed or K non-HTML hits are counted — and never after an HTML page was seen. */
export function isKeyBlocking(entry: PrefixEntry, params: NonHtmlPrefixParams): boolean {
    return !entry.sawHtml && (entry.confirmed || entry.nonHtml >= params.minNonHtml);
}

const newEntry = (): PrefixEntry => ({
    nonHtml: 0,
    sawHtml: false,
    confirmed: false,
    confirmedAt: null,
    probation: null,
});

const isPending = (p: Probation | null): p is Probation => p !== null && !p.resolved;

/** Adds an identity to the isolated set unless already present or at the cap. */
function addIsolated(state: NonHtmlPrefixState, identity: string): boolean {
    if (state.isolated.has(identity) || state.isolated.size >= state.params.isolatedMax) return false;
    state.isolated.add(identity);
    return true;
}

export type NonHtmlEvent = "ignored" | "counted" | "learned" | "confirmed" | "isolated";

/** A response of a non-HTML content-type was served for `url`. Order of the cases is normative. */
export function recordNonHtml(state: NonHtmlPrefixState, url: string, nowIso: string): NonHtmlEvent {
    // 1. A URL with a known binary extension is already filtered elsewhere: learn nothing.
    if (hasIgnoredExtensionForSeed(url)) return "ignored";
    const n = normalizeUrlIdentity(url);
    const key = prefixKey(url);
    // 2. No prefix to learn: remember the URL itself (capped).
    if (key === null) return addIsolated(state, n) ? "isolated" : "ignored";
    // 3. Entry creation; a key that served HTML keeps its veto for the whole crawl.
    let entry = state.prefixes.get(key);
    if (!entry) {
        entry = newEntry();
        state.prefixes.set(key, entry);
    }
    if (entry.sawHtml) {
        entry.nonHtml++;
        return "counted";
    }
    // 4.
    const wasBlocking = isKeyBlocking(entry, state.params);
    entry.nonHtml++;
    // 5. Under an unresolved probation, ANY non-HTML under the key confirms it.
    if (isPending(entry.probation)) {
        entry.probation.resolved = true;
        entry.probation.probeUrl = null;
        entry.confirmed = true;
        entry.confirmedAt = nowIso;
        return "confirmed";
    }
    // 6.
    if (wasBlocking) return "counted";
    // 7. K reached by this very hit.
    if (isKeyBlocking(entry, state.params)) {
        entry.confirmedAt = nowIso;
        return "learned";
    }
    // 8. Under K: the URL is also remembered on its own (capped).
    return addIsolated(state, n) ? "isolated" : "counted";
}

export type HtmlEvent = "none" | "released";

/** An `ok`-class HTML page was served for `url`. Sets the veto; "released" = a blocking or probing key was freed. */
export function recordHtml(state: NonHtmlPrefixState, url: string): HtmlEvent {
    const key = prefixKey(url);
    if (key === null) return "none";
    const entry = state.prefixes.get(key);
    if (!entry) {
        state.prefixes.set(key, { ...newEntry(), sawHtml: true });
        return "none";
    }
    if (!entry.sawHtml && (isKeyBlocking(entry, state.params) || isPending(entry.probation))) {
        entry.sawHtml = true;
        if (entry.probation) {
            entry.probation.resolved = true;
            entry.probation.probeUrl = null;
        }
        return "released";
    }
    entry.sawHtml = true;
    return "none";
}

/**
 * The probe URL failed (timeout / error, no HTTP verdict). True only if `url` is the in-flight
 * probe of an unresolved probation. Out of admissions ⇒ the key is confirmed without signal
 * (blocks, stays persisted — spec 3.3).
 */
export function recordProbeFailure(state: NonHtmlPrefixState, url: string): boolean {
    const key = prefixKey(url);
    if (key === null) return false;
    const entry = state.prefixes.get(key);
    const p = entry?.probation;
    if (!entry || !p || p.resolved || p.probeUrl !== normalizeUrlIdentity(url)) return false;
    p.probeUrl = null;
    if (p.admitted >= state.params.probes) {
        p.resolved = true;
        entry.confirmed = true;
    }
    return true;
}

export type NonHtmlDecision = "allow" | "block" | "probe";

/** Verdict for `url` before it is fetched. May admit a probe (mutates the probation). Order is normative. */
export function decide(
    state: NonHtmlPrefixState,
    url: string,
    isExempt: (normalizedUrl: string) => boolean,
): NonHtmlDecision {
    const n = normalizeUrlIdentity(url);
    // 1. Absolute exemption (previous dataset, homepage).
    if (isExempt(n)) return "allow";
    // 2. Isolated URL learned by a previous crawl.
    if (state.loadedIsolated.has(n)) return "block";
    // 3.
    const key = prefixKey(url);
    const entry = key === null ? undefined : state.prefixes.get(key);
    if (!entry || entry.sawHtml) return "allow";
    // 4. Probation: one probe at a time, `probes` admissions at most.
    const p = entry.probation;
    if (isPending(p)) {
        if (p.probeUrl === n) return "probe";
        if (p.probeUrl !== null) return "block";
        if (p.admitted < state.params.probes) {
            p.admitted++;
            p.probeUrl = n;
            return "probe";
        }
        p.resolved = true;
        entry.confirmed = true;
        return "block";
    }
    // 5.
    return isKeyBlocking(entry, state.params) ? "block" : "allow";
}
