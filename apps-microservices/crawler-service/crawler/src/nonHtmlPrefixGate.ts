import {
    decide,
    normalizeUrlIdentity,
    prefixKey,
    recordHtml,
    recordNonHtml,
    recordProbeFailure,
} from "./nonHtmlPrefix.js";
import type { NonHtmlPrefixState } from "./nonHtmlPrefix.js";
import { serializeNonHtmlPrefixState } from "./nonHtmlPrefixSidecar.js";

export type GatePoint = "enqueue" | "prenav" | "seed";

export interface NonHtmlPrefixGateDeps {
    mode: "shadow" | "on";
    state: NonHtmlPrefixState;
    log: (message: string) => void;
    persist: (serialized: string) => void;
    now?: () => string;
}

/**
 * Applies the NONHTML_PREFIX_MODE policy on top of the pure decisions of nonHtmlPrefix.ts.
 * `check` is synchronous (it runs inside Crawlee's transformRequestFunction) and never
 * touches a counter: the caller increments `filtered_nonhtml` only when it actually drops.
 */
export class NonHtmlPrefixGate {
    readonly mode: "shadow" | "on";
    readonly state: NonHtmlPrefixState;
    private readonly log: (message: string) => void;
    private readonly persist: (serialized: string) => void;
    private readonly now: () => string;
    private readonly exempt = new Set<string>();

    constructor(deps: NonHtmlPrefixGateDeps) {
        this.mode = deps.mode;
        this.state = deps.state;
        this.log = deps.log;
        this.persist = deps.persist;
        this.now = deps.now ?? (() => new Date().toISOString());
    }

    addExempt(url: string): void {
        this.exempt.add(normalizeUrlIdentity(url));
    }

    exemptCount(): number {
        return this.exempt.size;
    }

    /** true = let the URL through. */
    check(url: string, point: GatePoint): boolean {
        const decision = decide(this.state, url, (n) => this.exempt.has(n));
        if (decision === "allow") return true;
        const key = prefixKey(url);
        if (decision === "probe") {
            this.log(`[nonhtml-prefix] probe (${point}): ${url} [${key}]`);
            return true;
        }
        if (this.mode === "on") {
            this.log(`[nonhtml-prefix] blocked (${point}): ${url} [${key}]`);
            return false;
        }
        this.log(`[nonhtml-prefix] would block (${point}): ${url} [${key}]`);
        return true;
    }

    onNonHtml(url: string): void {
        const event = recordNonHtml(this.state, url, this.now());
        const key = prefixKey(url);
        const n = key === null ? 0 : (this.state.prefixes.get(key)?.nonHtml ?? 0);
        if (event === "learned") {
            this.log(`Non-HTML prefix learned: ${key} (n=${n})`);
            this.persist(serializeNonHtmlPrefixState(this.state));
        } else if (event === "confirmed") {
            this.log(`Non-HTML prefix confirmed by probe: ${key} (n=${n})`);
            this.persist(serializeNonHtmlPrefixState(this.state));
        } else if (event === "isolated") {
            this.persist(serializeNonHtmlPrefixState(this.state));
        }
    }

    onHtml(url: string): void {
        const event = recordHtml(this.state, url);
        if (event !== "released") return;
        const key = prefixKey(url);
        const n = key === null ? 0 : (this.state.prefixes.get(key)?.nonHtml ?? 0);
        this.log(`Non-HTML prefix released: ${key} (n=${n})`);
        this.persist(serializeNonHtmlPrefixState(this.state));
    }

    onProbeFailure(url: string): void {
        if (!recordProbeFailure(this.state, url)) return;
        this.log(`[nonhtml-prefix] probe failed: ${url} [${prefixKey(url)}]`);
    }
}
