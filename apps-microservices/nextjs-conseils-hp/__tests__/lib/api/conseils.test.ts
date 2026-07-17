import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock dynamic import of mocks (used when no API token)
vi.mock('@/data/mocks/index', () => ({
  getMockPage: (id: number) => ({ slug: `mock-${id}`, pageType: 'prix', meta: {}, hero: {}, blocks: [] }),
}));

/** Construit une réponse fetch minimale (l'implémentation lit res.ok/status/text()). */
function jsonResponse(body: unknown, init: { ok?: boolean; status?: number } = {}): Response {
  return {
    ok: init.ok ?? true,
    status: init.status ?? 200,
    text: async () => JSON.stringify(body),
  } as Response;
}

describe('fetchConseilPage', () => {
  beforeEach(() => {
    vi.resetModules();
    vi.unstubAllEnvs();
  });

  it('returns the mock page when no API token is set', async () => {
    vi.stubEnv('CONSEILS_API_TOKEN', '');

    const { fetchConseilPage } = await import('@/lib/api/conseils');
    const result = await fetchConseilPage(1001);

    expect(result.ok).toBe(true);
    if (result.ok) expect(result.page.slug).toBe('mock-1001');
  });

  it('falls back to the mock page on network error (transient, token set)', async () => {
    vi.stubEnv('CONSEILS_API_TOKEN', 'fake-token');
    global.fetch = vi.fn().mockRejectedValueOnce(new Error('Network error'));

    const { fetchConseilPage } = await import('@/lib/api/conseils');
    const result = await fetchConseilPage(1001);

    // Erreur transitoire → on ne redirige pas, on sert le mock.
    expect(result.ok).toBe(true);
  });

  it('returns not-found when the API body signals 404', async () => {
    vi.stubEnv('CONSEILS_API_TOKEN', 'fake-token');
    global.fetch = vi.fn().mockResolvedValueOnce(
      jsonResponse({ error: '404 Not Found', error_description: 'Page conseil introuvable' }),
    );

    const { fetchConseilPage } = await import('@/lib/api/conseils');
    const result = await fetchConseilPage(1001);

    expect(result).toEqual({ ok: false, reason: 'not-found' });
  });

  it('returns gone when the API body signals 410', async () => {
    vi.stubEnv('CONSEILS_API_TOKEN', 'fake-token');
    global.fetch = vi.fn().mockResolvedValueOnce(
      jsonResponse({ error: '410 Gone', error_description: 'Page conseil supprimé' }),
    );

    const { fetchConseilPage } = await import('@/lib/api/conseils');
    const result = await fetchConseilPage(1001);

    expect(result).toEqual({ ok: false, reason: 'gone' });
  });
});
