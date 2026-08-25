import { describe, it, expect } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import HubHead from '@/app/@head/hub/[hubSlug]/page';
import { listHubPages } from '@/data/hub';
import { hubCanonicalPath } from '@/types/hub';

const SITE = 'https://conseils.hellopro.fr';
const page = listHubPages()[0];
const hubSlug = `${page.slug}-${page.id}`;

/** Rend le slot @head et extrait les blocs JSON-LD parsés. */
async function renderJsonLd(slug: string): Promise<Record<string, unknown>[]> {
  const element = await HubHead({ params: Promise.resolve({ hubSlug: slug }) });
  if (element === null) return [];
  const html = renderToStaticMarkup(element);
  // `[\s\S]` plutôt que `.` + drapeau `s` : le JSON-LD contient des sauts de
  // ligne, mais `s` exige `target: es2018` alors que le projet est en ES2017.
  const matches = [
    ...html.matchAll(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/g),
  ];
  return matches.map((m) => JSON.parse(m[1].replace(/\\u003c/g, '<')));
}

function byType(blocks: Record<string, unknown>[], type: string) {
  return blocks.find((b) => b['@type'] === type);
}

describe('slot @head des pages HUB', () => {
  it('émet Article, BreadcrumbList et FAQPage', async () => {
    const blocks = await renderJsonLd(hubSlug);
    expect(blocks).toHaveLength(3);
    expect(byType(blocks, 'Article')).toBeDefined();
    expect(byType(blocks, 'BreadcrumbList')).toBeDefined();
    expect(byType(blocks, 'FAQPage')).toBeDefined();
  });

  it('n’émet jamais le type Guide, non supporté par Google', async () => {
    const blocks = await renderJsonLd(hubSlug);
    expect(blocks.map((b) => b['@type'])).not.toContain('Guide');
  });

  it('renseigne un headline en texte brut, sans balise', async () => {
    const article = byType(await renderJsonLd(hubSlug), 'Article') as Record<string, string>;
    const expected = page.hero.titleParts.map((p) => p.text).join('');
    expect(article.headline).toBe(expected);
    expect(article.headline).not.toMatch(/[<>]/);
  });

  it('pointe mainEntityOfPage sur l’URL canonique en -projet.html', async () => {
    const article = byType(await renderJsonLd(hubSlug), 'Article') as Record<
      string,
      Record<string, string>
    >;
    expect(article.mainEntityOfPage['@id']).toBe(`${SITE}${hubCanonicalPath(page)}`);
  });

  /**
   * Invariant SEO : un ListItem intermédiaire sans `item` déclenche un
   * avertissement Search Console. Les maillons de catégorie n'ayant pas encore
   * d'URL, ils doivent être ABSENTS du balisage — pas présents sans `item`.
   */
  it('n’émet que des maillons de fil d’ariane adressables', async () => {
    const breadcrumb = byType(await renderJsonLd(hubSlug), 'BreadcrumbList') as {
      itemListElement: { position: number; name: string; item?: string }[];
    };

    const addressableCount =
      page.breadcrumb.filter((b, i) => b.href || i === page.breadcrumb.length - 1).length;
    expect(breadcrumb.itemListElement).toHaveLength(addressableCount);

    for (const entry of breadcrumb.itemListElement) {
      expect(entry.item, `maillon « ${entry.name} » sans item`).toBeTruthy();
    }
  });

  it('numérote les maillons de 1 à n sans trou', async () => {
    const breadcrumb = byType(await renderJsonLd(hubSlug), 'BreadcrumbList') as {
      itemListElement: { position: number }[];
    };
    const positions = breadcrumb.itemListElement.map((e) => e.position);
    expect(positions).toEqual(positions.map((_, i) => i + 1));
  });

  it('termine le fil d’ariane sur la page courante', async () => {
    const breadcrumb = byType(await renderJsonLd(hubSlug), 'BreadcrumbList') as {
      itemListElement: { name: string; item: string }[];
    };
    const last = breadcrumb.itemListElement[breadcrumb.itemListElement.length - 1];
    expect(last.name).toBe(page.breadcrumb[page.breadcrumb.length - 1].label);
    expect(last.item).toBe(`${SITE}${hubCanonicalPath(page)}`);
  });

  it('reprend toutes les questions de la FAQ', async () => {
    const faq = byType(await renderJsonLd(hubSlug), 'FAQPage') as {
      mainEntity: { name: string; acceptedAnswer: { text: string } }[];
    };
    expect(faq.mainEntity).toHaveLength(page.faq.items.length);
    expect(faq.mainEntity[0].name).toBe(page.faq.items[0].q);
    expect(faq.mainEntity[0].acceptedAnswer.text).toBe(page.faq.items[0].a);
  });

  it('retourne null sur un id inconnu', async () => {
    expect(await renderJsonLd('page-inexistante-999999')).toEqual([]);
  });

  it('retourne null sur un slug non canonique (la page redirige en 308)', async () => {
    expect(await renderJsonLd(`mauvais-slug-${page.id}`)).toEqual([]);
  });

  it('retourne null sur une entrée non parsable', async () => {
    expect(await renderJsonLd('sans-id')).toEqual([]);
  });
});
