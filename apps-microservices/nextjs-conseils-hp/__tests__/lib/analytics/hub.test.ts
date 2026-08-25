import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  pushHubEvent,
  pushHubEventOnce,
  __resetHubEventDedup,
  articleIdFromUrl,
  questionStepName,
} from '@/lib/analytics/hub';
// Module neutre (sans `'use client'`) : c'est ce qui permet à `HubTrackingContext`,
// Server Component, d'appeler cette fonction. Cf. lib/analytics/hubPageContext.ts.
import { hubPageContextScript } from '@/lib/analytics/hubPageContext';

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

  it('lit hub_page_id et hub_page_uri depuis le dataLayer', () => {
    dl().push({
      hub_page_id: 1000,
      hub_page_uri: '/lancer-elevage-poules-pondeuses-1000-projet.html',
    });
    pushHubEvent('hub_form_submission', 'projet');
    const last = dl()[dl().length - 1];
    expect(last.hub_page_id).toBe(1000);
    expect(last.hub_page_uri).toBe('/lancer-elevage-poules-pondeuses-1000-projet.html');
  });

  it('retient le contexte le PLUS RÉCENT si plusieurs sont présents', () => {
    dl().push({ hub_page_id: 1000, hub_page_uri: '/a-1000-projet.html' });
    dl().push({ hub_page_id: 1002, hub_page_uri: '/c-1002-projet.html' });
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
  it('pousse TOUTES les clés connues, à undefined si non fournies', () => {
    // C'est ce qui empêche une valeur de fuiter d'un événement au suivant : GTM
    // fusionne les pushes, une clé absente conserve la valeur précédente.
    pushHubEvent('hub_form_step', 'projet', {
      step_name: '2eme-question',
      last_step_name: '',
    });
    const push = dl()[0];
    expect(push.step_name).toBe('2eme-question');
    expect('step_index' in push).toBe(true);
    expect(push.step_index).toBeUndefined();
    // Chaîne vide traitée comme une absence, pour la même raison.
    expect(push.last_step_name).toBeUndefined();
  });

  it('efface la valeur d’un paramètre laissé par l’événement précédent', () => {
    // Scénario constaté en recette : questionnaire projet complété (step_name =
    // "delai", answer_label, steps_answered), puis clic sur un CTA guide. Sans
    // cette remise à zéro, GTM attachait encore les valeurs du projet à
    // l'événement du guide.
    pushHubEvent('hub_form_step', 'projet', {
      step_name: '4eme-question',
      step_id: 'delai',
      answer_label: 'Création d’un premier élevage',
      steps_answered: 4,
    });
    pushHubEvent('hub_guide_download', 'guide', { download_trigger: 'auto' });

    const second = dl()[1];
    expect(second.download_trigger).toBe('auto');
    for (const key of ['step_name', 'step_id', 'answer_label', 'steps_answered']) {
      expect(second[key]).toBeUndefined();
    }
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
    const script = hubPageContextScript(1001, '/creer-food-truck-1001-projet.html');
    expect(script).toContain('"hub_page_id":1001');
    expect(script).toContain('"hub_page_uri":"/creer-food-truck-1001-projet.html"');

    // Exécution réelle du script, puis lecture par le helper : c'est le contrat
    // entre l'écriture serveur et la lecture client qu'on vérifie ici, pas la
    // chaîne produite.
    new Function(script)();
    pushHubEvent('hub_form_view', 'projet');
    const last = dl()[dl().length - 1];
    expect(last.hub_page_id).toBe(1001);
    expect(last.hub_page_uri).toBe('/creer-food-truck-1001-projet.html');
  });

  it('échappe l’URI (aucune injection possible depuis les données)', () => {
    const script = hubPageContextScript(1000, 'a"</script><script>alert(1)');
    expect(script).not.toContain('</script>');
  });
});

describe('questionStepName', () => {
  it('produit des libellés ordinaux génériques', () => {
    expect(questionStepName(0)).toBe('1ere-question');
    expect(questionStepName(1)).toBe('2eme-question');
    expect(questionStepName(3)).toBe('4eme-question');
  });

  it('reste identique quelle que soit la page HUB', () => {
    // C'est TOUT l'intérêt : les 3 verticales n'ont pas les mêmes questions, mais
    // leurs entonnoirs doivent se superposer dans un seul rapport GA4. Un id
    // métier (`budget`, `volume`) rendrait la comparaison impossible.
    expect(questionStepName(1)).toBe('2eme-question');
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
