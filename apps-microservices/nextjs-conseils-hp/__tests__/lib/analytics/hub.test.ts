import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  pushHubEvent,
  pushHubEventOnce,
  __resetHubEventDedup,
  hubPageContextScript,
  articleIdFromUrl,
} from '@/lib/analytics/hub';

/**
 * Le helper est le seul point d'écriture du dataLayer pour les pages HUB : s'il
 * se trompe, les 21 événements se trompent ensemble. D'où des tests sur la FORME
 * du push plutôt que sur son existence.
 */

type Push = Record<string, unknown>;
const dl = () => (window as unknown as { dataLayer: Push[] }).dataLayer;

beforeEach(() => {
  (window as unknown as { dataLayer: Push[] }).dataLayer = [];
  __resetHubEventDedup();
  // `getHpSessionId` écrit dans sessionStorage : on part d'un état propre pour
  // que les assertions sur `session_id` soient reproductibles.
  sessionStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('pushHubEvent — paramètres communs', () => {
  it('pousse le nom de l’événement et le groupe', () => {
    pushHubEvent('hub_form_view', 'projet');
    expect(dl()).toHaveLength(1);
    expect(dl()[0].event).toBe('hub_form_view');
    expect(dl()[0].hub_group).toBe('projet');
  });

  it('joint toujours session_id et product.category5', () => {
    pushHubEvent('hub_form_start', 'projet');
    expect(dl()[0].session_id).toMatch(/^session_\d+_/);
    // Aucun `product` dans le dataLayer de test → chaîne vide, pas `undefined` :
    // une dimension présente et vide reste analysable, une clé absente non.
    expect(dl()[0]['product.category5']).toBe('');
  });

  it('réutilise le MÊME session_id sur deux événements consécutifs', () => {
    // C'est ce qui permet de recoller questionnaire projet PUIS guide.
    pushHubEvent('hub_form_view', 'projet');
    pushHubEvent('hub_form_view', 'guide');
    expect(dl()[0].session_id).toBe(dl()[1].session_id);
  });

  it('lit hub_page_id et hub_page_slug depuis le dataLayer', () => {
    dl().push({ hub_page_id: 1000, hub_page_slug: 'lancer-elevage-poules-pondeuses' });
    pushHubEvent('hub_form_submission', 'projet');
    const last = dl()[dl().length - 1];
    expect(last.hub_page_id).toBe(1000);
    expect(last.hub_page_slug).toBe('lancer-elevage-poules-pondeuses');
  });

  it('retient le contexte le PLUS RÉCENT si plusieurs sont présents', () => {
    dl().push({ hub_page_id: 1000, hub_page_slug: 'a' });
    dl().push({ hub_page_id: 1002, hub_page_slug: 'c' });
    pushHubEvent('hub_form_view', 'projet');
    expect(dl()[dl().length - 1].hub_page_id).toBe(1002);
  });

  it('n’échoue pas si le contexte de page est absent', () => {
    // Une erreur de tracking ne doit jamais casser la page.
    expect(() => pushHubEvent('hub_form_view', 'projet')).not.toThrow();
    expect(dl()[0].hub_page_id).toBeUndefined();
  });

  it('crée le dataLayer s’il n’existe pas encore', () => {
    delete (window as unknown as { dataLayer?: Push[] }).dataLayer;
    pushHubEvent('hub_form_view', 'projet');
    expect(dl()).toHaveLength(1);
  });
});

describe('pushHubEvent — nettoyage des paramètres', () => {
  it('omet les paramètres undefined et les chaînes vides', () => {
    pushHubEvent('hub_form_step', 'projet', {
      step_name: 'budget',
      step_index: undefined,
      last_step_name: '',
    });
    const push = dl()[0];
    expect(push.step_name).toBe('budget');
    expect('step_index' in push).toBe(false);
    expect('last_step_name' in push).toBe(false);
  });

  it('conserve step_index = 0 (valeur significative, pas une absence)', () => {
    // Piège classique du filtrage par falsy : l'étape 0 est la PREMIÈRE, pas rien.
    pushHubEvent('hub_form_step', 'projet', { step_index: 0 });
    expect(dl()[0].step_index).toBe(0);
  });

  it('transmet les paramètres métier sans les renommer', () => {
    pushHubEvent('hub_form_submission', 'guide', {
      lead_path: 'reconnu',
      user_known_status: 'Known',
      id_page_hub: 2000,
      entry_point: 'popup_scroll',
    });
    expect(dl()[0]).toMatchObject({
      lead_path: 'reconnu',
      user_known_status: 'Known',
      id_page_hub: 2000,
      entry_point: 'popup_scroll',
    });
  });
});

describe('pushHubEvent — cloisonnement du vocabulaire', () => {
  it('n’émet jamais un nom d’événement du funnel devis', () => {
    // Garde-fou de la décision fondatrice du plan (§2) : un lead HUB dans
    // quote_funnel_validation contaminerait la mesure d'impact du template conseils.
    const interdits = [
      'quote_form_funnel',
      'quote_funnel_validation',
      'quote_funnel_validation_v2',
      'Popup_Appel_Offre',
      'eec.add',
      'demarrages_de_devis_all_forms',
    ];
    pushHubEvent('hub_form_submission', 'projet');
    pushHubEvent('hub_guide_download', 'guide', { download_trigger: 'auto' });
    for (const push of dl()) {
      expect(interdits).not.toContain(push.event);
      expect(String(push.event)).toMatch(/^hub_/);
    }
  });

  it('ne laisse fuir aucune clé de donnée personnelle', () => {
    // La liste fermée de HubEventParams l'empêche à la compilation ; ce test
    // verrouille le runtime, au cas où un `as any` s'introduirait un jour.
    pushHubEvent('hub_form_submission', 'projet', {
      answer_label: 'Création d’un premier élevage',
      steps_answered: 4,
    });
    const clefs = Object.keys(dl()[0]);
    for (const interdit of ['email', 'telephone', 'nom', 'prenom', 'code_postal', 'civilite', 'nom_prenom']) {
      expect(clefs).not.toContain(interdit);
    }
  });
});

describe('pushHubEventOnce', () => {
  it('n’émet qu’une fois pour une même clé', () => {
    expect(pushHubEventOnce('hero-view', 'hub_form_view', 'projet')).toBe(true);
    expect(pushHubEventOnce('hero-view', 'hub_form_view', 'projet')).toBe(false);
    expect(dl()).toHaveLength(1);
  });

  it('distingue deux clés différentes', () => {
    pushHubEventOnce('popup', 'hub_guide_popup_view', 'guide');
    pushHubEventOnce('hero-view', 'hub_form_view', 'projet');
    expect(dl()).toHaveLength(2);
  });
});

describe('hubPageContextScript', () => {
  it('produit un push exploitable par getHubPageContext', () => {
    const script = hubPageContextScript(1001, 'creer-food-truck');
    expect(script).toContain('"hub_page_id":1001');
    expect(script).toContain('"hub_page_slug":"creer-food-truck"');

    // Exécution réelle du script, puis lecture par le helper : c'est le contrat
    // entre l'écriture serveur et la lecture client qu'on vérifie ici, pas la
    // chaîne produite.
    new Function(script)();
    pushHubEvent('hub_form_view', 'projet');
    expect(dl()[dl().length - 1].hub_page_id).toBe(1001);
  });

  it('échappe le slug (aucune injection possible depuis les données)', () => {
    const script = hubPageContextScript(1000, 'a"</script><script>alert(1)');
    expect(script).not.toContain('</script>');
  });
});

describe('articleIdFromUrl', () => {
  it('extrait l’id d’une URL de page conseil', () => {
    expect(
      articleIdFromUrl('https://conseils.hellopro.fr/comment-financer-un-batiment-avicole-5270.html'),
    ).toBe(5270);
  });

  it('tolère une query string et un fragment', () => {
    expect(articleIdFromUrl('/slug-5297.html?utm_source=hub')).toBe(5297);
    expect(articleIdFromUrl('/slug-5297.html#bloc')).toBe(5297);
  });

  it('renvoie undefined si l’URL n’a pas la forme attendue', () => {
    // Mieux vaut aucun article_id qu'un id inventé : une dimension fausse est
    // pire qu'une dimension vide, elle se retrouve dans les rapports.
    expect(articleIdFromUrl('https://www.hellopro.fr/')).toBeUndefined();
    expect(articleIdFromUrl('/lancer-elevage-1000-projet.html')).toBeUndefined();
  });
});
