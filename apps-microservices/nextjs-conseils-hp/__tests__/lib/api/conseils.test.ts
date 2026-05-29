import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock dynamic import of mocks (used when no API token)
vi.mock('@/data/mocks/index', () => ({
  getMockPage: (id: number) => ({ slug: `mock-${id}`, pageType: 'prix', meta: {}, hero: {}, blocks: [] }),
}));

describe('fetchConseilPage', () => {
  beforeEach(() => {
    vi.resetModules();
    vi.unstubAllEnvs();
  });

  it('returns mock page when CONSEILS_API_TOKEN is not set', async () => {
    vi.stubEnv('CONSEILS_API_TOKEN', '');
    vi.stubEnv('NODE_ENV', 'production');

    const { fetchConseilPage } = await import('@/lib/api/conseils');
    const result = await fetchConseilPage(1001);

    expect(result).not.toBeNull();
    expect(result?.slug).toBe('mock-1001');
  });

  it('returns null on API fetch error when token is set', async () => {
    vi.stubEnv('CONSEILS_API_TOKEN', 'fake-token');
    vi.stubEnv('NODE_ENV', 'production');

    global.fetch = vi.fn().mockRejectedValueOnce(new Error('Network error'));

    const { fetchConseilPage } = await import('@/lib/api/conseils');
    const result = await fetchConseilPage(1001);

    expect(result).toBeNull();
  });

  it('returns null when API responds with 404', async () => {
    vi.stubEnv('CONSEILS_API_TOKEN', 'fake-token');
    vi.stubEnv('NODE_ENV', 'production');

    global.fetch = vi.fn().mockResolvedValueOnce({ ok: false, status: 404 } as Response);

    const { fetchConseilPage } = await import('@/lib/api/conseils');
    const result = await fetchConseilPage(1001);

    expect(result).toBeNull();
  });
});
