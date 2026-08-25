import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { GuideDownloadDialog, openGuideDialog } from '@/components/hub/GuideDownloadDialog';
import { listHubPages, guideIdPageHub } from '@/data/hub';
import { markLeadKnown } from '@/lib/hub/leadEmailCookie';

// PhoneField encapsule react-international-phone (+ CSS) : on le mocke par un input
// simple qui remonte toujours le pays « France » / indicatif « 33 ».
// On mocke le WRAPPER lazy (chargé par GuideSteps) → jsdom n'importe jamais la lib.
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

const data = listHubPages()[0].guideDialog;
const ID_PAGE_HUB = guideIdPageHub(listHubPages()[0].id);
/**
 * Id du PROJET — portée du drapeau « déjà converti », distinct de l'id du TUNNEL
 * guide envoyé à l'API. Cf. `lib/hub/leadEmailCookie.ts`.
 */
const PAGE_ID = listHubPages()[0].id;

type MockResponse = { status: number; body: unknown };

function stubFetch(responses: MockResponse[]) {
  let i = 0;
  // Signature calquée sur `fetch` — cf. AssistantForm.test.tsx : sans elle,
  // `mock.calls[0][1]` ne compile pas (tuple d'arguments vide).
  const fn = vi.fn(async (...args: Parameters<typeof fetch>) => {
    void args;
    const r = responses[Math.min(i, responses.length - 1)];
    i += 1;
    return { status: r.status, ok: r.status < 400, json: async () => r.body } as Response;
  });
  globalThis.fetch = fn as unknown as typeof fetch;
  return fn;
}

/** Ouvre le dialog et attend son rendu (Radix le monte dans un portail). */
async function open() {
  openGuideDialog();
  await waitFor(() => expect(screen.getByRole('dialog')).toBeDefined());
}

/** Valide l'étape e-mail puis clique « Continuer ». */
function submitEmailStep() {
  fireEvent.change(screen.getByLabelText(data.fields.email), {
    target: { value: 'jean@exemple.fr' },
  });
  fireEvent.click(screen.getByRole('button', { name: new RegExp(data.emailSubmitLabel, 'i') }));
}

afterEach(() => {
  vi.restoreAllMocks();
  // markLeadKnown() pose un cookie que jsdom conserve entre tests : on le purge
  // pour ne pas déclencher le raccourci « lead connu » du test suivant.
  document.cookie = 'hub_lead=; path=/; max-age=0';
});

describe('GuideDownloadDialog', () => {
  it('reste fermé au montage', () => {
    stubFetch([{ status: 200, body: {} }]);
    render(<GuideDownloadDialog data={data} idPageHub={ID_PAGE_HUB} pageId={PAGE_ID} />);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('s’ouvre sur l’événement et démarre par l’étape e-mail seule', async () => {
    stubFetch([{ status: 200, body: {} }]);
    render(<GuideDownloadDialog data={data} idPageHub={ID_PAGE_HUB} pageId={PAGE_ID} />);
    await open();
    expect(screen.getByLabelText(data.fields.email)).toBeDefined();
    expect(screen.queryByLabelText(data.fields.name)).toBeNull();
  });

  it('refuse un e-mail invalide sans appel réseau', async () => {
    const fetchMock = stubFetch([{ status: 200, body: {} }]);
    render(<GuideDownloadDialog data={data} idPageHub={ID_PAGE_HUB} pageId={PAGE_ID} />);
    await open();
    fireEvent.change(screen.getByLabelText(data.fields.email), {
      target: { value: 'pas-un-email' },
    });
    fireEvent.click(screen.getByRole('button', { name: new RegExp(data.emailSubmitLabel, 'i') }));

    const alerts = await screen.findAllByRole('alert');
    expect(alerts.some((a) => /adresse e-mail valide/i.test(a.textContent ?? ''))).toBe(true);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  /** E-mail inconnu : APPEL 1 → 200 → coordonnées → APPEL 2 → 201 → téléchargement. */
  it('déroule e-mail → coordonnées → téléchargement (e-mail inconnu, 2 appels)', async () => {
    const fetchMock = stubFetch([
      { status: 200, body: { statut: 'coordonnees_requises' } },
      { status: 201, body: { statut: 'enregistre', id_demande: 42, contact_connu: 0 } },
    ]);
    render(<GuideDownloadDialog data={data} idPageHub={ID_PAGE_HUB} pageId={PAGE_ID} />);
    await open();
    submitEmailStep();

    await waitFor(() => expect(screen.getByLabelText(data.fields.name)).toBeDefined());

    // APPEL 1 : email + id_page_hub guide, SANS reponses ni coordonnees.
    const body1 = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string);
    expect(body1.email).toBe('jean@exemple.fr');
    expect(body1.id_page_hub).toBe(ID_PAGE_HUB);
    expect(body1.reponses).toBeUndefined();
    expect(body1.coordonnees).toBeUndefined();

    fireEvent.click(screen.getByLabelText(data.civilityOptions[0])); // Monsieur
    fireEvent.change(screen.getByLabelText(data.fields.prenom), { target: { value: 'Jean' } });
    fireEvent.change(screen.getByLabelText(data.fields.name), { target: { value: 'Dupont' } });
    fireEvent.change(screen.getByLabelText(data.fields.phone), { target: { value: '+33612345678' } });
    fireEvent.change(screen.getByLabelText(data.fields.postalCode), { target: { value: '44000' } });
    fireEvent.click(
      screen.getByRole('button', { name: new RegExp(data.coordinatesSubmitLabel, 'i') })
    );

    await waitFor(() => expect(screen.getByText(data.download.title)).toBeDefined());

    // APPEL 2 : civilité + nom_prenom recombiné (« _ ») + pays, sans adresse.
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const body2 = JSON.parse((fetchMock.mock.calls[1][1] as RequestInit).body as string);
    expect(body2.coordonnees).toEqual({
      civilite: 'Monsieur',
      nom_prenom: 'Dupont_Jean',
      telephone: '+33612345678',
      code_postal: '44000',
      pays: 'France',
    });
    expect(
      screen.getByRole('link', { name: new RegExp(data.download.buttonLabel, 'i') })
    ).toBeDefined();
  });

  /** E-mail connu : APPEL 1 → 201 direct. L'étape coordonnées n'apparaît jamais. */
  it('va directement au téléchargement si l’e-mail est reconnu (1 seul appel)', async () => {
    const fetchMock = stubFetch([
      { status: 201, body: { statut: 'enregistre', id_demande: 7, contact_connu: 1 } },
    ]);
    render(<GuideDownloadDialog data={data} idPageHub={ID_PAGE_HUB} pageId={PAGE_ID} />);
    await open();
    submitEmailStep();

    await waitFor(() => expect(screen.getByText(data.download.title)).toBeDefined());
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(screen.queryByLabelText(data.fields.name)).toBeNull();
  });

  it('bloque l’étape coordonnées si le téléphone est invalide', async () => {
    stubFetch([{ status: 200, body: { statut: 'coordonnees_requises' } }]);
    render(<GuideDownloadDialog data={data} idPageHub={ID_PAGE_HUB} pageId={PAGE_ID} />);
    await open();
    submitEmailStep();
    await waitFor(() => expect(screen.getByLabelText(data.fields.name)).toBeDefined());

    fireEvent.click(screen.getByLabelText(data.civilityOptions[0]));
    fireEvent.change(screen.getByLabelText(data.fields.prenom), { target: { value: 'Jean' } });
    fireEvent.change(screen.getByLabelText(data.fields.name), { target: { value: 'Dupont' } });
    fireEvent.change(screen.getByLabelText(data.fields.postalCode), { target: { value: '44000' } });
    fireEvent.change(screen.getByLabelText(data.fields.phone), { target: { value: '123' } });

    expect(
      screen.getByRole('button', { name: new RegExp(data.coordinatesSubmitLabel, 'i') })
    ).toBeDisabled();
    const alerts = await screen.findAllByRole('alert');
    expect(alerts.some((a) => /téléphone/i.test(a.textContent ?? ''))).toBe(true);
  });

  /**
   * Lead connu (drapeau cookie) : ouverture → écran de téléchargement DIRECT,
   * SANS aucun appel réseau (on ne stocke plus l'e-mail, donc pas de ré-envoi).
   */
  it('va directement au téléchargement si le lead est connu, sans appel réseau', async () => {
    // Le drapeau est posé sur le PROJET, pas sur le tunnel : `PAGE_ID`.
    markLeadKnown(PAGE_ID);
    const fetchMock = stubFetch([{ status: 200, body: {} }]);
    render(<GuideDownloadDialog data={data} idPageHub={ID_PAGE_HUB} pageId={PAGE_ID} />);
    await open();

    await waitFor(() => expect(screen.getByText(data.download.title)).toBeDefined());
    expect(fetchMock).not.toHaveBeenCalled();
    // L'étape e-mail (label « Adresse e-mail ») ne s'affiche jamais.
    expect(screen.queryByLabelText(data.fields.email)).toBeNull();
  });

  /** Verrou anti double-clic : bouton désactivé pendant l'appel en vol. */
  it('désactive le bouton pendant l’appel en cours', async () => {
    let resolveFetch: (value: unknown) => void = () => {};
    const pending = new Promise((resolve) => {
      resolveFetch = resolve;
    });
    globalThis.fetch = vi.fn(() => pending) as unknown as typeof fetch;

    render(<GuideDownloadDialog data={data} idPageHub={ID_PAGE_HUB} pageId={PAGE_ID} />);
    await open();
    fireEvent.change(screen.getByLabelText(data.fields.email), {
      target: { value: 'jean@exemple.fr' },
    });
    const submit = screen.getByRole('button', { name: new RegExp(data.emailSubmitLabel, 'i') });
    fireEvent.click(submit);

    await waitFor(() => expect(submit).toBeDisabled());

    resolveFetch({ status: 200, ok: true, json: async () => ({ statut: 'coordonnees_requises' }) });
  });
});
