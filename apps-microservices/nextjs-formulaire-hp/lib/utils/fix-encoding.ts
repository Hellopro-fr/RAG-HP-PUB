/**
 * Corrige les problèmes d'encodage UTF-8 mal interprété en Latin-1 (ISO-8859-1)
 * Exemple: "CaractÃ©ristiques" → "Caractéristiques"
 *
 * Approche : remplacement direct des séquences mojibake connues
 * sans toucher aux caractères déjà corrects.
 */

/**
 * Map des séquences mojibake → caractères corrects
 * UTF-8 lu comme Latin-1 (ISO-8859-1)
 */
const MOJIBAKE_REPLACEMENTS: [string | RegExp, string][] = [
  // Lettres accentuées minuscules
  ['Ã©', 'é'],
  ['Ã¨', 'è'],
  ['Ãª', 'ê'],
  ['Ã«', 'ë'],
  ['Ã ', 'à'],
  ['Ã¢', 'â'],
  ['Ã¤', 'ä'],
  ['Ã´', 'ô'],
  ['Ã¶', 'ö'],
  ['Ã®', 'î'],
  ['Ã¯', 'ï'],
  ['Ã¹', 'ù'],
  ['Ã»', 'û'],
  ['Ã¼', 'ü'],
  ['Ã§', 'ç'],
  ['Ã±', 'ñ'],
  ['Å"', 'œ'],

  // Lettres accentuées majuscules
  ['Ã‰', 'É'],
  ['Ã€', 'À'],
  ['Ã‚', 'Â'],
  ['Ã"', 'Ô'],
  ['Ã‡', 'Ç'],
  ['Ãˆ', 'È'],
  ['ÃŠ', 'Ê'],
  ['Ã™', 'Ù'],
  ['Ã›', 'Û'],
  ['Ã', 'Í'],   // Í seul

  // Ponctuation et symboles
  ['â€™', "'"],    // Apostrophe typographique '
  ['â€˜', "'"],    // Apostrophe ouvrante '
  ['â€œ', '"'],    // Guillemet ouvrant "
  ['â€', '"'],     // Guillemet fermant "
  ['â€"', '–'],    // En dash –
  ['â€"', '—'],    // Em dash —
  ['â€¦', '...'],  // Ellipsis …
  ['â€¢', '•'],    // Bullet •
  ['â¢', '-'],     // Bullet corrompu → tiret
  ['Â°', '°'],     // Degré °
  ['Â«', '«'],     // Guillemet français «
  ['Â»', '»'],     // Guillemet français »
  ['Â ', ' '],     // Espace insécable corrompu
  ['â‚¬', '€'],    // Euro €
];

export function fixBrokenEncoding(text: string | null | undefined): string {
  if (!text) return '';

  let result = text;

  // Remplacer chaque séquence mojibake par son équivalent correct
  for (const [mojibake, correct] of MOJIBAKE_REPLACEMENTS) {
    if (typeof mojibake === 'string') {
      // Remplacement global de la string
      result = result.split(mojibake).join(correct);
    } else {
      result = result.replace(mojibake, correct);
    }
  }

  return result;
}
