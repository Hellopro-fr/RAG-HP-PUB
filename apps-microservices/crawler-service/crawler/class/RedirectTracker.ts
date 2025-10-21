import { ExtendedOptionsOfTextResponseBody, gotScraping } from "got-scraping";
import { IRedirect } from "../interfaces/IRedirect.js";
import { IRedirectResponse } from "../interfaces/IRedirectResponse.js";

export class RedirectTracker {
    private _redirects: IRedirect[];
    private _finalUrl: string | null;

    constructor() {
        this._redirects = [];
        this._finalUrl = null;
    }

    public set redirects(v: any) {
        this._redirects = v;
    }

    public set finalUrl(v: string | null) {
        this._finalUrl = v;
    }

    private getRedirects(): IRedirect[] {
        return this._redirects;
    }

    private getFinalUrl(): string | null {
        return this._finalUrl;
    }

    private getInitialUrl(): string | null {
        return this._redirects.length > 0 ? this._redirects[0].from : null;
    }

    private getRedirectChain(): string[] {
        return this._redirects.map((redirect) => redirect.to);
    }

    public async getUrlRedirection(
        url: string,
        proxyUrl: string | null = null
    ): Promise<IRedirectResponse> {
        try {
            let options: ExtendedOptionsOfTextResponseBody = {
                method: "GET",
                timeout: {
                    request: 5000,
                },
                followRedirect: true,
                maxRedirects: 10,
            };

            if (proxyUrl) options.proxyUrl = proxyUrl;

            const response = await gotScraping(url, options);

            if (response.redirectUrls && response.redirectUrls.length > 0) {
                this._redirects = [];
                let currentUrl = url;

                for (const redirectUrl of response.redirectUrls) {
                    this._redirects.push({
                        from: currentUrl,
                        to: redirectUrl.toString(),
                    });
                    currentUrl = redirectUrl.toString();
                }

                this._finalUrl = response.url;
            } else {
                this._finalUrl = url;
            }

            return {
                success: true,
                initial_url: this.getInitialUrl(),
                final_url: this.getFinalUrl() ?? url,
                redirects: this.getRedirects(),
                redirect_chain: this.getRedirectChain(),
                status_code: response.statusCode,
                content_type: response.headers["content-type"] || "",
            };
        } catch (error: any) {
            throw new Error(
                JSON.stringify({
                    success: false,
                    error: error.message,
                    redirects: this.getRedirects(),
                    redirect_chain: this.getRedirectChain(),
                    status_code: error.response?.statusCode || 0,
                })
            );
        }
    }

    public static async getUrlRedirectionPemavor(
        urls: string[],
        internal: string = "no"
    ): Promise<{
        success: boolean;
        data?: any;
        status_code?: number;
        error?: string;
    }> {
        try {
            // Create form data boundary
            const boundary =
                "geckoformboundary" + crypto.randomUUID().replace(/-/g, "");

            // Construct multipart form data
            const formData = [
                `--${boundary}`,
                'Content-Disposition: form-data; name="url"',
                "",
                JSON.stringify(urls),
                `--${boundary}`,
                'Content-Disposition: form-data; name="internal"',
                "",
                internal,
                `--${boundary}--`,
            ].join("\r\n");

            const options: ExtendedOptionsOfTextResponseBody = {
                method: "POST",
                url: "https://europe-west1-pemavor-free-tools.cloudfunctions.net/HttpStatusCodeChecker",
                headers: {
                    "Content-Type": `multipart/form-data; boundary=${boundary}`,
                },
                body: formData,
            };

            const response = await gotScraping(options);
            const responseData = JSON.parse(response.body);

            return {
                success: true,
                data: responseData,
                status_code: response.statusCode,
            };
        } catch (error: any) {
            throw new Error(
                JSON.stringify({
                    success: false,
                    error: error.message,
                    status_code: error.response?.statusCode || 0,
                })
            );
        }
    }
}
