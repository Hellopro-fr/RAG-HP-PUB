import { transformPhpConseilPage } from './conseil';
import type { PhpConseilResponse } from '@/types/api/page-conseil-php';

const BASE_RESPONSE: PhpConseilResponse = {
  code: 200,
  response: {
    id: 6497,
    titre: 'test Malanto 2',
    url: 'https://conseils.hellopro.fr/test-malanto-2-6497.html',
    seo: {
      meta_title: 'test Malanto 2 en 2026 | Hellopro',
      meta_description: 'Découvrez comment.',
    },
    fil_ariane: [],
    auteur: null,
    date_modification: '2026-05-28 09:21:49',
    id_tag: 1,
    prix: null,
    premier_bloc_texte: 'Sous-titre hero',
    blocs: [],
    schema_guide: {},
    schema_breadcrumb: {},
  },
};

describe('transformPhpConseilPage', () => {
  it('extrait le slug depuis l\'URL canonique', () => {
    const page = transformPhpConseilPage(BASE_RESPONSE);
    expect(page.slug).toBe('test-malanto-2');
  });

  it('mappe id_tag=1 → pageType prix', () => {
    expect(transformPhpConseilPage(BASE_RESPONSE).pageType).toBe('prix');
  });

  it('mappe id_tag=0 → pageType autre', () => {
    const page = transformPhpConseilPage({ ...BASE_RESPONSE, response: { ...BASE_RESPONSE.response, id_tag: 0 } });
    expect(page.pageType).toBe('autre');
  });

  it('mappe id_tag=2 → pageType top', () => {
    const page = transformPhpConseilPage({ ...BASE_RESPONSE, response: { ...BASE_RESPONSE.response, id_tag: 2 } });
    expect(page.pageType).toBe('top');
  });

  it('construit meta depuis seo', () => {
    const page = transformPhpConseilPage(BASE_RESPONSE);
    expect(page.meta.title).toBe('test Malanto 2 en 2026 | Hellopro');
    expect(page.meta.description).toBe('Découvrez comment.');
  });

  it('construit hero depuis titre + premier_bloc_texte', () => {
    const page = transformPhpConseilPage(BASE_RESPONSE);
    expect(page.hero.title).toBe('test Malanto 2');
    expect(page.hero.subtitle).toBe('Sous-titre hero');
  });

  it('n\'inclut pas hero.subtitle si premier_bloc_texte est null', () => {
    const page = transformPhpConseilPage({ ...BASE_RESPONSE, response: { ...BASE_RESPONSE.response, premier_bloc_texte: null } });
    expect(page.hero.subtitle).toBeUndefined();
  });

  it('transforme un bloc faq (type 1) — question/reponse → q/a', () => {
    const response = withBlocs([{ type: 1, ordre: 1, contenu: { items: [{ question: 'Q1?', reponse: 'R1.' }] } }]);
    const page = transformPhpConseilPage(response);
    expect(page.blocks[0].type).toBe('faq');
    expect((page.blocks[0].data as any).items[0]).toEqual({ q: 'Q1?', a: 'R1.' });
  });

  it('transforme un bloc texte (type 2)', () => {
    const page = transformPhpConseilPage(withBlocs([{ id: 1, type: 2, ordre: 1, contenu: { texte: '<p>bonjour</p>' } }]));
    expect(page.blocks[0].type).toBe('texte');
    expect((page.blocks[0].data as any).html).toBe('<p>bonjour</p>');
  });

  it('transforme un bloc texte-image (type 4) avec image', () => {
    const page = transformPhpConseilPage(withBlocs([{
      id: 1, type: 4, ordre: 1,
      contenu: {
        texte: 'du texte',
        image: { path: 'https://hp.fr/img.jpg', title: 'img', legende: '', alternatif: 'alt text', taille: '300x200' },
        estimation: { label: 'Prix', valeur: '100€' },
        cta: { wording: 'Devis', color: '#000', wording_color: '#fff', formulaire_popup: 1, feuille_associe: '', url: '' },
      },
    }]));
    const bloc = page.blocks[0];
    expect(bloc.type).toBe('texte-image');
    expect((bloc.data as any).image.src).toBe('https://hp.fr/img.jpg');
    expect((bloc.data as any).image.alt).toBe('alt text');
    expect((bloc.data as any).estimate).toBe('100€');
    expect((bloc.data as any).imagePosition).toBe('right');
  });

  it('fallback texte-image (type 4) sans image → bloc texte', () => {
    const page = transformPhpConseilPage(withBlocs([{ id: 1, type: 4, ordre: 1, contenu: { texte: 'sans image' } }]));
    expect(page.blocks[0].type).toBe('texte');
  });

  it('transforme un bloc vidéo (type 6)', () => {
    const page = transformPhpConseilPage(withBlocs([{ id: 1, type: 6, ordre: 1, contenu: { video: 'https://youtube.com/watch?v=abc' } }]));
    expect(page.blocks[0].type).toBe('video');
    expect((page.blocks[0].data as any).youtubeUrl).toBe('https://youtube.com/watch?v=abc');
  });

  it('transforme un bloc CTA standalone (type 7)', () => {
    const page = transformPhpConseilPage(withBlocs([{
      id: 1, type: 7, ordre: 1,
      contenu: { cta: { accroche_1: 'Titre CTA', accroche_2: 'Sous-titre', wording: 'Demander', color: '#000', wording_color: '#fff', formulaire_popup: 1, feuille_associe: '', url: '' } },
    }]));
    expect(page.blocks[0].type).toBe('cta');
    expect((page.blocks[0].data as any).title).toBe('Titre CTA');
    expect((page.blocks[0].data as any).ctaLabel).toBe('Demander');
  });

  it('transforme un bloc produits (type 8) en IDs string', () => {
    const page = transformPhpConseilPage(withBlocs([{
      id: 1, type: 8, ordre: 1,
      contenu: { liste_id_produit: [111, 222, 333], produits: [], id_feuille: 2001661 },
    }]));
    expect(page.blocks[0].type).toBe('produits');
    expect((page.blocks[0].data as any).productIds).toEqual(['111', '222', '333']);
  });

  it('transforme un tableau HTML (type 9) en <table>', () => {
    const page = transformPhpConseilPage(withBlocs([{
      id: 1, type: 9, ordre: 1,
      contenu: { table: [['Titre 1', 'Titre 2'], ['col 1', 'col 2']] },
    }]));
    expect(page.blocks[0].type).toBe('tableau-html');
    const html = (page.blocks[0].data as any).html as string;
    expect(html).toContain('<table>');
    expect(html).toContain('<th>Titre 1</th>');
    expect(html).toContain('<td>col 2</td>');
  });

  it('transforme une estimation prix (type 11) en badge', () => {
    const page = transformPhpConseilPage(withBlocs([{ id: 1, type: 11, ordre: 1, contenu: { texte: '200 à 500 €' } }]));
    expect(page.blocks[0].type).toBe('texte');
    expect((page.blocks[0].data as any).estimation.value).toBe('200 à 500 €');
  });

  it('transforme un bloc pros-cons (type 16)', () => {
    const page = transformPhpConseilPage(withBlocs([{
      id: 1, type: 16, ordre: 1,
      contenu: { pros_cons: { label_avantages: 'Avantages', liste_avantages: ['a1', 'a2'], label_inconvenients: 'Inc.', liste_inconvenients: ['i1'] } },
    }]));
    expect(page.blocks[0].type).toBe('pros-cons');
    expect((page.blocks[0].data as any).pros).toEqual(['a1', 'a2']);
    expect((page.blocks[0].data as any).cons).toEqual(['i1']);
  });

  it('trie les blocs par ordre croissant', () => {
    const page = transformPhpConseilPage(withBlocs([
      { id: 3, type: 2, ordre: 3, contenu: { texte: 'c' } },
      { id: 1, type: 2, ordre: 1, contenu: { texte: 'a' } },
      { id: 2, type: 2, ordre: 2, contenu: { texte: 'b' } },
    ]));
    expect(page.blocks.map(b => b.order)).toEqual([1, 2, 3]);
  });

  it('filtre les types inconnus', () => {
    const page = transformPhpConseilPage(withBlocs([{ id: 1, type: 99, ordre: 1, contenu: {} }]));
    expect(page.blocks).toHaveLength(0);
  });

  it('extrait hero.image du premier bloc type 4 avec image', () => {
    const page = transformPhpConseilPage(withBlocs([
      { id: 1, type: 2, ordre: 1, contenu: { texte: 'pas d\'image' } },
      { id: 2, type: 4, ordre: 2, contenu: { texte: 'avec image', image: { path: 'https://hp.fr/hero.jpg', title: '', legende: '', alternatif: '', taille: '' } } },
    ]));
    expect(page.hero.image).toBe('https://hp.fr/hero.jpg');
  });
});

// Helper
function withBlocs(blocs: PhpConseilResponse['response']['blocs']): PhpConseilResponse {
  return { ...BASE_RESPONSE, response: { ...BASE_RESPONSE.response, blocs } };
}
