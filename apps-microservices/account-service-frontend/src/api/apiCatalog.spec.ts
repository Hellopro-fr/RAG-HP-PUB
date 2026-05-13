import { describe, expect, it, vi, beforeEach } from 'vitest'

vi.mock('./client', () => ({
  api: vi.fn(),
}))

import { api } from './client'
import * as catalog from './apiCatalog'

describe('apiCatalog API wrapper', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('list passes pagination + filter', async () => {
    ;(api as any).mockResolvedValue({ items: [], total: 0 })
    await catalog.list(20, 5, 'foo')
    expect(api).toHaveBeenCalledWith('/api/v1/admin/api', {
      query: { limit: 20, offset: 5, filter: 'foo' },
    })
  })

  it('create POSTs payload', async () => {
    ;(api as any).mockResolvedValue({ id: 'x' })
    await catalog.create({ name: 'x-service', baseUrl: 'http://x', protocols: ['rest'] })
    expect(api).toHaveBeenCalledWith('/api/v1/admin/api', {
      method: 'POST',
      body: { name: 'x-service', baseUrl: 'http://x', protocols: ['rest'] },
    })
  })

  it('rescanOne hits the right path', async () => {
    ;(api as any).mockResolvedValue({ servicesScanned: 1 })
    await catalog.rescanOne('abc')
    expect(api).toHaveBeenCalledWith('/api/v1/admin/api/abc/rescan', {
      method: 'POST',
    })
  })
})
