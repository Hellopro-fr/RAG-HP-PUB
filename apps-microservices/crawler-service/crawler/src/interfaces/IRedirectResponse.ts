import { IRedirect } from "./IRedirect.js";

export interface IRedirectResponse {
    success: boolean;
    initial_url: string | null;
    final_url: string;
    redirects: Array<IRedirect>;
    redirect_chain: Array<string>;
    status_code: number;
    content_type?: string;
    error?: string;
}