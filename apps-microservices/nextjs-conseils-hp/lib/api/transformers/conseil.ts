import type { ConseilPage, ConseilBlock, ConseilPageType } from '@/types/conseils';
import type { PhpConseilResponse, PhpBloc } from '@/types/api/page-conseil-php';

const PAGE_TYPE_MAP: Record<number, ConseilPageType> = {
  0: 'autre',
  1: 'prix',
  2: 'top',
};

function extractSlugFromUrl(url: string): string {
  const match = url.match(/\/([^/]+)-\d+\.html$/);
  return match ? match[1] : '';
}

function extractHeroImage(blocs: PhpBloc[]): string | undefined {
  for (const bloc of blocs) {
    if (bloc.type === 4 && bloc.contenu.image?.path) {
      return bloc.contenu.image.path;
    }
  }
  return undefined;
}

function tableToHtml(table: string[][]): string {
  if (!table.length) return '';
  const [headerRow, ...dataRows] = table;
  const headers = headerRow.map(cell => `<th>${cell}</th>`).join('');
  const rows = dataRows
    .map(row => `<tr>${row.map(cell => `<td>${cell}</td>`).join('')}</tr>`)
    .join('');
  return `<table><thead><tr>${headers}</tr></thead><tbody>${rows}</tbody></table>`;
}

function transformBloc(phpBloc: PhpBloc): ConseilBlock | null {
  const base = {
    id: String(phpBloc.id ?? `bloc-${phpBloc.ordre}`),
    order: phpBloc.ordre,
  };
  const c = phpBloc.contenu;

  switch (phpBloc.type) {
    case 1: // FAQ
      return {
        ...base,
        type: 'faq',
        data: {
          items: (c.items ?? []).map(i => ({ q: i.question, a: i.reponse })),
        },
      };

    case 2: // Texte simple
      return {
        ...base,
        type: 'texte',
        data: {
          html: c.texte ?? '',
          ...(c.estimation && {
            estimation: { value: c.estimation.valeur, label: c.estimation.label },
          }),
          ...(c.cta && { hasCta: true }),
        },
      };

    case 4: // Texte + Image (estimation + CTA optionnels)
      if (!c.image) {
        return {
          ...base,
          type: 'texte',
          data: {
            html: c.texte ?? '',
            ...(c.estimation && {
              estimation: { value: c.estimation.valeur, label: c.estimation.label },
            }),
          },
        };
      }
      return {
        ...base,
        type: 'texte-image',
        data: {
          html: c.texte ?? '',
          image: {
            src: c.image.path,
            alt: c.image.alternatif || c.image.title || '',
          },
          ...(c.estimation && {
            estimate: c.estimation.valeur,
            estimateLabel: c.estimation.label,
          }),
          ...(c.cta && { ctaLabel: c.cta.wording }),
          imagePosition: 'right' as const,
        },
      };

    case 6: // Vidéo YouTube
      return {
        ...base,
        type: 'video',
        data: { youtubeUrl: c.video ?? '' },
      };

    case 7: // Bloc CTA standalone
      if (!c.cta) return null;
      return {
        ...base,
        type: 'cta',
        data: {
          title: c.cta.accroche_1 ?? '',
          subtitle: c.cta.accroche_2,
          ctaLabel: c.cta.wording || 'Demander un devis',
        },
      };

    case 8: // Liste de produits
      return {
        ...base,
        type: 'produits',
        data: {
          productIds: (c.liste_id_produit ?? []).map(String),
        },
      };

    case 9: // Tableau HTML (2D array → <table>)
      return {
        ...base,
        type: 'tableau-html',
        data: { html: tableToHtml(c.table ?? []) },
      };

    case 11: // Estimation prix (texte avec badge)
      return {
        ...base,
        type: 'texte',
        data: {
          html: '',
          estimation: { value: c.texte ?? '', label: 'Estimation' },
        },
      };

    case 16: // Avantages / Inconvénients
      if (!c.pros_cons) return null;
      return {
        ...base,
        type: 'pros-cons',
        data: {
          pros: c.pros_cons.liste_avantages ?? [],
          cons: c.pros_cons.liste_inconvenients ?? [],
        },
      };

    default:
      console.warn(`[transformBloc] Type PHP inconnu: ${(phpBloc as { type: number }).type}`);
      return null;
  }
}

export function transformPhpConseilPage(raw: PhpConseilResponse): ConseilPage {
  const r = raw.response;
  const heroImage = extractHeroImage(r.blocs ?? []);

  return {
    slug: extractSlugFromUrl(r.url),
    pageType: PAGE_TYPE_MAP[r.id_tag] ?? 'autre',
    meta: {
      title: r.seo.meta_title,
      description: r.seo.meta_description,
    },
    hero: {
      title: r.titre,
      ...(r.premier_bloc_texte ? { subtitle: r.premier_bloc_texte } : {}),
      ...(heroImage ? { image: heroImage } : {}),
    },
    blocks: (r.blocs ?? [])
      .sort((a, b) => a.ordre - b.ordre)
      .map(transformBloc)
      .filter((b): b is ConseilBlock => b !== null),
    ...(r.auteur ? { author: r.auteur as ConseilPage['author'] } : {}),
  };
}
