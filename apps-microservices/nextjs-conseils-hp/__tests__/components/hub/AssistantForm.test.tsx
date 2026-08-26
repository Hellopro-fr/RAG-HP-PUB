import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { AssistantForm, openAssistantDialog } from '@/components/hub/AssistantForm';
import { listHubPages } from '@/data/hub';
import { markLeadKnown } from '@/lib/hub/leadEmailCookie';
import { __resetHubEventDedup, type HubEntryPoint } from '@/lib/analytics/hub';

// PhoneField encapsule react-international-phone (+ son CSS) : on le mocke par un
// input simple qui remonte toujours le pays « France » / indicatif « 33 ».
// On mocke le WRAPPER lazy (chargé par AssistantForm) → jsdom n'importe jamais la
// vraie lib ni son chunk `next/dynamic`.
vi.mock('@/components/hub/PhoneFieldLazy', () => ({
  PhoneField: ({
    value,
    ariaLabel,
    onChange,
  }: {
    value: string;
    ariaLabel: string;
    onChange: (phone: string, countryName: string, dialCode: string) => void;
  }) => (
    <input
      aria-label={ariaLabel}
      value={value}
      onChange={(event) => onChange(event.target.value, 'France', '33')}
    />
  ),
}));

const data = listHubPages()[0].assistant;
const ID_PAGE_HUB = listHubPages()[0].id;

type MockResponse = { status: number; body: unknown };

/** File d'attente de réponses `fetch` — la dernière est répétée si épuisée. */
function stubFetch(responses: MockResponse[]) {
  let i = 0;
  // Signature calquée sur `fetch` : sans elle, `vi.fn` infère un tuple d'arguments
  // VIDE, et les assertions qui lisent `mock.calls[0][1]` — l'objet `RequestInit`
  // portant le payload — ne compilent pas.
  const fn = vi.fn(async (...args: Parameters<typeof fetch>) => {
    void args;
    const r = responses[Math.min(i, responses.length - 1)];
    i += 1;
    return {
      status: r.status,
      ok: r.status < 400,
      json: async () => r.body,
    } as Response;
  });
  globalThis.fetch = fn as unknown as typeof fetch;
  return fn;
}

/** Atteint l'étape e-mail rapidement (un seul écran de questions). */
function renderShort(fetchResponses: MockResponse[] = [{ status: 200, body: {} }]) {
  const short = { ...data, steps: [data.steps[0]] };
  const fetchMock = stubFetch(fetchResponses);
  render(<AssistantForm data={short} idPageHub={ID_PAGE_HUB} />);
  fireEvent.click(screen.getByText(short.steps[0].options[0]));
  return { short, fetchMock };
}

/** Lecture du dataLayer — même helper que `__tests__/lib/analytics/hub.test.ts`. */
type Push = Record<string, unknown>;
const dl = () => (window as unknown as { dataLayer: Push[] }).dataLayer ?? [];

beforeEach(() => {
  (window as unknown as { dataLayer: Push[] }).dataLayer = [];
  // `hub_form_view` est dédupliqué au niveau du MODULE : sans ce reset, un seul
  // test le verrait et les suivants croiraient à une régression.
  __resetHubEventDedup();
});

afterEach(() => {
  vi.restoreAllMocks();
  // markLeadKnown() pose un cookie que jsdom conserve entre tests : on le purge.
  document.cookie = 'hub_lead=; path=/; max-age=0';
});

describe('AssistantForm', () => {
  it('rend l’étape 1 inline dans le hero, sans clic', () => {
    render(<AssistantForm data={data} idPageHub={ID_PAGE_HUB} />);
    expect(screen.getByText(data.cardTitle)).toBeDefined();
    expect(screen.getByText(data.steps[0].label)).toBeDefined();
    for (const option of data.steps[0].options) {
      expect(screen.getByText(option)).toBeDefined();
    }
  });

  it('désactive le bouton de démarrage tant qu’aucune réponse n’est choisie', () => {
    render(<AssistantForm data={data} idPageHub={ID_PAGE_HUB} />);
    expect(screen.getByRole('button', { name: new RegExp(data.ctaLabel, 'i') })).toBeDisabled();
  });

  it('ouvre le dialog sur l’étape 2 après un choix unique', async () => {
    render(<AssistantForm data={data} idPageHub={ID_PAGE_HUB} />);
    fireEvent.click(screen.getByText(data.steps[0].options[0]));
    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeDefined();
    });
    expect(screen.getByText(data.steps[1].label)).toBeDefined();
  });

  it('marque l’option choisie comme sélectionnée', () => {
    render(<AssistantForm data={data} idPageHub={ID_PAGE_HUB} />);
    const option = screen.getByText(data.steps[0].options[1]).closest('button');
    fireEvent.click(option!);
    expect(option).toHaveAttribute('aria-pressed', 'true');
  });

  it('s’ouvre sur l’événement window hp:open-assistant-dialog', async () => {
    render(<AssistantForm data={data} idPageHub={ID_PAGE_HUB} />);
    expect(screen.queryByRole('dialog')).toBeNull();
    openAssistantDialog();
    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeDefined();
    });
  });

  it('n’avance pas automatiquement sur une étape à choix multiple', async () => {
    // Le questionnaire réel n'a plus d'étape multi : on en synthétise une pour
    // verrouiller le comportement du composant (multi → pas d'auto-avance).
    const multiStep = {
      id: 'multi-test',
      label: 'Sur quels sujets souhaitez-vous être accompagné ?',
      multi: true,
      options: ['Sujet A', 'Sujet B', 'Sujet C'],
    };
    const multiFirst = { ...data, steps: [multiStep, ...data.steps.slice(1)] };
    render(<AssistantForm data={multiFirst} idPageHub={ID_PAGE_HUB} />);
    fireEvent.click(screen.getByText('Sujet A'));
    // Laisse passer le délai d'auto-avance des choix uniques (180 ms).
    await new Promise((resolve) => setTimeout(resolve, 250));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('refuse une adresse e-mail invalide (bouton désactivé)', async () => {
    const { short } = renderShort();
    await waitFor(() => {
      expect(screen.getByLabelText(short.contact.label)).toBeDefined();
    });
    fireEvent.change(screen.getByLabelText(short.contact.label), {
      target: { value: 'pas-un-email' },
    });
    expect(
      screen.getByRole('button', { name: new RegExp(short.contact.submitLabel, 'i') })
    ).toBeDisabled();
  });

  /**
   * Parcours e-mail inconnu : APPEL 1 → 200 (coordonnées requises) → étape
   * coordonnées → APPEL 2 → 201 → remerciement. Vérifie aussi la forme du
   * payload : appel 1 SANS `coordonnees`, appel 2 AVEC.
   */
  it('déroule e-mail → coordonnées → succès (e-mail inconnu, 2 appels)', async () => {
    const { short, fetchMock } = renderShort([
      { status: 200, body: { statut: 'coordonnees_requises' } },
      { status: 201, body: { statut: 'enregistre', id_demande: 42, contact_connu: 0 } },
    ]);

    await waitFor(() => {
      expect(screen.getByLabelText(short.contact.label)).toBeDefined();
    });
    fireEvent.change(screen.getByLabelText(short.contact.label), {
      target: { value: 'jean@exemple.fr' },
    });
    fireEvent.click(
      screen.getByRole('button', { name: new RegExp(short.contact.submitLabel, 'i') })
    );

    // Étape coordonnées affichée après l'APPEL 1.
    await waitFor(() => {
      expect(screen.getByLabelText(short.coordinates.fields.name)).toBeDefined();
    });

    // APPEL 1 : payload avec e-mail + réponses (libellés), SANS coordonnees.
    const body1 = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string);
    expect(body1.email).toBe('jean@exemple.fr');
    expect(body1.id_page_hub).toBe(ID_PAGE_HUB);
    expect(body1.reponses[0].question).toBe(short.steps[0].label);
    expect(body1.reponses[0].reponses).toContain(short.steps[0].options[0]);
    expect(body1.coordonnees).toBeUndefined();

    fireEvent.click(screen.getByLabelText(short.coordinates.civilityOptions[0])); // Monsieur
    fireEvent.change(screen.getByLabelText(short.coordinates.fields.name), {
      target: { value: 'Jean' },
    });
    fireEvent.change(screen.getByLabelText(short.coordinates.fields.prenom), {
      target: { value: 'Dupont' },
    });
    fireEvent.change(screen.getByLabelText(short.coordinates.fields.phone), {
      target: { value: '+33612345678' },
    });
    fireEvent.change(screen.getByLabelText(short.coordinates.fields.postalCode), {
      target: { value: '44000' },
    });
    // Adresse laissée vide (facultative).
    fireEvent.click(
      screen.getByRole('button', { name: new RegExp(short.coordinates.submitLabel, 'i') })
    );

    await waitFor(() => {
      expect(screen.getByText(short.success.title)).toBeDefined();
    });

    // APPEL 2 : civilité + nom_prenom recombiné, adresse vide (facultative).
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const body2 = JSON.parse((fetchMock.mock.calls[1][1] as RequestInit).body as string);
    expect(body2.coordonnees).toEqual({
      civilite: 'Monsieur',
      nom_prenom: 'Jean_Dupont',
      telephone: '+33612345678',
      code_postal: '44000',
      pays: 'France',
    });
  });

  /** E-mail reconnu : APPEL 1 → 201 direct. L'étape coordonnées n'apparaît jamais. */
  it('va directement au remerciement si l’e-mail est reconnu (1 seul appel)', async () => {
    const { short, fetchMock } = renderShort([
      { status: 201, body: { statut: 'enregistre', id_demande: 7, contact_connu: 1 } },
    ]);

    await waitFor(() => {
      expect(screen.getByLabelText(short.contact.label)).toBeDefined();
    });
    fireEvent.change(screen.getByLabelText(short.contact.label), {
      target: { value: 'connu@exemple.fr' },
    });
    fireEvent.click(
      screen.getByRole('button', { name: new RegExp(short.contact.submitLabel, 'i') })
    );

    await waitFor(() => {
      expect(screen.getByText(short.success.title)).toBeDefined();
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    // Aucun champ coordonnées n'a été présenté.
    expect(screen.queryByLabelText(short.coordinates.fields.name)).toBeNull();
  });

  /**
   * Le questionnaire N'A PAS de raccourci « e-mail mémorisé » : même avec un
   * cookie, l'étape e-mail est TOUJOURS affichée.
   */
  it('affiche toujours l’étape e-mail, même pour un lead connu', async () => {
    markLeadKnown(ID_PAGE_HUB);
    const { short, fetchMock } = renderShort([{ status: 200, body: { statut: 'coordonnees_requises' } }]);

    await waitFor(() => expect(screen.getByLabelText(short.contact.label)).toBeDefined());
    // Aucun appel réseau tant que l'utilisateur n'a pas soumis l'e-mail lui-même.
    expect(fetchMock).not.toHaveBeenCalled();
  });

  /**
   * Convertit en ouvrant le questionnaire depuis l'emplacement demandé, et
   * renvoie l'événement de conversion.
   *
   * ⚠️ Toutes les interactions passent par `within(dialog)`. L'étape 1 est rendue
   * DEUX FOIS quand le dialog est ouvert — une fois dans le bloc inline du hero,
   * une fois dans le dialog — et une requête globale échoue sur « Found multiple
   * elements ». C'est propre à ce composant, dont l'étape d'entrée vit hors du
   * dialog.
   */
  async function convertirDepuis(entryPoint?: HubEntryPoint) {
    const short = { ...data, steps: [data.steps[0]] };
    stubFetch([{ status: 201, body: { statut: 'enregistre', contact_connu: 1 } }]);
    render(<AssistantForm data={short} idPageHub={ID_PAGE_HUB} />);

    openAssistantDialog(entryPoint);
    const dialog = await screen.findByRole('dialog');
    const dans = within(dialog);

    fireEvent.click(dans.getByText(short.steps[0].options[0]));
    await waitFor(() => expect(dans.getByLabelText(short.contact.label)).toBeDefined());
    fireEvent.change(dans.getByLabelText(short.contact.label), {
      target: { value: 'jean@exemple.fr' },
    });
    fireEvent.click(
      dans.getByRole('button', { name: new RegExp(short.contact.submitLabel, 'i') })
    );

    await waitFor(() => {
      expect(dl().some((e) => e.event === 'hub_form_submission')).toBe(true);
    });
    return dl().find((e) => e.event === 'hub_form_submission');
  }

  /**
   * RÉGRESSION (2026-08-25). La conversion du tunnel projet partait SANS
   * `hub_entry_point`, alors que six emplacements ouvrent ce questionnaire :
   * impossible de répondre à « quel CTA amène des projets ? », question pourtant
   * résolue côté guide. La dimension GA4 était donc borgne sur un tunnel.
   */
  it('porte l’emplacement d’ouverture jusqu’à la conversion', async () => {
    const conversion = await convertirDepuis('bloc_thematique');
    expect(conversion?.hub_entry_point).toBe('bloc_thematique');
  });

  /**
   * Sans emplacement fourni, le parcours vient du bloc inline du hero. Le défaut
   * doit donc décrire la réalité, et non une valeur neutre du type `unknown` qui
   * gonflerait artificiellement une catégorie « non attribué ».
   */
  it('retombe sur hero quand aucun emplacement n’est fourni', async () => {
    const conversion = await convertirDepuis();
    expect(conversion?.hub_entry_point).toBe('hero');
  });

  /**
   * RÉGRESSION (constatée en recette le 2026-08-25). L'emplacement fuyait d'un
   * parcours à l'autre : après une ouverture par CTA abandonnée, une conversion
   * partie du bloc inline du hero restait attribuée au CTA précédent.
   *
   * Le dialog s'ouvre de DEUX façons — par événement, qui pose l'emplacement, ou
   * par le hero où `step > 0` suffit et n'émet rien. Seul `reset()` peut donc
   * garantir qu'un nouveau parcours reparte du bon défaut.
   */
  it('ne conserve pas l’emplacement du parcours précédent', async () => {
    const short = { ...data, steps: [data.steps[0]] };
    stubFetch([{ status: 201, body: { statut: 'enregistre', contact_connu: 1 } }]);
    render(<AssistantForm data={short} idPageHub={ID_PAGE_HUB} />);

    // 1. Ouverture par un CTA, puis abandon (fermeture au clavier).
    openAssistantDialog('banner_accompagnement');
    const dialog = await screen.findByRole('dialog');
    fireEvent.keyDown(dialog, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());

    // 2. Parcours depuis le bloc inline du hero — aucun événement d'ouverture.
    fireEvent.click(screen.getByText(short.steps[0].options[0]));
    fireEvent.click(screen.getByRole('button', { name: new RegExp(short.ctaLabel, 'i') }));

    const rouvert = await screen.findByRole('dialog');
    const dans = within(rouvert);
    await waitFor(() => expect(dans.getByLabelText(short.contact.label)).toBeDefined());
    fireEvent.change(dans.getByLabelText(short.contact.label), {
      target: { value: 'jean@exemple.fr' },
    });
    fireEvent.click(
      dans.getByRole('button', { name: new RegExp(short.contact.submitLabel, 'i') })
    );

    await waitFor(() => {
      const conversion = dl().find((e) => e.event === 'hub_form_submission');
      expect(conversion?.hub_entry_point).toBe('hero');
    });
  });

  it('bloque l’étape coordonnées si le téléphone est invalide', async () => {
    const { short } = renderShort([{ status: 200, body: { statut: 'coordonnees_requises' } }]);
    await waitFor(() => expect(screen.getByLabelText(short.contact.label)).toBeDefined());
    fireEvent.change(screen.getByLabelText(short.contact.label), {
      target: { value: 'jean@exemple.fr' },
    });
    fireEvent.click(
      screen.getByRole('button', { name: new RegExp(short.contact.submitLabel, 'i') })
    );
    await waitFor(() => expect(screen.getByLabelText(short.coordinates.fields.name)).toBeDefined());

    fireEvent.change(screen.getByLabelText(short.coordinates.fields.name), {
      target: { value: 'Jean' },
    });
    fireEvent.change(screen.getByLabelText(short.coordinates.fields.prenom), {
      target: { value: 'Dupont' },
    });
    fireEvent.change(screen.getByLabelText(short.coordinates.fields.postalCode), {
      target: { value: '44000' },
    });
    fireEvent.change(screen.getByLabelText(short.coordinates.fields.phone), {
      target: { value: '123' }, // 3 chiffres (mock indicatif « 33 ») → numéro trop court
    });

    expect(
      screen.getByRole('button', { name: new RegExp(short.coordinates.submitLabel, 'i') })
    ).toBeDisabled();
    const alerts = await screen.findAllByRole('alert');
    expect(alerts.some((a) => /téléphone/i.test(a.textContent ?? ''))).toBe(true);
  });

  /** Verrou anti double-clic (§11) : bouton désactivé pendant l'appel en vol. */
  it('désactive le bouton d’envoi pendant l’appel en cours', async () => {
    const short = { ...data, steps: [data.steps[0]] };
    let resolveFetch: (value: unknown) => void = () => {};
    const pending = new Promise((resolve) => {
      resolveFetch = resolve;
    });
    globalThis.fetch = vi.fn(() => pending) as unknown as typeof fetch;

    render(<AssistantForm data={short} idPageHub={ID_PAGE_HUB} />);
    fireEvent.click(screen.getByText(short.steps[0].options[0]));
    await waitFor(() => {
      expect(screen.getByLabelText(short.contact.label)).toBeDefined();
    });
    fireEvent.change(screen.getByLabelText(short.contact.label), {
      target: { value: 'jean@exemple.fr' },
    });
    const submit = screen.getByRole('button', {
      name: new RegExp(short.contact.submitLabel, 'i'),
    });
    fireEvent.click(submit);

    await waitFor(() => expect(submit).toBeDisabled());

    resolveFetch({ status: 200, ok: true, json: async () => ({ statut: 'coordonnees_requises' }) });
  });
});
