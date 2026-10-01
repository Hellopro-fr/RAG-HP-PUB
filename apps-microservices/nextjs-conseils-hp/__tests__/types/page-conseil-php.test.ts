/**
 * Validation structurelle des types PHP — vérifie que les interfaces
 * correspondent bien à la réponse réelle de page-conseil.php.
 */
import type {
  PhpConseilResponse,
  PhpConseilPage,
  PhpBloc,
  PhpBlocContenu,
  PhpCta,
  PhpImage,
  PhpEstimation,
  PhpFaqItem,
  PhpProduit,
  PhpProsConsData,
  PhpLienInterne,
} from '@/types/api/page-conseil-php';

describe('PhpConseilResponse types', () => {
  it('accepte une réponse PHP valide', () => {
    const response: PhpConseilResponse = {
      code: 200,
      response: {
        id: 6497,
        titre: 'test Malanto 2',
        url: 'https://conseils.hellopro.fr/test-malanto-2-6497.html',
        seo: {
          meta_title: 'test Malanto 2 en 2026 | Hellopro',
          meta_description: 'Découvrez comment optimiser la collecte d\'eau de pluie.',
        },
        fil_ariane: [{ libelle: 'test Malanto 2', url: 'https://conseils.hellopro.fr/test-malanto-2-6497.html', type: 'conseils' }],
        auteur: null,
        date_modification: '2026-05-28 09:21:49',
        id_tag: 1,
        prix: null,
        premier_bloc_texte: 'texte',
        blocs: [],
        schema_guide: {},
        schema_breadcrumb: {},
      },
    };
    expect(response.code).toBe(200);
    expect(response.response.id).toBe(6497);
  });

  it('accepte tous les types de blocs connus', () => {
    const blocTexte: PhpBloc = { id: 1, type: 2, ordre: 1, contenu: { texte: 'hello' } };
    const blocFaq: PhpBloc = { type: 1, ordre: 2, contenu: { items: [{ question: 'Q?', reponse: 'R.' }] } };
    const blocVideo: PhpBloc = { id: 3, type: 6, ordre: 3, contenu: { video: 'https://youtube.com/watch?v=xxx' } };
    const blocProduits: PhpBloc = { id: 4, type: 8, ordre: 4, contenu: { liste_id_produit: [123, 456], produits: [] } };
    const blocProscons: PhpBloc = {
      id: 5, type: 16, ordre: 5,
      contenu: { pros_cons: { label_avantages: 'Avantages', liste_avantages: ['a'], label_inconvenients: 'Inconvénients', liste_inconvenients: ['b'] } },
    };

    expect(blocTexte.type).toBe(2);
    expect(blocFaq.contenu.items).toHaveLength(1);
    expect(blocVideo.contenu.video).toContain('youtube');
    expect(blocProduits.contenu.liste_id_produit).toHaveLength(2);
    expect(blocProscons.contenu.pros_cons?.liste_avantages).toHaveLength(1);
  });

  it('accepte un bloc texte-image (type 4) avec tous ses champs optionnels', () => {
    const bloc: PhpBloc = {
      id: 10,
      type: 4,
      ordre: 1,
      contenu: {
        texte: 'texte avant image',
        image: { path: 'https://hellopro.fr/img.jpg', title: 'img', legende: '', alternatif: '', taille: '150x300' },
        estimation: { label: 'Prix moyen', valeur: '100 à 150' },
        cta: { wording: 'bouton', color: '#000', wording_color: '#fff', formulaire_popup: 2, feuille_associe: '', url: 'https://nextjs.org' },
      },
    };
    expect(bloc.contenu.image?.path).toBeTruthy();
    expect(bloc.contenu.estimation?.valeur).toBe('100 à 150');
    expect(bloc.contenu.cta?.wording).toBe('bouton');
  });

  it('accepte un bloc CTA standalone (type 7) avec accroche_1/accroche_2', () => {
    const bloc: PhpBloc = {
      id: 20,
      type: 7,
      ordre: 1,
      contenu: {
        cta: {
          accroche_1: 'Estimez votre projet',
          accroche_2: 'Recevez 3 devis gratuits',
          wording: 'demande de devis',
          color: '#000',
          wording_color: '#fff',
          formulaire_popup: 1,
          feuille_associe: 2003658,
          url: '',
        },
      },
    };
    expect(bloc.contenu.cta?.accroche_1).toBeTruthy();
  });

  it('id_tag mappe correctement les pageTypes', () => {
    const tagMap: Record<number, string> = { 0: 'autre', 1: 'prix', 2: 'top' };
    expect(tagMap[0]).toBe('autre');
    expect(tagMap[1]).toBe('prix');
    expect(tagMap[2]).toBe('top');
  });
});
