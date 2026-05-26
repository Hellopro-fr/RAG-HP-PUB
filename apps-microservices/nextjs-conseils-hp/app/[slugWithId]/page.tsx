import { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { ConseilTemplate } from '@/components/conseil/ConseilTemplate';
import { fetchConseilPage } from '@/lib/api/conseils';

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
  const match = input.match(/^(.+)-(\d+)\.html$/);
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
    title: page.meta.title,
    description: page.meta.description,
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

  return <ConseilTemplate page={page} />;
}
