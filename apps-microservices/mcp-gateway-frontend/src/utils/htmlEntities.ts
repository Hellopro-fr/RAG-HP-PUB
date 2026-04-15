/**
 * HTML-entity encoding utilities.
 *
 * Converts non-ASCII characters (accents, smart quotes, dashes, etc.) to
 * HTML entities so the resulting strings are ASCII-safe for JSON exports,
 * `.env` files, copy-paste, etc.
 *
 * Uses named entities for common French/European chars and falls back to
 * numeric entities (`&#1234;`) for the rest.
 */

const namedEntities: Record<string, string> = {
  '\u00a0': '&nbsp;', '\u00a9': '&copy;', '\u00ae': '&reg;', '\u00b0': '&deg;',
  '\u00ab': '&laquo;', '\u00bb': '&raquo;',
  '\u00e0': '&agrave;', '\u00e2': '&acirc;', '\u00e4': '&auml;', '\u00e1': '&aacute;', '\u00e3': '&atilde;', '\u00e5': '&aring;', '\u00e6': '&aelig;',
  '\u00e7': '&ccedil;',
  '\u00e8': '&egrave;', '\u00e9': '&eacute;', '\u00ea': '&ecirc;', '\u00eb': '&euml;',
  '\u00ec': '&igrave;', '\u00ed': '&iacute;', '\u00ee': '&icirc;', '\u00ef': '&iuml;',
  '\u00f1': '&ntilde;',
  '\u00f2': '&ograve;', '\u00f3': '&oacute;', '\u00f4': '&ocirc;', '\u00f6': '&ouml;', '\u00f5': '&otilde;', '\u00f8': '&oslash;', '\u0153': '&oelig;',
  '\u00f9': '&ugrave;', '\u00fa': '&uacute;', '\u00fb': '&ucirc;', '\u00fc': '&uuml;',
  '\u00ff': '&yuml;',
  '\u00c0': '&Agrave;', '\u00c2': '&Acirc;', '\u00c4': '&Auml;', '\u00c1': '&Aacute;', '\u00c3': '&Atilde;', '\u00c5': '&Aring;', '\u00c6': '&AElig;',
  '\u00c7': '&Ccedil;',
  '\u00c8': '&Egrave;', '\u00c9': '&Eacute;', '\u00ca': '&Ecirc;', '\u00cb': '&Euml;',
  '\u00cc': '&Igrave;', '\u00cd': '&Iacute;', '\u00ce': '&Icirc;', '\u00cf': '&Iuml;',
  '\u00d1': '&Ntilde;',
  '\u00d2': '&Ograve;', '\u00d3': '&Oacute;', '\u00d4': '&Ocirc;', '\u00d6': '&Ouml;', '\u00d5': '&Otilde;', '\u00d8': '&Oslash;', '\u0152': '&OElig;',
  '\u00d9': '&Ugrave;', '\u00da': '&Uacute;', '\u00db': '&Ucirc;', '\u00dc': '&Uuml;',
  '\u00df': '&szlig;',
  '\u2013': '&ndash;', '\u2014': '&mdash;', '\u2026': '&hellip;',
  '\u2018': '&lsquo;', '\u2019': '&rsquo;', '\u201c': '&ldquo;', '\u201d': '&rdquo;',
  '\u20ac': '&euro;',
}

/**
 * Encode non-ASCII chars to HTML entities, but only **outside** HTML tags
 * (tag names, attributes and quoted attribute values stay intact).
 */
export function encodeHtmlEntities(html: string): string {
  if (!html) return html
  let result = ''
  let inTag = false
  for (let i = 0; i < html.length; i++) {
    const ch = html[i]!
    if (ch === '<') {
      inTag = true
      result += ch
      continue
    }
    if (ch === '>' && inTag) {
      inTag = false
      result += ch
      continue
    }
    if (inTag) {
      result += ch
      continue
    }
    const code = ch.charCodeAt(0)
    if (code > 127) {
      result += namedEntities[ch] || `&#${code};`
    } else {
      result += ch
    }
  }
  return result
}

/**
 * Encode all non-ASCII chars in a plain (non-HTML) string. Use for fields
 * like titles, labels, slugs that should not contain raw markup.
 */
export function encodeTextEntities(text: string): string {
  if (!text) return text
  let result = ''
  for (let i = 0; i < text.length; i++) {
    const ch = text[i]!
    const code = ch.charCodeAt(0)
    if (code > 127) {
      result += namedEntities[ch] || `&#${code};`
    } else {
      result += ch
    }
  }
  return result
}

/**
 * Recursively walk an object/array and encode all string values.
 *
 * - Strings that look like HTML (contain `<` followed by a letter) use the
 *   tag-aware encoder.
 * - Other strings use the plain text encoder.
 * - Returns a new object — the input is not mutated.
 *
 * `skipKeys` lets the caller exclude fields like slugs, URLs, icons, colors,
 * filenames, etc. that must remain ASCII-as-typed.
 */
const looksLikeHtml = (s: string) => /<[a-zA-Z\/!]/.test(s)

export function encodeEntitiesDeep<T>(input: T, skipKeys: Set<string> = new Set()): T {
  if (input === null || input === undefined) return input
  if (typeof input === 'string') {
    return (looksLikeHtml(input) ? encodeHtmlEntities(input) : encodeTextEntities(input)) as unknown as T
  }
  if (Array.isArray(input)) {
    return input.map(item => encodeEntitiesDeep(item, skipKeys)) as unknown as T
  }
  if (typeof input === 'object') {
    const out: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(input as Record<string, unknown>)) {
      if (skipKeys.has(k) || typeof v === 'string' && /^https?:\/\//.test(v)) {
        out[k] = v
      } else {
        out[k] = encodeEntitiesDeep(v, skipKeys)
      }
    }
    return out as T
  }
  return input
}
