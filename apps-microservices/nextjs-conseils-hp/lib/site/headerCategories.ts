import {
  HEADER_CATEGORIES_FALLBACK,
  type HeaderCategory,
} from '@/data/site/header-categories';

/**
 * Récupère les rubriques du méga-menu « Tous les produits » depuis la MÊME source
 * que www.hellopro.fr, plutôt que d'en figer une copie.
 *
 * Pourquoi cette source : `mega-menu.php` est le fragment HTML servi au site
 * principal. En le lisant, les pages HUB restent alignées sur le BO sans
 * intervention — un ajout ou un renommage de rubrique se propage tout seul.
 * L'endpoint est public : aucun token requis, contrairement au BFF conseils
 * (`page_conseil.php`) dont le token est absent de l'image Docker au build.
 *
 * Revalidation quotidienne : les rubriques de 1er niveau bougent rarement, et ça
 * évite de dépendre du réseau à chaque rendu.
 *
 * ⚠️ Repli sur `HEADER_CATEGORIES_FALLBACK` si la récupération échoue ou renvoie
 * un résultat manifestement incomplet. Un méga-menu vide, ce n'est pas seulement
 * une gêne de navigation : c'est zéro lien de rubrique crawlable depuis les pages
 * HUB. Mieux vaut un instantané légèrement daté que rien.
 */
const MEGA_MENU_URL =
  process.env.HELLOPRO_MEGA_MENU_URL ??
  'https://www.hellopro.fr/hellopro_fr/include/mega-menu.php';

const REVALIDATE_SECONDS = 86_400; // 24 h

/** En dessous de ce seuil, on considère la réponse cassée (24 rubriques attendues). */
const MIN_EXPECTED = 10;

/**
 * Extrait les rubriques d'un fragment HTML de méga-menu.
 *
 * Volontairement tolérant : on ne s'accroche qu'au motif d'URL
 * `…-<id>-fr-rubrique.html` et au texte du lien. Les classes CSS et la structure
 * interne (`<span>`, wrappers) peuvent changer sans casser le parsing — c'est du
 * HTML qu'on ne maîtrise pas.
 *
 * Exporté pour être testé sans réseau.
 */
export function parseHeaderCategories(html: string): HeaderCategory[] {
  const anchor =
    /<a\b[^>]*href="(https?:\/\/(?:www\.)?hellopro\.fr\/[^"]*?-(\d+)-fr-rubrique\.html)"[^>]*>([\s\S]*?)<\/a>/gi;

  const seen = new Set<number>();
  const categories: HeaderCategory[] = [];

  for (const match of html.matchAll(anchor)) {
    const [, url, rawId, inner] = match;
    const id = Number(rawId);

    // Retire les balises internes, décode le strict nécessaire, normalise l'espace.
    const nom = inner
      .replace(/<[^>]*>/g, ' ')
      .replace(/&nbsp;/gi, ' ')
      .replace(/&amp;/gi, '&')
      .replace(/&#0?39;|&apos;/gi, "'")
      .replace(/&quot;/gi, '"')
      .replace(/\s+/g, ' ')
      .trim();

    if (!nom || seen.has(id)) continue;
    seen.add(id);
    categories.push({ id, nom, url });
  }

  return categories;
}

export async function fetchHeaderCategories(): Promise<HeaderCategory[]> {
  try {
    const response = await fetch(MEGA_MENU_URL, {
      next: { revalidate: REVALIDATE_SECONDS },
    });
    if (!response.ok) {
      console.warn(
        `[headerCategories] HTTP ${response.status} sur ${MEGA_MENU_URL} — repli sur l'instantané.`
      );
      return HEADER_CATEGORIES_FALLBACK;
    }

    const categories = parseHeaderCategories(await response.text());
    if (categories.length < MIN_EXPECTED) {
      console.warn(
        `[headerCategories] ${categories.length} rubrique(s) extraite(s), attendu ≥ ${MIN_EXPECTED} — la structure a probablement changé. Repli sur l'instantané.`
      );
      return HEADER_CATEGORIES_FALLBACK;
    }
    return categories;
  } catch (error) {
    console.warn('[headerCategories] récupération impossible — repli sur l’instantané.', error);
    return HEADER_CATEGORIES_FALLBACK;
  }
}
