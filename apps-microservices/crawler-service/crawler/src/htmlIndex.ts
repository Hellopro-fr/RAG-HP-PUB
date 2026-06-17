import fs from "fs";
import path from "path";

/**
 * Canonical URL key — MUST match PHP normalize_sfpi_url() and the Python
 * _normalize_url_key() byte-for-byte. Mirrors parse_url/urlparse semantics:
 * keeps path+query RAW (no percent re-encoding), drops scheme/port/userinfo,
 * lowercases host, strips leading www., drops empty query and #fragment,
 * strips a single trailing slash. Inputs without an authority (no "scheme://"
 * and no leading "//") are returned verbatim minus a trailing slash (PHP's
 * no-host branch), so www. is NOT stripped from schemeless strings.
 */
export function normalizeUrl(rawUrl: string): string {
  const s0 = rawUrl.trim().replace(/#.*$/, "");                 // drop fragment
  const hadAuthority = /^[a-zA-Z][a-zA-Z0-9+.\-]*:\/\//.test(s0) || /^\/\//.test(s0);
  if (!hadAuthority) {
    return s0.replace(/\/$/, "");                               // PHP no-host branch
  }
  const s = s0.replace(/^[a-zA-Z][a-zA-Z0-9+.\-]*:\/\//, "").replace(/^\/\//, "");
  const slash = s.indexOf("/");
  let authority = slash === -1 ? s : s.slice(0, slash);
  const rest = slash === -1 ? "" : s.slice(slash);              // raw path(+query)
  authority = authority.replace(/^[^@]*@/, "").replace(/:\d+$/, ""); // drop userinfo + port
  const host = authority.toLowerCase().replace(/^www\./, "");
  const qi = rest.indexOf("?");
  const pathPart = qi === -1 ? rest : rest.slice(0, qi);
  const queryPart = qi === -1 ? "" : rest.slice(qi + 1);
  const query = queryPart !== "" ? "?" + queryPart : "";
  return (host + pathPart + query).replace(/\/$/, "");
}

function indexOneDir(datasetDir: string): Record<string, string> {
  const index: Record<string, string> = {};
  if (!fs.existsSync(datasetDir)) return index;
  for (const file of fs.readdirSync(datasetDir)) {
    if (!file.endsWith(".json") || file === "html_index.json") continue;
    try {
      const json = JSON.parse(fs.readFileSync(path.join(datasetDir, file), "utf-8"));
      if (json && typeof json.url === "string") index[normalizeUrl(json.url)] = file;
    } catch { /* skip unreadable/invalid file (fail-open) */ }
  }
  return index;
}

/** Scan storage/datasets/{domain} (and update-{domain}) → write html_index.json. Never throws. */
export function buildHtmlIndex(storagePath: string, domain: string): void {
  for (const dirName of [domain, `update-${domain}`]) {
    try {
      const datasetDir = path.join(storagePath, "storage", "datasets", dirName);
      if (!fs.existsSync(datasetDir)) continue;
      const index = indexOneDir(datasetDir);
      const out = path.join(datasetDir, "html_index.json");
      fs.writeFileSync(out, JSON.stringify({ version: "1.0", domain, index }));
      const fd = fs.openSync(out, "r"); fs.fsyncSync(fd); fs.closeSync(fd);
    } catch (e) {
      console.error(`buildHtmlIndex failed for ${dirName} (non-fatal):`, e);
    }
  }
}
