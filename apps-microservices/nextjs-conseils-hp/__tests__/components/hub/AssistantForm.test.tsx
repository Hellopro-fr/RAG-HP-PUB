import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { AssistantForm, openAssistantDialog } from '@/components/hub/AssistantForm';
import { listHubPages } from '@/data/hub';
import { rememberEmail } from '@/lib/hub/leadEmailCookie';

// PhoneField encapsule react-international-phone (+ son CSS) : on le mocke par un
// input simple qui remonte toujours le pays « France » / indicatif « 33 ».
vi.mock('@/components/hub/PhoneField', () => ({
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
  const fn = vi.fn(async () => {
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

afterEach(() => {
  vi.restoreAllMocks();
  // rememberEmail() pose un cookie que jsdom conserve entre tests : on le purge
  // pour ne pas déclencher le raccourci « e-mail mémorisé » du test suivant.
  document.cookie = 'hub_lead_email=; path=/; max-age=0';
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
   * E-mail mémorisé (cookie) : dès les réponses finies, on saute l'étape e-mail
   * et on lance l'APPEL 1 → 201 → remerciement direct.
   */
  it('saute l’étape e-mail si un e-mail est mémorisé', async () => {
    rememberEmail('connu@exemple.fr');
    const { short, fetchMock } = renderShort([
      { status: 201, body: { statut: 'enregistre', id_demande: 5, contact_connu: 1 } },
    ]);

    await waitFor(() => expect(screen.getByText(short.success.title)).toBeDefined());
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const body = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string);
    expect(body.email).toBe('connu@exemple.fr');
    // L'étape e-mail n'est jamais affichée.
    expect(screen.queryByLabelText(short.contact.label)).toBeNull();
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
