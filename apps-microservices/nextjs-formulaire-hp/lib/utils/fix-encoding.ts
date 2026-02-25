/**
 * Corrige les problèmes d'encodage UTF-8 mal interprété en Latin-1 (ISO-8859-1)
 * Exemple: "CaractÃ©ristiques" → "Caractéristiques"
 *
 * Ce problème survient quand du texte UTF-8 est stocké/lu comme Latin-1.
 * La solution: réinterpréter les bytes Latin-1 comme UTF-8.
 */
export function fixBrokenEncoding(text: string | null | undefined): string {
  if (!text) return '';

  try {
    // Convertir chaque caractère en son code Latin-1 (byte)
    // puis décoder ces bytes comme UTF-8
    const bytes = new Uint8Array(
      [...text].map(char => char.charCodeAt(0) & 0xff)
    );

    const decoded = new TextDecoder('utf-8', { fatal: false }).decode(bytes);

    // Si le décodage produit des caractères de remplacement (�),
    // le texte original était probablement correct
    if (decoded.includes('\uFFFD')) {
      return text;
    }

    return decoded;
  } catch {
    // En cas d'erreur, retourner le texte original
    return text;
  }
}
