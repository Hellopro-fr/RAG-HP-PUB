import { describe, it, expect, vi, afterEach } from 'vitest';
import { parseHeaderCategories, fetchHeaderCategories } from '@/lib/site/headerCategories';
import { HEADER_CATEGORIES_FALLBACK } from '@/data/site/header-categories';

/**
 * Extrait réel de `mega-menu.php` (structure relevée le 29/07/2026).
 * Le parser ne doit s'accrocher QU'au motif d'URL et au texte du lien : les
 * classes et les wrappers appartiennent à un HTML qu'on ne maîtrise pas.
 */
const REAL_MARKUP = `
<ul class="menu-container d-none">
  <li class="menu-item" data-id-univers="2006625">
    <a class="d-flex justify-content-space-between align-items-center w-100"
       href="https://www.hellopro.fr/travaux-publics-2006625-fr-rubrique.html">
      <span class="sous-menu d-flex align-items-center gp-8 ss-1">Engins et matériels de chantier</span>
    </a>
  </li>
  <li class="menu-item" data-id-univers="1000006">
    <a href="https://www.hellopro.fr/fabrication-et-processus-1000006-fr-rubrique.html">
      <span>Industrie</span>
    </a>
  </li>
</ul>
`;

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('parseHeaderCategories', () => {
  it('extrait id, libellé et URL du balisage réel', () => {
    expect(parseHeaderCategories(REAL_MARKUP)).toEqual([
      {
        id: 2006625,
        nom: 'Engins et matériels de chantier',
        url: 'https://www.hellopro.fr/travaux-publics-2006625-fr-rubrique.html',
      },
      {
        id: 1000006,
        nom: 'Industrie',
        url: 'https://www.hellopro.fr/fabrication-et-processus-1000006-fr-rubrique.html',
      },
    ]);
  });

  it('préserve l’ordre de la source', () => {
    const noms = parseHeaderCategories(REAL_MARKUP).map((c) => c.nom);
    expect(noms).toEqual(['Engins et matériels de chantier', 'Industrie']);
  });

  it('tolère un changement de classes ou de wrappers', () => {
    const html = `<div><a href="https://www.hellopro.fr/securite-1000012-fr-rubrique.html"><i class="x"></i><b>Sécurité</b></a></div>`;
    expect(parseHeaderCategories(html)).toEqual([
      {
        id: 1000012,
        nom: 'Sécurité',
        url: 'https://www.hellopro.fr/securite-1000012-fr-rubrique.html',
      },
    ]);
  });

  it('décode les entités HTML courantes', () => {
    const html = `<a href="https://www.hellopro.fr/x-1-fr-rubrique.html">Nettoyage &amp; entretien&nbsp;d&#39;atelier</a>`;
    expect(parseHeaderCategories(html)[0].nom).toBe("Nettoyage & entretien d'atelier");
  });

  it('déduplique par id', () => {
    const html = REAL_MARKUP + REAL_MARKUP;
    expect(parseHeaderCategories(html)).toHaveLength(2);
  });

  it('ignore les liens qui ne sont pas des rubriques', () => {
    const html = `
      <a href="https://www.hellopro.fr/mon-compte.html">Mon compte</a>
      <a href="https://www.hellopro.fr/un-produit-123-fr-produit.html">Un produit</a>
      <a href="https://www.hellopro.fr/securite-1000012-fr-rubrique.html">Sécurité</a>
    `;
    expect(parseHeaderCategories(html).map((c) => c.nom)).toEqual(['Sécurité']);
  });

  it('ignore un lien au libellé vide', () => {
    const html = `<a href="https://www.hellopro.fr/x-1-fr-rubrique.html"><span></span></a>`;
    expect(parseHeaderCategories(html)).toEqual([]);
  });

  it('renvoie un tableau vide sur du HTML sans rubrique', () => {
    expect(parseHeaderCategories('<html><body>rien</body></html>')).toEqual([]);
  });
});

describe('fetchHeaderCategories', () => {
  /** Construit un HTML avec `count` rubriques distinctes. */
  function markup(count: number) {
    return Array.from(
      { length: count },
      (_, i) =>
        `<a href="https://www.hellopro.fr/rubrique-${1000 + i}-fr-rubrique.html">Rubrique ${i}</a>`
    ).join('');
  }

  it('renvoie les rubriques récupérées quand la réponse est complète', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, text: () => Promise.resolve(markup(24)) })
    );
    const categories = await fetchHeaderCategories();
    expect(categories).toHaveLength(24);
    expect(categories[0].nom).toBe('Rubrique 0');
  });

  /**
   * Un méga-menu vide = zéro lien de rubrique crawlable depuis les pages HUB.
   * Le repli est donc une protection SEO, pas un simple confort.
   */
  it('se replie sur l’instantané si la réponse est incomplète', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, text: () => Promise.resolve(markup(3)) })
    );
    expect(await fetchHeaderCategories()).toBe(HEADER_CATEGORIES_FALLBACK);
  });

  it('se replie sur l’instantané en cas d’erreur HTTP', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 503, text: () => Promise.resolve('') })
    );
    expect(await fetchHeaderCategories()).toBe(HEADER_CATEGORIES_FALLBACK);
  });

  it('se replie sur l’instantané si le réseau échoue', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('ENOTFOUND')));
    expect(await fetchHeaderCategories()).toBe(HEADER_CATEGORIES_FALLBACK);
  });

  it('ne lève jamais', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('boom')));
    await expect(fetchHeaderCategories()).resolves.toBeInstanceOf(Array);
  });
});
