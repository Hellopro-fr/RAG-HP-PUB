/**
 * Ignored-extension check for UPDATE-mode baseline seeding (main.ts Phase 2).
 *
 * Single source of truth shared with UpdateChecker's eligibility check
 * (class/UpdateChecker.ts imports IGNORED_EXTENSIONS_SET from here instead of
 * keeping its own copy). routes.ts keeps its own separate `ignoredExtensions`
 * list — a different shape (joined string) consumed by Playwright glob/regex
 * patterns for live-page resource blocking, a different concern from
 * seed-time URL filtering.
 */
export const IGNORED_EXTENSIONS_SET = new Set([
    // archives
    "7z", "7zip", "bz2", "rar", "tar", "tar.gz", "xz", "zip",
    // images
    "mng", "pct", "bmp", "gif", "jpg", "jpeg", "png", "pst", "psp", "tif", "tiff",
    "ai", "drw", "dxf", "eps", "ps", "svg", "cdr", "ico", "webp",
    // audio
    "mp3", "wma", "ogg", "wav", "ra", "aac", "mid", "au", "aiff",
    // video
    "3gp", "asf", "asx", "avi", "mov", "mp4", "mpg", "qt", "rm", "swf", "wmv", "m4a", "m4v", "flv", "webm",
    // office suites
    "xls", "xlsx", "ppt", "pptx", "pps", "doc", "docx", "odt", "ods", "odg", "odp",
    // other
    "css", "pdf", "exe", "bin", "rss", "dmg", "iso", "apk", "xml",
]);

/**
 * True when `url`'s path (ignoring query string and fragment) ends with an
 * ignored extension, case-insensitive. Used to stop UPDATE-mode baseline
 * seeding from re-enqueuing inherited image/pdf/doc URLs forever (the
 * inherited-image infinite re-crawl loop).
 *
 * Malformed URLs never throw — they return false so the seed passes through
 * to the existing pipeline unchanged.
 */
export function hasIgnoredExtensionForSeed(url: string): boolean {
    try {
        const pathname = new URL(url).pathname;
        const lastDot = pathname.lastIndexOf(".");
        if (lastDot === -1) return false;
        const ext = pathname.substring(lastDot + 1).toLowerCase();
        return IGNORED_EXTENSIONS_SET.has(ext);
    } catch {
        return false;
    }
}
