import fs from "fs";
import path from "path";

/** Canonical URL key — MUST match PHP normalize_sfpi_url() byte-for-byte. */
export function normalizeUrl(rawUrl: string): string {
  const noFrag = rawUrl.trim().replace(/#.*$/, "");
  try {
    const u = new URL(noFrag);
    const host = u.hostname.toLowerCase().replace(/^www\./, "");
    const key = `${host}${u.pathname}${u.search}`;
    return key.replace(/\/$/, "");
  } catch {
    return noFrag.replace(/\/$/, "");
  }
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
  try {
    for (const dirName of [domain, `update-${domain}`]) {
      const datasetDir = path.join(storagePath, "storage", "datasets", dirName);
      if (!fs.existsSync(datasetDir)) continue;
      const index = indexOneDir(datasetDir);
      const out = path.join(datasetDir, "html_index.json");
      fs.writeFileSync(out, JSON.stringify({ version: "1.0", domain, index }));
      const fd = fs.openSync(out, "r"); fs.fsyncSync(fd); fs.closeSync(fd);
    }
  } catch (e) {
    console.error("buildHtmlIndex failed (non-fatal):", e);
  }
}
