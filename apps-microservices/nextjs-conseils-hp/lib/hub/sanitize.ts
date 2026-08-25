/**
 * Assainit le HTML restreint des données HUB (`bodyHtml`, `descriptionHtml`).
 *
 * Le contenu vient de `data/hub/*.ts` (donc de nous, pas d'un utilisateur), mais
 * la règle `.claude/rules/security.md` interdit tout `dangerouslySetInnerHTML`
 * non assaini — sans exception, parce qu'une donnée « de confiance » aujourd'hui
 * peut venir d'un BO demain.
 *
 * ⚠️ NE PAS utiliser `isomorphic-dompurify` ici. Le paquet est bien déclaré dans
 * `package.json` mais n'est importé par AUCUN fichier du projet, et pour cause :
 * il embarque jsdom, dont webpack casse la résolution de
 * `browser/default-stylesheet.css` (il réécrit `__dirname`). Résultat côté
 * Docker : `ENOENT /app/browser/default-stylesheet.css` pendant le « Collecting
 * page data », et build en échec. Tous les autres sanitizers du service sont
 * écrits à la main pour cette raison (`FaqBlock`, `TableauHtmlBlock`,
 * `EstimationContent`, `Suppliers`, `ConseilTemplate`).
 *
 * Stratégie : allowlist stricte, **zéro attribut conservé**. Chaque balise
 * autorisée est reconstruite à partir de son seul nom, ce qui supprime d'office
 * `href`, `src`, `style`, `on*` — il n'existe donc aucun vecteur d'attribut.
 * Une balise non autorisée est retirée en gardant son texte.
 */
const ALLOWED_TAGS = new Set([
  'strong',
  'em',
  'b',
  'i',
  'br',
  'ul',
  'ol',
  'li',
  'p',
  'span',
  /**
   * `h3` autorisé depuis le 2026-08-07 : le bloc éditorial « Camion ou remorque »
   * de la page food truck se décompose en deux sous-parties nommées. Sans cette
   * entrée, les balises étaient retirées et le texte des sous-titres se fondait
   * dans le paragraphe suivant — la hiérarchie disparaissait en silence.
   *
   * Le titre d'un bloc éditorial étant un `h2`, `h3` est le seul niveau qui s'y
   * emboîte correctement. Ne pas ajouter `h2` : ça permettrait à une donnée de
   * créer une section de même rang que le bloc qui la contient.
   */
  'h3',
]);

/** Balises dont le CONTENU doit disparaître, pas seulement la balise. */
const STRIPPED_WITH_CONTENT = /<(script|style|iframe|object|embed|template|noscript)\b[\s\S]*?<\/\1\s*>/gi;

const HTML_COMMENT = /<!--[\s\S]*?-->/g;

const ANY_TAG = /<\/?([a-zA-Z][a-zA-Z0-9-]*)\b[^>]*>/g;

export function sanitizeHubHtml(html: string): string {
  return html
    .replace(STRIPPED_WITH_CONTENT, '')
    // Les commentaires peuvent masquer du markup lors d'un reparse.
    .replace(HTML_COMMENT, '')
    .replace(ANY_TAG, (tag, rawName: string) => {
      const name = rawName.toLowerCase();
      if (!ALLOWED_TAGS.has(name)) return '';
      const closing = tag.startsWith('</') ? '/' : '';
      // `br` est auto-fermante : on la normalise pour rester valide en JSX/HTML.
      const selfClosing = name === 'br' && !closing ? ' /' : '';
      return `<${closing}${name}${selfClosing}>`;
    });
}
