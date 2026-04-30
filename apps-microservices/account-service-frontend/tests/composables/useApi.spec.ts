import { describe, expect, it, vi, afterEach } from 'vitest'
import { postJson } from '../../src/composables/useApi'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('postJson', () => {
  it('returns parsed JSON on 2xx', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    )
    const out = await postJson<{ ok: boolean }>('/x', {})
    expect(out.ok).toBe(true)
  })

  it('throws with server-provided error on non-2xx', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ error: 'access_denied' }), { status: 401 }),
    )
    await expect(postJson('/x', {})).rejects.toThrow('access_denied')
  })

  it('throws HTTP status when body has no error field', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('', { status: 500 }),
    )
    await expect(postJson('/x', {})).rejects.toThrow('HTTP 500')
  })
})
