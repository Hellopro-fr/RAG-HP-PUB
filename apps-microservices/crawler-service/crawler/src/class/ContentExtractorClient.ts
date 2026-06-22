import axios, { AxiosInstance, AxiosError } from "axios";
import pLimit from "p-limit";

type PLimitInstance = ReturnType<typeof pLimit>;

/** Minimal POST shape so tests can inject a fake without a network. */
type Poster = (path: string, body: unknown) => Promise<{ data: { content?: string } }>;

interface CleanResponse { content?: string }

/**
 * Error from content-extractor /clean. `transient` marks capacity/infra failures
 * (503 admission, timeout, network) that are worth retrying later, vs terminal
 * content failures (413/422 too-big/invalid, 500 extraction error) that will not
 * change on replay. Tier-2 uses `transient` so a service outage does not pollute
 * the comparison tally (see diezTier2.adjudicate).
 */
export class ContentExtractorError extends Error {
    readonly status?: number;
    readonly transient: boolean;
    constructor(status: number | undefined, transient: boolean) {
        super(`content-extractor /clean error (status=${status ?? "n/a"})`);
        this.name = "ContentExtractorError";
        this.status = status;
        this.transient = transient;
    }
}

/**
 * Client for content-extractor-api-service POST /clean. Tier-2 uses it to
 * boilerplate-strip two crawled pages before similarity comparison. Bespoke
 * retry: 413/422 are deterministic (never retry); 500 / timeout / network retry
 * once; 503 (admission capacity shed) honours Retry-After — capped — before the
 * single retry. See spec §6 + the 2026-06-20 content-extractor hardening.
 */
export class ContentExtractorClient {
    private post: Poster;
    private limit: PLimitInstance;
    private maxRetries: number;
    private retryAfterCapMs: number;

    constructor(baseUrl?: string, poster?: Poster) {
        const url =
            baseUrl ||
            process.env.CONTENT_EXTRACTOR_API_URL ||
            "http://content-extractor-api-service:8600";
        if (!baseUrl && !process.env.CONTENT_EXTRACTOR_API_URL) {
            console.warn("CONTENT_EXTRACTOR_API_URL not set, using default: http://content-extractor-api-service:8600");
        }
        const timeoutMs = parseInt(process.env.CONTENT_EXTRACTOR_TIMEOUT_S ?? "20") * 1000;
        const maxConcurrency = parseInt(process.env.CONTENT_EXTRACTOR_MAX_CONCURRENCY ?? "4");
        this.maxRetries = parseInt(process.env.CONTENT_EXTRACTOR_MAX_RETRIES ?? "1");
        // Cap how long we honour a 503 Retry-After before the single retry, so a
        // large server-suggested delay cannot stall the crawl page handler.
        this.retryAfterCapMs = parseInt(process.env.CONTENT_EXTRACTOR_RETRY_AFTER_CAP_S ?? "5") * 1000;
        this.limit = pLimit(maxConcurrency);

        if (poster) {
            this.post = poster;
        } else {
            const client: AxiosInstance = axios.create({ baseURL: url, timeout: timeoutMs });
            this.post = (path, body) => client.post<CleanResponse>(path, body);
        }
    }

    /** Returns the cleaned main text (may be ""). Throws ContentExtractorError on persistent error. */
    async clean(html: string): Promise<string> {
        return this.limit(() => this._cleanWithRetry(html));
    }

    private async _cleanWithRetry(html: string): Promise<string> {
        for (let attempt = 0; attempt <= this.maxRetries; attempt++) {
            try {
                const res = await this.post("/clean", { html, format: "text" });
                return res.data.content ?? "";
            } catch (error) {
                const status = (error as AxiosError).response?.status;
                const deterministic = status === 413 || status === 422; // content-level, never retry
                if (!deterministic && attempt < this.maxRetries) {
                    // Admission capacity shed: honour Retry-After (capped) before the one retry.
                    if (status === 503) {
                        const waitMs = this._retryAfterMs(error);
                        if (waitMs > 0) await ContentExtractorClient._sleep(waitMs);
                    }
                    continue;
                }
                // 503 / timeout / network (no response) are transient; 413/422/500 are terminal.
                const transient = status === 503 || status === undefined;
                throw new ContentExtractorError(status, transient);
            }
        }
        throw new ContentExtractorError(undefined, true);
    }

    /** Retry-After (seconds) from the error response, capped to retryAfterCapMs. 0 if absent/invalid. */
    private _retryAfterMs(error: unknown): number {
        const header = (error as AxiosError).response?.headers?.["retry-after"];
        const raw = Array.isArray(header) ? header[0] : header;
        const seconds = parseInt(String(raw ?? ""));
        if (!Number.isFinite(seconds) || seconds <= 0) return 0;
        return Math.min(seconds * 1000, this.retryAfterCapMs);
    }

    private static _sleep(ms: number): Promise<void> {
        return new Promise((resolve) => setTimeout(resolve, ms));
    }
}
