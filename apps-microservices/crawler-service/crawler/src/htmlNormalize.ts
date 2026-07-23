/**
 * Reduce raw page HTML to a content-fingerprinting surface: drop the dynamic
 * noise that makes two same-content pages differ byte-wise (scripts, styles,
 * comments, canonical/og:url metas that echo the ?param), then collapse
 * whitespace. Pure + dependency-free (regex, not a DOM parser) so it stays
 * tsx-testable and cheap over a whole dataset. Conservative: only well-known
 * noise is stripped; visible text is preserved (loss-proof lean).
 */
export const normalizeHtml = (html: string): string => {
  if (!html) return "";
  return html
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, "")
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, "")
    .replace(/<!--[\s\S]*?-->/g, "")
    .replace(/<link\b[^>]*\brel=["']?canonical["']?[^>]*>/gi, "")
    .replace(/<meta\b[^>]*\bproperty=["']og:url["'][^>]*>/gi, "")
    .replace(/\s+/g, " ")
    .trim();
};
