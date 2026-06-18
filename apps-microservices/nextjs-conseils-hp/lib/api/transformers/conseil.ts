import type { ConseilPage, ConseilBlock, ConseilPageType, LienInterne, AuthorInfo, ConseilAssocie } from '@/types/conseils';
import type { PhpConseilResponse, PhpBloc, PhpImage, PhpCta, PhpAuteur, PhpConseilAssocie } from '@/types/api/page-conseil-php';

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

/** Parse "800x600" → { width: 800, height: 600 }. Retourne {} si invalide. */
function parseTaille(taille?: string): { width?: number; height?: number } {
  if (!taille) return {};
  const [w, h] = taille.split(/[xX]/).map(Number);
  return w > 0 && h > 0 ? { width: w, height: h } : {};
}

function slugify(text: string): string {
  return text
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z0-9\s-]/g, '')
    .trim()
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-');
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

function normalizeSchemaGuide(raw: Record<string, unknown>): Record<string, unknown> {
  const author = raw.author;
  const authorName =
    typeof author === 'string' ? author : (author as Record<string, unknown> | undefined)?.name ?? author;

  const ordered: Record<string, unknown> = {};
  if (raw['@context'] !== undefined) ordered['@context'] = raw['@context'];
  if (raw['@type'] !== undefined)    ordered['@type']    = raw['@type'];
  if (raw.about !== undefined)       ordered.about       = raw.about;
  if (raw.name !== undefined)        ordered.name        = raw.name;
  if (raw.text !== undefined)        ordered.text        = raw.text;
  if (authorName !== undefined)      ordered.author      = authorName;
  if (raw.datePublished !== undefined) ordered.datePublished = raw.datePublished;
  if (raw.image !== undefined)       ordered.image       = raw.image;

  // Champs supplémentaires éventuels non listés ci-dessus
  for (const key of Object.keys(raw)) {
    if (!(key in ordered)) ordered[key] = raw[key];
  }

  return ordered;
}

/**
 * Si un bloc type 11 (estimation prix) est directement suivi d'un bloc type 4 ou 5
 * sans estimation propre, injecte l'estimation dans le bloc suivant et supprime le type 11.
 */
function mergeEstimationIntoNextBloc(blocs: PhpBloc[]): PhpBloc[] {
  const result: PhpBloc[] = [];
  let i = 0;
  while (i < blocs.length) {
    const cur = blocs[i];
    const next = blocs[i + 1];
    if (
      cur.type === 11 &&
      next &&
      (next.type === 4 || next.type === 5) &&
      !next.contenu.estimation?.valeur
    ) {
      result.push({
        ...next,
        contenu: {
          ...next.contenu,
          estimation: { label: 'Estimation de prix', valeur: cur.contenu.texte ?? '' },
        },
      });
      i += 2;
    } else {
      result.push(cur);
      i++;
    }
  }
  return result;
}

/**
 * Mappe un bloc PHP (par `type` numérique du BO) vers un bloc Next.
 *
 * Référence des types BO (contenu.type) :
 *   1  : Titre secondaire / H2
 *   12 : Titre paragraphe / H3
 *   2  : Texte
 *   15 : Bloc résumé
 *   3  : Image
 *   4  : Texte + Image
 *   5  : Image + Texte
 *   13 : Image + Image
 *   6  : Vidéo (lien vidéo)
 *   7  : CTA
 *   8  : Bloc produit
 *   9  : Tableau HTML
 *   11 : Tableau prix (fusionné dans le 4/5 suivant via mergeEstimationIntoNextBloc)
 *   16 : Bloc pour / contre (pros & cons)
 *
 * Tout type non géré ici retourne `null` (bloc ignoré au rendu).
 */
/**
 * Fusionne, UNIQUEMENT juste après un H3 (type 12), une séquence tableau prix (11)
 * + texte (2) + image (3) — dans l'un ou l'autre ordre texte/image — en un seul bloc
 * texte-image (type 4 si texte avant image, type 5 si image avant texte) :
 *
 *   H3 + [11, 2, 3] | [11, 3, 2] → estimation (= texte du 11) + texte-image
 *   + CTA « Demander un devis » vers demande_info.php (form groupée préfiltrée sur la rubrique).
 *
 * On ne fusionne QUE lorsque le tableau prix (11) est présent : un CTA sans estimation
 * de prix ne serait pas cohérent. Le H3 reste affiché ; les blocs après la séquence sont
 * conservés tels quels. CTA omis si la catégorie (info_rubrique.id) est absente.
 */
function isTexteImagePair(x: PhpBloc, y: PhpBloc): boolean {
  return (x.type === 2 && y.type === 3) || (x.type === 3 && y.type === 2);
}

function orderTexteImagePair(
  x: PhpBloc,
  y: PhpBloc,
): { textBloc: PhpBloc; imageBloc: PhpBloc; imageFirst: boolean } {
  return x.type === 3
    ? { imageBloc: x, textBloc: y, imageFirst: true } // image puis texte → type 5
    : { textBloc: x, imageBloc: y, imageFirst: false }; // texte puis image → type 4
}

function buildTexteImageBloc(
  textBloc: PhpBloc,
  imageBloc: PhpBloc,
  imageFirst: boolean,
  priceBloc: PhpBloc | null,
  catId?: string | number,
): PhpBloc {
  const cta: PhpCta | undefined = catId
    ? {
        wording: 'Demander un devis',
        color: '',
        wording_color: '',
        formulaire_popup: 1,
        feuille_associe: '',
        url: `https://www.hellopro.fr/demande_info.php?soc=1&origine=46&f=${catId}`,
      }
    : undefined;

  return {
    ...textBloc, // conserve id/ordre (position préservée)
    type: imageFirst ? 5 : 4, // 3,2 → image+texte ; 2,3 → texte+image
    contenu: {
      texte: textBloc.contenu.texte,
      image: imageBloc.contenu.image,
      ...(priceBloc
        ? { estimation: { label: 'Estimation de prix', valeur: priceBloc.contenu.texte ?? '' } }
        : {}),
      ...(cta ? { cta } : {}),
    },
  };
}

function mergeTexteImageRunsAfterH3(blocs: PhpBloc[], catId?: string | number): PhpBloc[] {
  const result: PhpBloc[] = [];
  let i = 0;
  while (i < blocs.length) {
    const cur = blocs[i];
    result.push(cur);

    if (cur.type === 12) {
      const a = blocs[i + 1];
      const b = blocs[i + 2];
      const c = blocs[i + 3];

      // H3 + tableau prix (11) + (texte/image) — uniquement avec le bloc 11
      if (a?.type === 11 && b && c && isTexteImagePair(b, c)) {
        const { textBloc, imageBloc, imageFirst } = orderTexteImagePair(b, c);
        result.push(buildTexteImageBloc(textBloc, imageBloc, imageFirst, a, catId));
        i += 4;
        continue;
      }
    }
    i++;
  }
  return result;
}

function transformBloc(phpBloc: PhpBloc): ConseilBlock | null {
  const base = {
    id: String(phpBloc.id ?? `bloc-${phpBloc.ordre}`),
    order: phpBloc.ordre,
  };
  const c = phpBloc.contenu;

  switch (phpBloc.type) {
    case 1: // H2 — titre de section (contenu.titre → id + title, contenu.texte → intro)
      if (!c.titre) return null;
      return {
        ...base,
        type: 'h2',
        data: {
          id: slugify(c.titre),
          title: c.titre,
          ...(c.texte ? { intro: c.texte } : {}),
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
            ...parseTaille(c.image.taille),
          },
          ...(c.estimation?.valeur ? {
            estimate: c.estimation.valeur,
            estimateLabel: c.estimation.label,
          } : {}),
          ...(c.cta && {
            ctaLabel: c.cta.wording,
            ...(c.cta.url ? { ctaUrl: c.cta.url } : {}),
          }),
          imagePosition: 'right' as const,
        },
      };

    case 6: // Vidéo YouTube
      return {
        ...base,
        type: 'video',
        data: { url: c.video ?? '' },
      };

    case 13: { // Image + Image — contenu.images[0] et contenu.images[1]
      const imgs = c.images ?? [];
      if (imgs.length < 1) return null;
      const toImg = (img: PhpImage) => ({
        src: img.path,
        alt: img.alternatif || img.title || '',
        ...(img.legende ? { caption: img.legende } : {}),
        ...parseTaille(img.taille),
      });
      return {
        ...base,
        type: 'image-image',
        data: {
          left: toImg(imgs[0]),
          right: toImg(imgs[1] ?? imgs[0]),
        },
      };
    }

    case 3: // Image seule
      if (!c.image?.path) return null;
      return {
        ...base,
        type: 'image',
        data: {
          src: c.image.path,
          alt: c.image.alternatif || c.image.title || '',
          ...(c.image.legende ? { caption: c.image.legende } : {}),
          ...parseTaille(c.image.taille),
        },
      };

    case 5: // Image gauche + Texte droite
      if (!c.image) {
        return { ...base, type: 'texte', data: { html: c.texte ?? '' } };
      }
      return {
        ...base,
        type: 'image-texte',
        data: {
          html: c.texte ?? '',
          image: {
            src: c.image.path,
            alt: c.image.alternatif || c.image.title || '',
            ...parseTaille(c.image.taille),
          },
          ...(c.estimation?.valeur ? { estimate: c.estimation.valeur, estimateLabel: c.estimation.label } : {}),
          ...(c.cta && {
            ctaLabel: c.cta.wording,
            ...(c.cta.url ? { ctaUrl: c.cta.url } : {}),
          }),
          imagePosition: 'left' as const,
        },
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
          ...(c.cta.url ? { ctaUrl: c.cta.url } : {}),
        },
      };

    case 8: // Liste de produits
      return {
        ...base,
        type: 'produits',
        data: {
          productIds: (c.liste_id_produit ?? []).map(String),
          ...(c.titre ? { titre: c.titre } : {}),
          produits: (c.produits ?? []).map((p) => ({
            id: String(p.id_produit),
            name: p.nom_produit,
            image: p.vignette,
            priceHt: p.prix_ht !== null && p.prix_ht !== undefined
              ? (Number(p.prix_ht) || null)
              : null,
            url: p.url,
            brand: p.nom_fabricant ?? '',
            category: String(p.id_rubrique ?? ''),
            variant: p.variant_gtm ?? '',
            srcInteg: (Number(p.affichage_dd_rd) === 1 ? 1 : 0) as 0 | 1,
          })),
        },
      };

    case 13: // Tableau de prix — même structure que type 9
    case 9: { // Tableau (première ligne = en-têtes, cellules potentiellement enveloppées dans <div>)
      const unwrap = (cell: string) => cell.replace(/^<div[^>]*>([\s\S]*)<\/div>$/i, '$1').trim();
      const [headerRow = [], ...dataRows] = c.table ?? [];
      return {
        ...base,
        type: 'tableau-html',
        data: {
          headers: headerRow.map(unwrap),
          rows: dataRows.map(row => row.map(unwrap)),
        },
      };
    }

    case 11: // Tableau prix "single" (non fusionné dans un texte-image) → box estimation
      return {
        ...base,
        type: 'estimation-prix',
        data: {
          label: 'Estimation de prix',
          value: c.texte ?? '',
        },
      };

    case 12: // Titre H3
      if (!c.titre) return null;
      return {
        ...base,
        type: 'h3',
        data: { title: c.titre },
      };

    case 16: // Avantages / Inconvénients
      if (!c.pros_cons) return null;
      return {
        ...base,
        type: 'pros-cons',
        data: {
          pros: c.pros_cons.liste_avantages ?? [],
          cons: c.pros_cons.liste_inconvenients ?? [],
          ...(c.pros_cons.label_avantages ? { labelPros: c.pros_cons.label_avantages } : {}),
          ...(c.pros_cons.label_inconvenients ? { labelCons: c.pros_cons.label_inconvenients } : {}),
        },
      };

    case 17: // FAQ
      if (!c.items?.length) return null;
      return {
        ...base,
        type: 'faq',
        data: {
          items: c.items.map((item) => ({ q: item.question, a: item.reponse })),
        },
      };

    default:
      console.warn(`[transformBloc] Type PHP inconnu: ${(phpBloc as { type: number }).type}`);
      return null;
  }
}

function transformConseilAssocie(a: PhpConseilAssocie): ConseilAssocie {
  return { id: a.id, titre: a.titre, url: a.url, idTag: a.id_tag };
}

function transformAuteur(auteur: PhpAuteur): AuthorInfo {
  return {
    name: auteur.nom_prenom,
    role: auteur.profession,
    bio: auteur.description,
    ...(auteur.url_photo ? { photo: auteur.url_photo } : {}),
  };
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
    blocks: mergeEstimationIntoNextBloc(
      mergeTexteImageRunsAfterH3(
        (r.blocs ?? []).sort((a, b) => a.ordre - b.ordre),
        (r as { info_rubrique?: { id?: number | string } }).info_rubrique?.id,
      ),
    )
      .map(transformBloc)
      .filter((b): b is ConseilBlock => b !== null),
    ...(r.schema_guide && Object.keys(r.schema_guide).length > 0 ? { schemaGuide: normalizeSchemaGuide(r.schema_guide) } : {}),
    ...(r.schema_breadcrumb && Object.keys(r.schema_breadcrumb).length > 0 ? { schemaBreadcrumb: r.schema_breadcrumb } : {}),
    ...(r.auteur ? { author: transformAuteur(r.auteur) } : {}),
    ...(r.temps_lecture ? { tempsLecture: r.temps_lecture } : {}),
    ...(r.pages_conseils_associees?.length
      ? { conseilsAssocies: r.pages_conseils_associees.map(transformConseilAssocie) }
      : {}),
    ...(r.liens_intexts?.length
      ? {
          liensIntexts: r.liens_intexts.map((l): LienInterne => ({
            id: l.id_mli,
            type: l.type as 0 | 1 | 2,
            photo: l.photo,
            titre: l.titre,
            description: l.description,
            url: l.url,
            ...(l.prix ? { prix: l.prix } : {}),
          })),
        }
      : {}),
  };
}
