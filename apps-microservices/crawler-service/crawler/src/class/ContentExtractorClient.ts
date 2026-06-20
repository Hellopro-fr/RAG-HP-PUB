import axios, { AxiosInstance, AxiosError } from "axios";
import pLimit from "p-limit";

type PLimitInstance = ReturnType<typeof pLimit>;

/** Minimal POST shape so tests can inject a fake without a network. */
type Poster = (path: string, body: unknown) => Promise<{ data: { content?: string } }>;

interface CleanResponse { content?: string }

/**
 * Client for content-extractor-api-service POST /clean. Tier-2 uses it to
 * boilerplate-strip two crawled pages before similarity comparison. Bespoke
 * retry: the shared DetectionLangueClient retries only on 503, but /clean fails
 * with 413/422/500 — 413/422 are deterministic (never retry); 500 / network
 * errors retry once. See spec §6.
 */
export class ContentExtractorClient {
    private post: Poster;
    private limit: PLimitInstance;
    private maxRetries: number;

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
        this.limit = pLimit(maxConcurrency);

        if (poster) {
            this.post = poster;
        } else {
            const client: AxiosInstance = axios.create({ baseURL: url, timeout: timeoutMs });
            this.post = (path, body) => client.post<CleanResponse>(path, body);
        }
    }

    /** Returns the cleaned main text (may be ""). Throws on persistent error. */
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
                const deterministic = status === 413 || status === 422;
                if (!deterministic && attempt < this.maxRetries) continue;
                throw new Error(`content-extractor /clean error (status=${status ?? "n/a"})`);
            }
        }
        throw new Error("content-extractor /clean retry loop exited without result");
    }
}
