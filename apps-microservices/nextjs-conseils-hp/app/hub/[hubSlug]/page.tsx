import type { Metadata } from 'next';
import { permanentRedirect, redirect } from 'next/navigation';
import { HubTemplate } from '@/components/hub/HubTemplate';
import { getHubPage, listHubPages } from '@/data/hub';
import { fetchHeaderCategories } from '@/lib/site/headerCategories';
import { hubCanonicalPath } from '@/types/hub';

/** Page 404 HelloPro — aligné sur app/[slugWithId]/page.tsx. */
const HELLOPRO_404_URL = 'https://www.hellopro.fr/404.php';

/**
 * Pages HUB « projet » — /<slug>-<id>-projet.html
 *
 * Ce segment n'est jamais atteint directement : le rewrite de next.config.js
 * mappe l'URL publique `.html` vers `/hub/<slug>-<id>`. L'URL affichée reste
 * celle en `-projet.html`.
 *
 * Le CONTENU est 100 % statique (`data/hub/`) : pas de BFF, pas de transformer.
 * Seules les rubriques du méga-menu sont récupérées en direct depuis
 * `mega-menu.php` — la même source que www.hellopro.fr — pour éviter de figer une
 * copie qui dériverait du BO.
 *
 * D'où `revalidate` plutôt que `force-static` : les 3 pages sont prérendues au
 * build via `generateStaticParams`, puis revalidées chaque jour, ce qui propage
 * un ajout ou un renommage de rubrique sans redéploiement. `force-static` aurait
 * gelé le fetch indéfiniment (il force le cache et annule la revalidation).
 */
export const revalidate = 86_400; // 24 h

export async function generateStaticParams() {
  return listHubPages().map((page) => ({ hubSlug: `${page.slug}-${page.id}` }));
}

type PageProps = {
  params: Promise<{ hubSlug: string }>;
};

/**
 * 'lancer-elevage-poules-pondeuses-1000' → { slug: 'lancer-elevage-poules-pondeuses', id: 1000 }
 * Le suffixe `-projet.html` a déjà été retiré par le rewrite.
 *
 * Exporté pour être testé unitairement : une erreur ici est silencieuse (elle se
 * traduit par une 404 sur une page valide, sans exception ni log).
 */
export function parseHubSlug(input: string): { slug: string; id: number } | null {
  const match = input.match(/^(.+)-(\d+)$/);
  if (!match) return null;
  return { slug: match[1], id: Number(match[2]) };
}

/** Résout la page depuis le paramètre d'URL, ou null. */
function resolve(hubSlug: string) {
  const parsed = parseHubSlug(hubSlug);
  if (!parsed || parsed.id <= 0) return null;
  const page = getHubPage(parsed.id);
  if (!page) return null;
  return { page, requestedSlug: parsed.slug };
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { hubSlug } = await params;
  const resolved = resolve(hubSlug);
  if (!resolved) return {};
  const { page } = resolved;

  return {
    // `absolute` court-circuite le template "%s | HelloPro" du root layout.
    title: { absolute: page.meta.title },
    description: page.meta.description,
    alternates: {
      canonical: `https://conseils.hellopro.fr${hubCanonicalPath(page)}`,
    },
    openGraph: {
      title: page.meta.title,
      description: page.meta.description,
      images: page.meta.ogImage ? [page.meta.ogImage] : [],
    },
  };
}

export default async function Page({ params }: PageProps) {
  const { hubSlug } = await params;
  const resolved = resolve(hubSlug);

  // Id absent, non numérique ou inconnu du registry → 404 HelloPro.
  // redirect() = 307 : ce sont des URLs structurellement invalides, pas des
  // pages déplacées — on ne veut pas d'un 308 mis en cache.
  if (!resolved) redirect(HELLOPRO_404_URL);

  const { page, requestedSlug } = resolved;

  // Slug non canonique pour cet id → 308 vers l'URL canonique.
  // Même politique que les pages conseils : un seul chemin indexable par page.
  if (requestedSlug !== page.slug) {
    permanentRedirect(hubCanonicalPath(page));
  }

  // Après les redirections : inutile d'appeler le réseau pour une URL invalide.
  const headerCategories = await fetchHeaderCategories();

  return <HubTemplate page={page} headerCategories={headerCategories} />;
}
