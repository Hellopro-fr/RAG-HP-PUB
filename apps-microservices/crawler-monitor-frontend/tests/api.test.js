import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { apiFetch, api, ApiError, setOnUnauthorized } from '../src/lib/api';

const jsonRes = (status, body = {}) => ({
  status,
  ok: status >= 200 && status < 300,
  json: async () => body,
  text: async () => JSON.stringify(body),
});

beforeEach(() => {
  globalThis.fetch = vi.fn();
});

afterEach(() => {
  setOnUnauthorized(null);
  vi.restoreAllMocks();
});

describe('api — session refusée', () => {
  it('déclenche onUnauthorized sur 401', async () => {
    const onUnauthorized = vi.fn();
    setOnUnauthorized(onUnauthorized);
    globalThis.fetch.mockResolvedValue(jsonRes(401));
    await expect(api.get('/jobs', 'tok')).rejects.toBeInstanceOf(ApiError);
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it('ne déconnecte PAS sur 403 (nginx / service relayé par /albums)', async () => {
    const onUnauthorized = vi.fn();
    setOnUnauthorized(onUnauthorized);
    globalThis.fetch.mockResolvedValue(jsonRes(403, { error: 'forbidden' }));
    const err = await api.get('/albums/a.fr/products', 'tok').catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(403);
    expect(err.body).toEqual({ error: 'forbidden' });
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it('ne rejoue jamais un 401 (une seule requête)', async () => {
    globalThis.fetch.mockResolvedValue(jsonRes(401));
    await api.get('/jobs', 'tok').catch(() => {});
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
  });
});

describe('api — retry limité aux méthodes idempotentes', () => {
  it('rejoue un GET sur 500', async () => {
    globalThis.fetch
      .mockResolvedValueOnce(jsonRes(500))
      .mockResolvedValueOnce(jsonRes(200, { ok: true }));
    await expect(api.get('/jobs', 'tok')).resolves.toEqual({ ok: true });
    expect(globalThis.fetch).toHaveBeenCalledTimes(2);
  });

  it('ne rejoue PAS un POST sur 500 (effet de bord non idempotent)', async () => {
    globalThis.fetch.mockResolvedValue(jsonRes(500, { error: 'boom' }));
    const err = await api.post('/callbacks/0/retry', 'tok').catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(500);
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
  });

  it('ne rejoue PAS un DELETE sur 500', async () => {
    globalThis.fetch.mockResolvedValue(jsonRes(500));
    await api.delete('/albums/a.fr', 'tok').catch(() => {});
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
  });

  it('ne rejoue jamais un 4xx sur GET', async () => {
    globalThis.fetch.mockResolvedValue(jsonRes(404, { error: 'not found' }));
    const err = await api.get('/albums/jobs/x', 'tok').catch((e) => e);
    expect(err.status).toBe(404);
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
  });

  it('honore un retry explicite sur une méthode non idempotente', async () => {
    globalThis.fetch
      .mockResolvedValueOnce(jsonRes(500))
      .mockResolvedValueOnce(jsonRes(200, { ok: 1 }));
    await expect(
      apiFetch('/login', { method: 'POST', body: {}, retry: { attempts: 2, backoffMs: 1 } }),
    ).resolves.toEqual({ ok: 1 });
    expect(globalThis.fetch).toHaveBeenCalledTimes(2);
  });
});
