import { RedirectTracker } from "./RedirectTracker.js";

export class DomainFR {
    private _homepage: string;
    private _forcedMethod: string | null;
    private tracker: RedirectTracker;

    constructor(homepage: string, forcedMethod: string | null = null) {
        this._homepage = homepage;
        this._forcedMethod = forcedMethod;
        this.tracker = new RedirectTracker();
    }

    public set homepage(v: string) {
        this._homepage = v;
    }

    private detectLanguage(content: string): any {
        // Base regex for handling conditional comments and HTML tag
        // (?:<!--\[if[^>]*> - Optional IE conditional comment start
        // (?:<!--)?[^<]*    - Optional comment and content
        // <html[^>]*>       - HTML tag with attributes
        // (?:(?:<!--)?<!\[endif\]-->)? - Optional IE conditional comment end
        // (?:<!--\[if[^>]*!\(?ie\)?\]><!-->) - IE specific conditional
        const regexLang = `(?:<!--\\[if[^>]*>(?:<!--)?[^<]*<html[^>]*>(?:(?:<!--)?<!\\[endif\\]-->)?[^<]*)*(?:<!--\\[if[^>]*!\\(?ie\\)?\\]><!-->)`;

        // Match lang attribute in HTML tag
        // \s*<html - HTML tag with optional whitespace
        // [^>]*\slang= - Any attributes followed by lang=
        // ["']?([a-zA-Z-]+)["']? - Language code in quotes (optional)
        const regexHtml = `\\s*<html[^>]*\\s(?:xml:)?lang=["']?([a-zA-Z-]+)["']?`;

        // Combine conditional comments and HTML lang patterns
        let regexLangHtml = new RegExp(`${regexLang}${regexHtml}`, "i");

        // Match Open Graph locale meta tag
        // <meta property="og:locale" content="language_code">
        const regexMetaLang =
            /<meta[^>]*\sproperty=["']og:locale["'][^>]*content=["']([a-zA-Z-]+)["']/i;
        
        // Match meta tag with the property name="language"
        // <meta property="og:locale" content="language_code">
        const regexMetaLanguage =
            /<meta[^>]*\sname=["']LANGUAGE["'][^>]*content=["']([a-zA-Z-]+)["']/i;

        // Match HTTP-EQUIV content language meta tag
        // <meta http-equiv="content-language" content="language_code">
        const regexHttpEquiv =
            /<meta[^>]*\shttp-equiv=["']content-language["'][^>]*content=["']([a-zA-Z-]+)["']/i;

        // Priority 1: Check HTML tag with conditional comments
        let matchHtml = content.match(regexLangHtml);
        if (matchHtml)
            return {
                method: "langHtml",
                value: matchHtml[1].split("-")[0], // Extract primary language code. Ex: "fr-FR" → "fr"
            };

        // Priority 2: Check HTML tag without conditional comments
        regexLangHtml = new RegExp(`${regexLang}?${regexHtml}`, "i");
        matchHtml = content.match(regexLangHtml);
        if (matchHtml)
            return {
                method: "langHtml",
                value: matchHtml[1].split("-")[0], // ex: "fr-FR" → "fr"
            };

        // Priority 3: Check Open Graph locale meta tag
        const matchMeta = content.match(regexMetaLang);
        if (matchMeta)
            return {
                method: "matchMeta",
                value: matchMeta[1].split("-")[0],
            };
        
        // Priority 3.1: Check meta tag with property with="language"
        const matchMetaLanguage = content.match(regexMetaLanguage);
        if (matchMetaLanguage)
            return {
                method: "matchMeta",
                value: matchMetaLanguage[1].split("-")[0],
            };

        // Priority 4: Check HTTP-EQUIV content language
        const matchHttpEquiv = content.match(regexHttpEquiv);
        if (matchHttpEquiv)
            return {
                method: "matchHttpEquiv",
                value: matchHttpEquiv[1].split("-")[0],
            };

        return false;
    }

    public static async checkUrl(
        url: string,
        trackRedirect: boolean = true,
        proxyUrl: string | null = null
    ): Promise<any> {
        try {
            let result: any = false;
            const urlParts = new URL(url);

            if (!urlParts.hostname) {
                return {
                    ok: false,
                    method: "invalid_host",
                };
            }

            const protocol = urlParts.protocol;
            const hostname = urlParts.hostname;
            const path = urlParts.pathname;
            const queryParams = urlParts.searchParams;

            const instance = new this(url);

            // Vérifier le TLD .fr et les sous-domaines indiquant le français
            if (
                hostname.endsWith(".fr") ||
                /^({fr|france|french|francais|français})\./i.test(hostname)
            ) {
                if (!trackRedirect)
                    return {
                        ok: true,
                        method: "direct_match",
                    };

                const newUrl = `${protocol}//${hostname}`;
                const redirections = await instance.handleRedirections(
                    newUrl,
                    url,
                    "",
                    proxyUrl
                );
                if (redirections["ok"])
                    return await instance.recheckUrl(url, redirections["url"]);

                return redirections;
            } // Vérifier les segments de chemin
            else if (
                /\/(fr|france|french|francais|français|fr-fr|fr_fr)(\/|$)/i.test(
                    path
                )
            ) {
                return {
                    ok: true,
                    method: "pattern_match_path",
                };
            } else {
                // Vérifier les paramètres d'URL
                const langParams = ["lang", "locale", "language"];

                langParams.forEach((langParam) => {
                    if (
                        queryParams.get(langParam) &&
                        /^(fr|france|french|francais|français)(-[A-Z]{2})?$/i.test(
                            String(queryParams.get(langParam))
                        )
                    ) {
                        result = {
                            ok: true,
                            method: "pattern_match_query",
                        };
                    }
                });
            }

            return result;
        } catch (error) {
            return {
                ok: false,
                method: "invalid_url",
                error,
            };
        }
    }

    private async recheckUrl(
        originalUrl: string,
        newUrl: string
    ): Promise<any> {
        if (originalUrl === newUrl)
            return {
                ok: true,
                method: "no_redirect",
                url: originalUrl,
            };

        const recheck = await DomainFR.checkUrl(newUrl, false);
        recheck["original_url"] = originalUrl;
        recheck["url"] = newUrl;

        return recheck;
    }

    private async handleRedirections(
        urlToTrack: string,
        url: string | null = null,
        targetContentType: string = "",
        proxyUrl: string | null = null
    ): Promise<any> {
        if (!url) url = urlToTrack;

        try {
            this.tracker.redirects = [];
            this.tracker.finalUrl = null;

            const response = await this.tracker.getUrlRedirection(urlToTrack, proxyUrl);
            const contentType = response.content_type;

            if (response.success && response.status_code === 200) {
                const result = {
                    ok: true,
                    url: response.final_url,
                };

                if (targetContentType) {
                    if (contentType?.includes(targetContentType)) {
                        return result;
                    }
                } else {
                    return result;
                }
            } else {
                throw new Error(
                    JSON.stringify({
                        ok: false,
                        method: "redirect_failed",
                        url,
                        response,
                    })
                );
            }
        } catch (error: any) {
            console.error(
                `Error redirecting with got-scraping for ${url}\n`,
                error
            );

            try {
                const response = await RedirectTracker.getUrlRedirectionPemavor(
                    [urlToTrack]
                );
                const datas = response["data"]["Data"];

                for (const data in datas) {
                    const currentData = datas[data];
                    const value = currentData[currentData.length - 1];
                    const contentType = value?.headers?.["Content-Type"];

                    if (value?.["status_code"] === 200) {
                        if (targetContentType) {
                            if (contentType?.includes(targetContentType)) {
                                return {
                                    ok: true,
                                    url: value["url"],
                                };
                            } else {
                                return {
                                    ok: false,
                                    url: value["url"],
                                    status_code: value["status_code"],
                                    content_type: contentType,
                                };
                            }
                        } else {
                            return {
                                ok: true,
                                url: value["url"],
                            };
                        }
                    } else {
                        return {
                            ok: false,
                            url: value["url"],
                            status_code: value["status_code"],
                        };
                    }
                }
            } catch (pemavorError: any) {
                console.error(
                    `Error redirecting with Pemavor for ${url}\n`,
                    pemavorError
                );
            }

            return {
                ok: false,
                method: "all_redirections_failed",
                url,
            };
        }
    }

    private buildResult(url: string, method: string, isFrench: boolean): any {
        return {
            url,
            method,
            ok: isFrench,
        };
    }

    public async checkPageIfFrench(content: string, isCheckUrl: boolean = true): Promise<any> {
        const url = this._homepage;

        if (!url || !content) return this.buildResult(url, "Info_vide", false);

        if (isCheckUrl) {
            const checkUrl = await DomainFR.checkUrl(url, false);
    
            if (checkUrl["ok"]) return this.buildResult(url, "checkUrl", true);
        }

        // If forced method is set, check it first
        if (this._forcedMethod) {
            const language = this.detectLanguage(content);
            
            // If we find a language and it's French using the forced method
            if (language && language.method === this._forcedMethod && language.value === "fr") {
                return this.buildResult(url, this._forcedMethod, true);
            }
            
            // If forced method didn't work, return false
            return this.buildResult(url, "Check_nok_forced", false);
        }

        const language = this.detectLanguage(content);

        if (!language) return this.buildResult(url, "Check_nok_v1", false);

        if (language && language?.method && language?.value === "fr")
            return this.buildResult(url, language["method"], true);

        return this.buildResult(url, "Check_nok_v2", false);
    }
}
