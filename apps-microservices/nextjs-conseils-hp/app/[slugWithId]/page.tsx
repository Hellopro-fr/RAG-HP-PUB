import { Metadata } from 'next';
import { notFound, permanentRedirect } from 'next/navigation';
import { ConseilTemplate } from '@/components/conseil/ConseilTemplate';
import { fetchConseilPage } from '@/lib/api/conseils';

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
  if (!parsed) return {};

  const page = await fetchConseilPage(parsed.id);
  if (!page) return {};

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
  if (!parsed) notFound();

  const page = await fetchConseilPage(parsed.id);
  if (!page) notFound();

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
