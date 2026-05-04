import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore } from './auth'

describe('auth store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('login sets user on success', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ email: 'a@x', is_admin: true, is_allowed: true }),
    })
    globalThis.fetch = fetchMock as unknown as typeof fetch

    const a = useAuthStore()
    await a.login('a', 'p')
    expect(a.isAuthenticated).toBe(true)
    expect(a.isAdmin).toBe(true)
  })

  it('login throws ApiError on 401', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ error: 'invalid_grant', error_description: 'bad creds' }),
    })
    globalThis.fetch = fetchMock as unknown as typeof fetch
    const a = useAuthStore()
    await expect(a.login('a', 'wrong')).rejects.toThrow('Unauthorized')
  })
})
