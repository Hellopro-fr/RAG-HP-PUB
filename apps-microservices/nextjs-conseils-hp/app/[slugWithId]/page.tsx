import { Metadata } from 'next';
import { permanentRedirect, redirect } from 'next/navigation';
import { ConseilTemplate } from '@/components/conseil/ConseilTemplate';
import { fetchConseilPage } from '@/lib/api/conseils';

/**
 * Page 404 HelloPro — cible quand l'URL est invalide (id vide/0) OU quand l'API
 * signale une page introuvable (404). Comportement aligné sur hellopro.fr.
 */
const HELLOPRO_404_URL = 'https://www.hellopro.fr/404.php';

/** Page 410 HelloPro — cible quand l'API signale une page conseil supprimée (410 Gone). */
const HELLOPRO_410_URL = 'https://www.hellopro.fr/410.php';

/**
 * Extrait le chemin (sans domaine) d'une URL canonique complète.
 * Ex : "https://conseils.hellopro.fr/slug-1243.html" → "/slug-1243.html"
 * Retourne null si l'URL est invalide.
 */
function canonicalPathname(url: string): string | null {
  try {
    return new URL(url).pathname;
  } catch {
    return null;
  }
}

export const revalidate = 3600; // ISR 1h

/**
 * Déclare la route comme statiquement générable → active l'ISR à la demande.
 * On ne prérend AUCUNE page au build (les slugs/ID viennent du BO à l'exécution),
 * d'où le tableau vide. Mais sans ce `generateStaticParams`, Next.js rend le
 * segment dynamique [slugWithId] en mode dynamique pur (SSR à chaque requête,
 * Cache-Control: no-store) et IGNORE le `revalidate` ci-dessus.
 * `dynamicParams` reste à true (défaut) → tout slug est rendu à la demande puis caché.
 */
export async function generateStaticParams() {
  return [];
}

type PageProps = {
  params: Promise<{ slugWithId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

/**
 * Pattern URL : <slug>-<id>.html
 * Ex : combien-coute-un-conteneur-1243.html → id = 1243
 * Voir CLAUDE.md §6.1
 */
function parseSlugWithId(input: string): { slug: string; id: number } | null {
  // Le middleware retire .html avant le routing, mais on accepte les deux formes par défense.
  const match = input.match(/^(.+)-(\d+)(?:\.html)?$/);
  if (!match) return null;
  return { slug: match[1], id: Number(match[2]) };
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slugWithId } = await params;
  const parsed = parseSlugWithId(slugWithId);
  if (!parsed || parsed.id <= 0) return {};

  const result = await fetchConseilPage(parsed.id);
  if (!result.ok) return {};
  const page = result.page;

  return {
    // `absolute` court-circuite le template "%s | HelloPro" du layout :
    // on veut exactement le meta_title fourni par l'API.
    title: { absolute: page.meta.title },
    description: page.meta.description,
    ...(page.canonicalUrl ? { alternates: { canonical: page.canonicalUrl } } : {}),
    openGraph: {
      title: page.meta.title,
      description: page.meta.description,
      images: page.meta.ogImage ? [page.meta.ogImage] : [],
    },
  };
}

export default async function Page({ params }: PageProps) {
  const { slugWithId } = await params;
  const parsed = parseSlugWithId(slugWithId);
  // ID vide/absent ou égal à 0 → URL invalide → page 404 HelloPro.
  // redirect() émet un 307 (temporaire) : ce sont des URLs structurellement invalides,
  // pas une page "déplacée définitivement", donc on ne veut pas de 308 mis en cache.
  if (!parsed || parsed.id <= 0) redirect(HELLOPRO_404_URL);

  const result = await fetchConseilPage(parsed.id);
  // Redirections selon le signal de l'API :
  //   - 'gone' (410, supprimée)        → page 410 HelloPro — permanentRedirect (308, suppression définitive)
  //   - 'not-found' (404, introuvable) → page 404 HelloPro — redirect (307, même cible que l'id vide/0)
  // NB: Next.js n'émet pas de 301 littéral depuis un Server Component (308 = équivalent SEO).
  if (!result.ok) {
    if (result.reason === 'gone') permanentRedirect(HELLOPRO_410_URL);
    redirect(HELLOPRO_404_URL);
  }
  const page = result.page;

  // Pages de type "top" (id_tag = 2) : non gérées côté Next.js pour l'instant.
  // On redirige définitivement vers l'URL canonique retournée par l'API
  // (qui pointe vers la version PHP sur conseils.hellopro.fr).
  if (page.pageType === 'top' && page.canonicalUrl) {
    permanentRedirect(page.canonicalUrl);
  }

  // Redirection canonique : si le chemin demandé diffère du chemin canonique,
  // on redirige (301/308) vers le slug canonique — comme la gestion sur hellopro.fr.
  // ⚠️ On compare uniquement le CHEMIN (sans domaine) : en local le domaine diffère
  // toujours (localhost vs conseils.hellopro.fr), ce qui provoquerait une boucle.
  // Le middleware ayant retiré ".html", on compare sur le segment sans extension.
  if (page.canonicalUrl) {
    const canonicalPath = canonicalPathname(page.canonicalUrl);
    if (canonicalPath) {
      const canonicalSlug = canonicalPath.replace(/^\//, '').replace(/\.html$/, '');
      if (canonicalSlug && canonicalSlug !== slugWithId) {
        permanentRedirect(`/${canonicalSlug}.html`);
      }
    }
  }

  return <ConseilTemplate page={page} />;
}
