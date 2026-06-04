import type { ConseilPage, AoFormQuestion } from '@/types/conseils';
import type { PhpAoQuestion, PhpBloc } from '@/types/api/page-conseil-php';
import { transformPhpConseilPage } from '@/lib/api/transformers/conseil';

const HP_BASE = process.env.HELLOPRO_API_URL ?? 'https://api.hellopro.fr';
const HP_CONSEILS_URL = `${HP_BASE}/api/hp/view/page_conseil.php`;
const API_TOKEN = process.env.CONSEILS_API_TOKEN ?? '';


console.log('[conseils.ts] INIT — HELLOPRO_API_URL:', process.env.HELLOPRO_API_URL ?? '(non défini, défaut utilisé)');
console.log('[conseils.ts] INIT — HP_CONSEILS_URL:', HP_CONSEILS_URL);
console.log('[conseils.ts] INIT — CONSEILS_API_TOKEN:', API_TOKEN ? `défini (${API_TOKEN.slice(0, 6)}...)` : 'VIDE → mode mock');

export async function fetchConseilPage(id: number): Promise<ConseilPage | null> {
  const { getMockPage } = await import('@/data/mocks/index');

  console.log(`[fetchConseilPage] id=${id} — token=${API_TOKEN ? 'présent' : 'absent'}`);

  if (!API_TOKEN) {
    console.log(`[fetchConseilPage] id=${id} — pas de token, retour mock`);
    return getMockPage(id);
  }

  const url = `${HP_CONSEILS_URL}?p=${id}`;
  console.log(`[fetchConseilPage] id=${id} — appel API: ${url}`);

  try {
    const res = await fetch(url, {
      headers: { Authorization: `Bearer ${API_TOKEN}` },
      next: { revalidate: 3600 },
    });

    console.log(`[fetchConseilPage] id=${id} — réponse HTTP: ${res.status} ${res.statusText}`);

    if (!res.ok) {
      console.error(`[fetchConseilPage] id=${id} — API error ${res.status}, fallback mock`);
      return getMockPage(id);
    }

    const text = await res.text();
    console.log(`[fetchConseilPage] id=${id} — body (200 premiers chars): ${text.slice(0, 200)}`);

    // L'API PHP peut retourner du texte de debug SQL avant le JSON
    const jsonMatch = text.match(/\{[\s\S]*\}$/);
    if (!jsonMatch) {
      console.error(`[fetchConseilPage] id=${id} — aucun JSON trouvé dans la réponse, fallback mock`);
      return getMockPage(id);
    }

    const raw = JSON.parse(jsonMatch[0]);
    console.log(`[fetchConseilPage] id=${id} — JSON parsé: id=${raw.id ?? 'absent'}, titre="${raw.titre ?? 'absent'}"`);

    // La réponse est un objet plat {id, titre, seo, blocs, ...} sans wrapper {code, response}
    if (!raw.id || !raw.titre) {
      console.error(`[fetchConseilPage] id=${id} — réponse inattendue (id/titre absents), fallback mock`);
      return getMockPage(id);
    }

    console.log(`[fetchConseilPage] id=${id} — succès, titre: "${raw.titre}"`);

    // formulaire_ao : première question + choix (id, label, image)
    let formulaire_ao: AoFormQuestion | null = null;
    if (Array.isArray(raw.formulaire_ao) && raw.formulaire_ao.length > 0) {
      const q: PhpAoQuestion = raw.formulaire_ao[0];
      formulaire_ao = {
        id: q.id,
        question: q.question,
        avecImage: q.avec_image === 1,
        typeSelection: q.type_selection ?? 1,
        choix: (q.choix ?? []).map((c) => ({
          id: c.id,
          label: c.choix,
          ...(c.vignette ? { image: c.vignette } : {}),
          ...(c.type_input !== undefined ? { typeInput: c.type_input } : {}),
        })),
      };
      console.log(`[fetchConseilPage] id=${id} — formulaire_ao: "${q.question}" (${formulaire_ao.choix.length} choix)`);
    }

    // breadcrumb depuis fil_ariane (home toujours en premier, page courante sans lien)
    const filAriane = (raw.fil_ariane ?? []) as Array<{ libelle: string; url: string }>;
    const breadcrumb = [
      { label: 'Accueil', href: 'https://www.hellopro.fr' },
      ...filAriane.slice(0, -1).map((f) => ({ label: f.libelle, href: f.url })),
      ...(filAriane.length > 0
        ? [{ label: filAriane[filAriane.length - 1].libelle }]
        : [{ label: raw.titre as string }]),
    ];
    console.log(`[fetchConseilPage] id=${id} — breadcrumb: ${breadcrumb.length} items`);

    // prix → hero.estimation (uniquement si min ou max renseignés)
    const prixRaw = raw.prix as { min?: string | number; max?: string | number } | null;
    const estimation = prixRaw && (prixRaw.min || prixRaw.max)
      ? { min: Number(prixRaw.min) || 0, max: Number(prixRaw.max) || 0, unit: '€' }
      : undefined;
    if (estimation) {
      console.log(`[fetchConseilPage] id=${id} — prix: ${estimation.min}–${estimation.max} €`);
    }

    const rawBlocs = (raw.blocs ?? []) as PhpBloc[];
    const mockPage = getMockPage(id);
    const base = mockPage ?? (await import('@/data/mocks/page-prix')).mockPagePrix;

    // Transformer tous les blocs depuis l'API réelle
    const transformed = transformPhpConseilPage({ code: 200, response: raw as never });
    console.log(`[fetchConseilPage] id=${id} — ${transformed.blocks.length} blocs transformés`);

    // bloc type 15 → aside résumé dans le Hero (non géré par le transformer)
    const type15 = rawBlocs.find((b) => b.type === 15);
    let blocks = transformed.blocks;
    if (type15?.contenu?.texte) {
      const html = type15.contenu.texte;
      console.log(`[fetchConseilPage] id=${id} — type 15 aside: HTML brut (${html.length} chars)`);
      blocks = [
        { id: 'resume-api', type: 'resume', order: 0, data: { html, items: [] } },
        ...blocks.filter((b) => b.type !== 'resume'),
      ];
    }

    const infoRubrique = raw.info_rubrique
      ? { id: raw.info_rubrique.id, libelle: raw.info_rubrique.libelle }
      : null;

    return {
      ...base,
      breadcrumb,
      hero: {
        ...base.hero,
        title: raw.titre,
        ...(raw.premier_bloc_texte ? { subtitle: raw.premier_bloc_texte as string } : {}),
        ...(estimation ? { estimation } : {}),
      },
      blocks,
      formulaire_ao,
      infoRubrique,
      liensIntexts: transformed.liensIntexts
    };
  } catch (err) {
    console.error(`[fetchConseilPage] id=${id} — exception:`, err);
    return getMockPage(id);
  }
}
