import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { resolveTrackingSessionId, sendPageView } from './sessionTracking';

const ENDPOINT = 'https://www.hellopro.fr/hellopro_fr/ajax/ajax_trace_session.php';

function setCookies(value: string) {
  Object.defineProperty(document, 'cookie', {
    configurable: true,
    get: () => value,
    set: () => {},
  });
}

beforeEach(() => {
  setCookies('');
  vi.stubGlobal('location', {
    href: 'https://conseils.hellopro.fr/guide-1243.html',
    hostname: 'conseils.hellopro.fr',
    protocol: 'https:',
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('resolveTrackingSessionId', () => {
  it('priorité 1 — tracking_landing_session_id (même si PHPSESSID et next_tracking_id présents)', () => {
    setCookies('tracking_landing_session_id=ef0e67b538397890b818dcd17fa6c059; PHPSESSID=1111; next_tracking_id=aabbccdd11223344aabbccdd11223344');
    expect(resolveTrackingSessionId()).toBe('ef0e67b538397890b818dcd17fa6c059');
  });

  it('priorité 2 — PHPSESSID écrase next_tracking_id si tracking_landing absent', () => {
    setCookies('PHPSESSID=ef0e67b538397890b818dcd17fa6c059; next_tracking_id=aabbccdd11223344aabbccdd11223344');
    expect(resolveTrackingSessionId()).toBe('ef0e67b538397890b818dcd17fa6c059');
  });

  it('priorité 3 — next_tracking_id réutilisé si ni landing ni PHPSESSID', () => {
    setCookies('next_tracking_id=aabbccdd11223344aabbccdd11223344');
    expect(resolveTrackingSessionId()).toBe('aabbccdd11223344aabbccdd11223344');
  });

  it('priorité 4 — aucun cookie → génère 32 hex', () => {
    setCookies('');
    expect(resolveTrackingSessionId()).toMatch(/^[0-9a-f]{32}$/);
  });

  it('sanitise les caractères non alphanumériques', () => {
    setCookies('tracking_landing_session_id=ab-cd_ef.12');
    expect(resolveTrackingSessionId()).toBe('abcdef12');
  });
});

describe('sendPageView', () => {
  it('emet un beacon page_view vers l\'endpoint legacy', () => {
    setCookies('next_tracking_id=aabbccdd11223344aabbccdd11223344');
    const beacon = vi.fn((_url: string, _data?: BodyInit | null) => true);
    vi.stubGlobal('navigator', { ...navigator, sendBeacon: beacon });

    sendPageView();

    expect(beacon).toHaveBeenCalledTimes(1);
    expect(beacon.mock.calls[0][0]).toBe(ENDPOINT);
  });

  it('retombe sur fetch keepalive si sendBeacon échoue', async () => {
    setCookies('next_tracking_id=aabbccdd11223344aabbccdd11223344');
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
    const payload = JSON.parse(init.body as string);
    expect(payload).toMatchObject({
      action: 'page_view',
      session_id: 'aabbccdd11223344aabbccdd11223344',
      url: 'https://conseils.hellopro.fr/guide-1243.html',
      host: 'conseils.hellopro.fr',
    });
    expect(payload.datetime).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/);
  });

  it('envoie même sans cookie (génère next_tracking_id)', () => {
    setCookies('');
    const beacon = vi.fn((_url: string, _data?: BodyInit | null) => true);
    vi.stubGlobal('navigator', { ...navigator, sendBeacon: beacon });

    sendPageView();

    expect(beacon).toHaveBeenCalledTimes(1);
  });
});
