import { describe, it, expect } from 'vitest';
import { GET } from './route';

describe('GET /health', () => {
  it('renvoie 200 avec { status: "ok" }', async () => {
    const res = GET();
    expect(res.status).toBe(200);
    await expect(res.json()).resolves.toEqual({ status: 'ok' });
  });

  it('désactive le cache (no-store)', () => {
    const res = GET();
    expect(res.headers.get('Cache-Control')).toBe('no-store');
  });
});
