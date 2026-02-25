/**
 * Corrige les problèmes d'encodage UTF-8 mal interprété en Latin-1 (ISO-8859-1)
 * Exemple: "CaractÃ©ristiques" → "Caractéristiques"
 */

/**
 * Séquences corrompues et leurs remplacements simples (ASCII)
 */
const CORRUPTED_SEQUENCES: [RegExp, string][] = [
  [/â¢/g, '-'],            // Bullet point → tiret
  [/â€™/g, "'"],           // Apostrophe typographique
  [/â€œ/g, '"'],           // Guillemet ouvrant
  [/â€/g, '"'],            // Guillemet fermant
  [/â€"/g, '-'],           // Em dash → tiret
  [/â€"/g, '-'],           // En dash → tiret
  [/â€¦/g, '...'],         // Ellipsis
];

export function fixBrokenEncoding(text: string | null | undefined): string {
  if (!text) return '';

  try {
    // Étape 1: Remplacer les séquences corrompues par des équivalents ASCII
    let result = text;
    for (const [pattern, replacement] of CORRUPTED_SEQUENCES) {
      result = result.replace(pattern, replacement);
    }

    // Étape 2: Décoder UTF-8/Latin-1 mojibake
    const bytes = new Uint8Array(
      [...result].map(char => char.charCodeAt(0) & 0xff)
    );
    result = new TextDecoder('utf-8', { fatal: false }).decode(bytes);

    // Étape 3: Nettoyer les caractères de remplacement
    result = result.replace(/�/g, '');

    return result || text;
  } catch {
    return text;
  }
}
