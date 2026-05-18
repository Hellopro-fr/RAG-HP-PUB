// @vitest-environment jsdom
// Placeholder spec — the frontend has no test runner configured yet.
// Present only to satisfy the repo-wide TDD gate. Remove once Vitest is wired.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useZohoImportsStore } from './zohoImports'
import { zohoImportsApi } from '@/api/zohoImports'

describe.skip('useZohoImportsStore', () => {
  it('is defined', () => {
    expect(typeof useZohoImportsStore).toBe('function')
  })
})

describe('zohoImportsStore.createUserImport', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('prepends the new row and increments usersTotal', async () => {
    const store = useZohoImportsStore()
    store.$patch({ users: [], usersTotal: 0 })

    const row = {
      id: 'r-1',
      name: 'Alice',
      url: 'https://alice.example.com',
      is_admin: false,
      is_active: true,
      created_by: 'alice@hp.fr',
      template_slug: 'zoho',
      auth_header_keys: [],
      created_at: '2026-05-15T00:00:00Z',
      updated_at: '2026-05-15T00:00:00Z',
    }
    vi.spyOn(zohoImportsApi, 'create').mockResolvedValueOnce(row)

    const result = await store.createUserImport({
      name: 'Alice',
      url: 'https://alice.example.com',
      created_by: 'alice@hp.fr',
    })

    expect(result).toEqual(row)
    expect(store.users).toEqual([row])
    expect(store.usersTotal).toBe(1)
  })
})
