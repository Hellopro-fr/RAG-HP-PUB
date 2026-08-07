import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { LeadPopup } from '@/components/hub/LeadPopup';
import { listHubPages, guideIdPageHub } from '@/data/hub';
import type { HubLeadPopup } from '@/types/hub';

vi.mock('next/image', () => ({
  default: ({ src, alt, ...props }: { src: string; alt: string; [key: string]: unknown }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={src} alt={alt} {...props} />
  ),
}));

// PhoneField encapsule react-international-phone (+ CSS) : mocké par un input simple.
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

const data = listHubPages()[0].leadPopup;
const guide = listHubPages()[0].guideDialog;
const ID_PAGE_HUB = guideIdPageHub(listHubPages()[0].id);

const IMAGE = { src: '/images/hub/x/popup.png', alt: 'Guide' };

type MockResponse = { status: number; body: unknown };

function stubFetch(responses: MockResponse[]) {
  let i = 0;
  const fn = vi.fn(async () => {
    const r = responses[Math.min(i, responses.length - 1)];
    i += 1;
    return { status: r.status, ok: r.status < 400, json: async () => r.body } as Response;
  });
  globalThis.fetch = fn as unknown as typeof fetch;
  return fn;
}

/**
 * Rend la pop-up et la force ouverte : le déclencheur réel est un dépassement de
 * scroll sur une section absente en test.
 */
function renderOpen(
  overrides: Partial<HubLeadPopup> = {},
  fetchResponses: MockResponse[] = [{ status: 200, body: {} }]
) {
  const section = document.createElement('section');
  section.id = data.triggerSectionId;
  section.getBoundingClientRect = () => ({ bottom: -10 }) as DOMRect;
  document.body.appendChild(section);

  const fetchMock = stubFetch(fetchResponses);
  const result = render(
    <LeadPopup data={{ ...data, ...overrides }} guide={guide} idPageHub={ID_PAGE_HUB} />
  );
  fireEvent.scroll(window);
  return { ...result, fetchMock };
}

/** Renseigne un e-mail valide et valide l'étape e-mail (APPEL 1). */
function submitEmailStep() {
  fireEvent.change(screen.getByLabelText(data.emailPlaceholder), {
    target: { value: 'jean@exemple.fr' },
  });
  fireEvent.click(screen.getByRole('button', { name: new RegExp(data.submitLabel, 'i') }));
}

afterEach(() => {
  vi.restoreAllMocks();
  document.cookie = 'hub_lead=; path=/; max-age=0';
});

describe('LeadPopup', () => {
  it('reste fermée au montage', () => {
    render(<LeadPopup data={data} guide={guide} idPageHub={ID_PAGE_HUB} />);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('s’ouvre après avoir dépassé la section déclencheuse', async () => {
    renderOpen();
    await waitFor(() => expect(screen.getByRole('dialog')).toBeDefined());
    expect(screen.getByText(data.title)).toBeDefined();
  });

  it('ne réserve pas la colonne image quand aucun visuel n’est livré', async () => {
    renderOpen({ image: undefined });
    await waitFor(() => expect(screen.getByRole('dialog')).toBeDefined());
    const grid = document.body.querySelector('[class*="sm:grid-cols-"]');
    expect(grid?.className).not.toContain('140px');
    expect(grid?.className).toContain('sm:grid-cols-1');
  });

  it('rend la pastille ronde, une ligne par entrée', async () => {
    renderOpen({ circleBadgeLines: ['100%', 'Gratuit'] });
    await waitFor(() => expect(screen.getByRole('dialog')).toBeDefined());
    expect(screen.getByText('100%')).toBeDefined();
    expect(screen.getByText('Gratuit')).toBeDefined();
  });

  it('rend le bandeau photo quand il est livré', async () => {
    renderOpen({
      bannerImage: { src: '/images/hub/x/banner.png', alt: 'Élevage de poules pondeuses' },
    });
    await waitFor(() => expect(screen.getByRole('dialog')).toBeDefined());
    expect(screen.getByAltText('Élevage de poules pondeuses')).toBeDefined();
  });

  it('réserve la colonne image quand un visuel est livré', async () => {
    renderOpen({ image: IMAGE });
    await waitFor(() => expect(screen.getByRole('dialog')).toBeDefined());
    const grid = document.body.querySelector('[class*="sm:grid-cols-"]');
    expect(grid?.className).toContain('140px');
    expect(screen.getByAltText('Guide')).toBeDefined();
  });

  it('garde le bouton grisé tant que l’e-mail n’est pas valide', async () => {
    renderOpen();
    await waitFor(() => expect(screen.getByRole('dialog')).toBeDefined());
    const submit = screen.getByRole('button', { name: new RegExp(data.submitLabel, 'i') });
    expect(submit).toBeDisabled(); // e-mail vide
    fireEvent.change(screen.getByLabelText(data.emailPlaceholder), {
      target: { value: 'pas-un-email' },
    });
    expect(submit).toBeDisabled(); // e-mail invalide
    fireEvent.change(screen.getByLabelText(data.emailPlaceholder), {
      target: { value: 'jean@exemple.fr' },
    });
    expect(submit).toBeEnabled();
  });

  it('e-mail inconnu → coordonnées → téléchargement (2 appels)', async () => {
    const { fetchMock } = renderOpen({}, [
      { status: 200, body: { statut: 'coordonnees_requises' } },
      { status: 201, body: { statut: 'enregistre', id_demande: 42, contact_connu: 0 } },
    ]);
    await waitFor(() => expect(screen.getByRole('dialog')).toBeDefined());
    submitEmailStep();

    await waitFor(() => expect(screen.getByLabelText(guide.fields.name)).toBeDefined());
    // APPEL 1 : e-mail + id_page_hub (= id guide), sans reponses ni coordonnees.
    const body1 = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string);
    expect(body1.email).toBe('jean@exemple.fr');
    expect(body1.id_page_hub).toBe(ID_PAGE_HUB);
    expect(body1.reponses).toBeUndefined();
    expect(body1.coordonnees).toBeUndefined();

    fireEvent.click(screen.getByLabelText(guide.civilityOptions[0])); // Monsieur
    fireEvent.change(screen.getByLabelText(guide.fields.prenom), { target: { value: 'Jean' } });
    fireEvent.change(screen.getByLabelText(guide.fields.name), { target: { value: 'Dupont' } });
    fireEvent.change(screen.getByLabelText(guide.fields.phone), { target: { value: '+33612345678' } });
    fireEvent.change(screen.getByLabelText(guide.fields.postalCode), { target: { value: '44000' } });
    fireEvent.click(
      screen.getByRole('button', { name: new RegExp(guide.coordinatesSubmitLabel, 'i') })
    );

    await waitFor(() => expect(screen.getByText(guide.download.title)).toBeDefined());
    const body2 = JSON.parse((fetchMock.mock.calls[1][1] as RequestInit).body as string);
    expect(body2.coordonnees).toEqual({
      civilite: 'Monsieur',
      nom_prenom: 'Dupont_Jean',
      telephone: '+33612345678',
      code_postal: '44000',
      pays: 'France',
    });
  });

  it('e-mail reconnu → téléchargement direct (1 appel, pas de coordonnées)', async () => {
    const { fetchMock } = renderOpen({}, [
      { status: 201, body: { statut: 'enregistre', id_demande: 7, contact_connu: 1 } },
    ]);
    await waitFor(() => expect(screen.getByRole('dialog')).toBeDefined());
    submitEmailStep();

    await waitFor(() => expect(screen.getByText(guide.download.title)).toBeDefined());
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(screen.queryByLabelText(guide.fields.name)).toBeNull();
  });
});
