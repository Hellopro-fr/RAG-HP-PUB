import axios, { AxiosInstance } from "axios";

export interface DetectionResult {
    ok: boolean;
    method: string;
    url?: string;
    confidence?: number;
    alternative_urls?: string[];
    error?: string;
}

export interface DetectOptions {
    mode?: "simple" | "complete";
    forcedMethod?: string;
    useNlpDetection?: boolean;
    proxyUrl?: string;
}

export interface CheckUrlResult {
    ok: boolean;
    method: string;
    url?: string;
    original_url?: string;
}

export class DetectionLangueClient {
    private client: AxiosInstance;

    constructor(baseUrl?: string) {
        const url =
            baseUrl ||
            process.env.DETECTION_LANGUE_API_URL ||
            "http://api-detection-langue-fr-service:8999";
        this.client = axios.create({
            baseURL: `${url}/api/v1`,
            timeout: 30000,
        });
    }

    /**
     * Full detection: URL patterns + HTML content + NLP (optional).
     * Pass the HTML already fetched by the crawler to avoid double-fetch.
     */
    async detect(
        url: string,
        htmlContent?: string,
        options?: DetectOptions
    ): Promise<DetectionResult> {
        const response = await this.client.post<DetectionResult>("/detect", {
            url,
            html_content: htmlContent || undefined,
            mode: options?.mode ?? "complete",
            forced_method: options?.forcedMethod ?? undefined,
            use_nlp_detection: options?.useNlpDetection ?? true,
            proxy_url: options?.proxyUrl ?? undefined,
        });
        return response.data;
    }

    /**
     * Fast URL-only check (no HTML fetch, no NLP).
     * Equivalent to the old DomainFR.checkUrl(url, false).
     */
    async checkUrl(
        url: string,
        trackRedirect: boolean = false
    ): Promise<CheckUrlResult> {
        const response = await this.client.get<CheckUrlResult>("/check-url", {
            params: { url, track_redirect: trackRedirect },
        });
        return response.data;
    }

    /**
     * Extract the primary detection method from a combined API method string.
     * Prefers HTML-based methods (langHtml, matchMeta, matchHttpEquiv) over
     * URL-based ones (direct_match, pattern_match_*), because HTML methods
     * are the only ones that forced_method can validate on internal pages.
     *
     * e.g. "direct_match+langHtml+nlp_confirmed" -> "langHtml"
     *      "langHtml+nlp_confirmed"               -> "langHtml"
     *      "direct_match+nlp_confirmed"            -> "direct_match"
     *      "nlp_confirmed"                         -> "nlp_confirmed"
     */
    static extractPrimaryMethod(method: string): string {
        const parts = method.split("+");
        const HTML_METHODS = ["langHtml", "matchMeta", "matchHttpEquiv"];
        const htmlMethod = parts.find((p) => HTML_METHODS.includes(p));
        return htmlMethod ?? parts[0];
    }

    /**
     * Returns true if the stored method is URL-based or NLP-only,
     * meaning forced_method validation won't work on internal pages
     * and NLP must be used instead.
     */
    static requiresNlpValidation(method: string): boolean {
        const URL_OR_NLP_METHODS = [
            "direct_match",
            "pattern_match_path",
            "pattern_match_query",
            "nlp_confirmed",
            "nlp_soft_confirmed",
            "nlp_only",
            "french_lexical_signal",
            "alternative_link_validated",
        ];
        return URL_OR_NLP_METHODS.includes(method);
    }
}
