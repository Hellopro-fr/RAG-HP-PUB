import { getHubPage, listHubPages } from '@/data/hub';
import { hubCanonicalPath } from '@/types/hub';
import type { HubPage } from '@/types/hub';

/**
 * Slot parallèle `@head` des pages HUB — émet le JSON-LD côté SERVEUR.
 *
 * Pourquoi ici et pas dans la page : le balisage doit être dans <head> et
 * présent dans le HTML initial (Googlebot ne l'exécute pas depuis un effet
 * client). Le root layout injecte ce slot via sa prop `head`.
 *
 * Types choisis (leçon des pages conseils) : `Article` + `BreadcrumbList` + `FAQPage`.
 * On n'utilise PAS `@type: "Guide"` — non supporté par Google, seul le breadcrumb
 * ressortait sur les pages conseils.
 */
// Aligné sur la route enfant (`app/hub/[hubSlug]`), qui revalide pour rafraîchir
// les rubriques du méga-menu. Ce slot ne fait aucun fetch : le JSON-LD ne dépend
// que de `data/hub/`.
export const revalidate = 86_400; // 24 h

export async function generateStaticParams() {
  return listHubPages().map((page) => ({ hubSlug: `${page.slug}-${page.id}` }));
}

const SITE = 'https://conseils.hellopro.fr';

function plainTitle(page: HubPage): string {
  return page.hero.titleParts.map((part) => part.text).join('');
}

function buildArticle(page: HubPage) {
  const url = `${SITE}${hubCanonicalPath(page)}`;
  // `image` n'est émis que si un visuel est réellement livré : une URL d'image
  // inexistante dans les données structurées est pire que pas d'image du tout.
  const image = page.meta.ogImage ?? page.hero.background?.src;
  return {
    '@context': 'https://schema.org',
    '@type': 'Article',
    headline: plainTitle(page),
    description: page.meta.description,
    mainEntityOfPage: { '@type': 'WebPage', '@id': url },
    ...(image ? { image: image.startsWith('http') ? image : `${SITE}${image}` } : {}),
    author: { '@type': 'Organization', name: 'Hellopro' },
    publisher: {
      '@type': 'Organization',
      name: 'Hellopro',
      logo: { '@type': 'ImageObject', url: `${SITE}/images/hp-logo.svg` },
    },
  };
}

/**
 * BreadcrumbList — n'inclut que les maillons réellement ADRESSABLES.
 *
 * Le breadcrumb de `data/hub/` sert deux usages distincts : le tracking GTM
 * (category1..5, qui a besoin des libellés de rubrique même sans URL) et ce
 * balisage. Un `ListItem` intermédiaire sans `item` déclenche un avertissement
 * Search Console — on filtre donc les items sans href, et on renumérote les
 * positions. Le dernier maillon (page courante) est toujours émis, avec son URL
 * canonique : Google autorise l'omission d'`item` sur le dernier élément, mais
 * l'expliciter est plus robuste.
 */
function buildBreadcrumb(page: HubPage) {
  const lastIndex = page.breadcrumb.length - 1;

  const addressable = page.breadcrumb
    .map((item, index) => {
      if (index === lastIndex) {
        return { name: item.label, item: `${SITE}${hubCanonicalPath(page)}` };
      }
      if (!item.href) return null;
      return {
        name: item.label,
        item: item.href.startsWith('http') ? item.href : `${SITE}${item.href}`,
      };
    })
    .filter((entry): entry is { name: string; item: string } => entry !== null);

  return {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: addressable.map((entry, index) => ({
      '@type': 'ListItem',
      position: index + 1,
      name: entry.name,
      item: entry.item,
    })),
  };
}

function buildFaq(page: HubPage) {
  if (page.faq.items.length === 0) return null;
  return {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    mainEntity: page.faq.items.map((item) => ({
      '@type': 'Question',
      name: item.q,
      acceptedAnswer: { '@type': 'Answer', text: item.a },
    })),
  };
}

/** `<` échappé pour empêcher toute fermeture prématurée du <script>. */
function jsonLd(value: unknown): string {
  return JSON.stringify(value).replace(/</g, '\\u003c');
}

type PageProps = {
  params: Promise<{ hubSlug: string }>;
};

export default async function HubHead({ params }: PageProps) {
  const { hubSlug } = await params;
  const match = hubSlug.match(/^(.+)-(\d+)$/);
  if (!match) return null;

  const page = getHubPage(Number(match[2]));
  // Slug non canonique : la page redirige en 308, inutile d'émettre du balisage.
  if (!page || page.slug !== match[1]) return null;

  const faq = buildFaq(page);

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: jsonLd(buildArticle(page)) }}
      />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: jsonLd(buildBreadcrumb(page)) }}
      />
      {faq && (
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLd(faq) }} />
      )}
    </>
  );
}
