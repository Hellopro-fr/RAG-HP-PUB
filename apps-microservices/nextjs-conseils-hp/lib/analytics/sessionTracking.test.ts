import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { getTrackingSessionId, resolveTrackingSessionId, sendPageView } from './sessionTracking';

const ENDPOINT = 'https://www.hellopro.fr/hellopro_fr/ajax/ajax_trace_session.php';

function setCookies(value: string) {
  Object.defineProperty(document, 'cookie', {
    configurable: true,
    get: () => value,
    // no-op : la génération de cookie (resolveTrackingSessionId) ne doit pas casser le test.
    set: () => {},
  });
}

beforeEach(() => {
  setCookies('');
  // jsdom interdit replaceState() cross-origin → on stube directement location.
  vi.stubGlobal('location', {
    href: 'https://conseils.hellopro.fr/guide-1243.html',
    hostname: 'conseils.hellopro.fr',
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('getTrackingSessionId', () => {
  it('privilégie tracking_landing_session_id', () => {
    setCookies('PHPSESSID=php123; tracking_landing_session_id=land456');
    expect(getTrackingSessionId()).toBe('land456');
  });

  it('retombe sur PHPSESSID si tracking_landing_session_id absent', () => {
    setCookies('PHPSESSID=php123');
    expect(getTrackingSessionId()).toBe('php123');
  });

  it('renvoie une chaîne vide si aucun cookie de session', () => {
    setCookies('autre=valeur');
    expect(getTrackingSessionId()).toBe('');
  });
});

describe('resolveTrackingSessionId', () => {
  it('réutilise le cookie existant sans rien générer', () => {
    setCookies('tracking_landing_session_id=land456');
    expect(resolveTrackingSessionId()).toBe('land456');
  });

  it('génère un id de 32 caractères hexadécimaux si aucun cookie lisible', () => {
    setCookies('autre=valeur');
    expect(resolveTrackingSessionId()).toMatch(/^[0-9a-f]{32}$/);
  });

  it('sanitise le cookie existant comme le fait le lead (preg_replace [^a-zA-Z0-9])', () => {
    // Le lead reconstruit l'id via preg_replace('/[^a-zA-Z0-9]/','',cookie) : on doit
    // stocker la même valeur côté page_view, sinon aucun match en base.
    setCookies('tracking_landing_session_id=ab-cd_ef.12');
    expect(resolveTrackingSessionId()).toBe('abcdef12');
  });
});

describe('sendPageView', () => {
  it('envoie un beacon même sans cookie lisible (id généré)', () => {
    // Aucun cookie lisible → resolveTrackingSessionId génère un id → le beacon part.
    const beacon = vi.fn((_url: string, _data?: BodyInit | null) => true);
    vi.stubGlobal('navigator', { ...navigator, sendBeacon: beacon });
    sendPageView();
    expect(beacon).toHaveBeenCalledTimes(1);
    expect(beacon.mock.calls[0][0]).toBe(ENDPOINT);
  });

  it('émet un beacon page_view vers l’endpoint legacy', () => {
    setCookies('tracking_landing_session_id=land456');
    const beacon = vi.fn((_url: string, _data?: BodyInit | null) => true);
    vi.stubGlobal('navigator', { ...navigator, sendBeacon: beacon });

    sendPageView();

    expect(beacon).toHaveBeenCalledTimes(1);
    expect(beacon.mock.calls[0][0]).toBe(ENDPOINT);
  });

  it('retombe sur fetch keepalive si sendBeacon échoue', async () => {
    setCookies('tracking_landing_session_id=land456');
    vi.stubGlobal('navigator', { ...navigator, sendBeacon: vi.fn(() => false) });
    const fetchMock = vi.fn((_input: RequestInfo | URL, _init?: RequestInit) =>
      Promise.resolve(new Response(null, { status: 204 })),
    );
    vi.stubGlobal('fetch', fetchMock);

    sendPageView();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const url = fetchMock.mock.calls[0][0] as string;
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(url).toBe(ENDPOINT);
    expect(init.keepalive).toBe(true);
    expect(init.mode).toBe('no-cors');
    expect(init.credentials).toBe('include');
    const payload = JSON.parse(init.body as string);
    expect(payload).toMatchObject({
      action: 'page_view',
      session_id: 'land456',
      url: 'https://conseils.hellopro.fr/guide-1243.html',
      host: 'conseils.hellopro.fr',
    });
    // Format MySQL DATETIME `Y-m-d H:i:s` (pas d'ISO 8601).
    expect(payload.datetime).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/);
    expect(typeof payload.referrer).toBe('string');
  });
});
