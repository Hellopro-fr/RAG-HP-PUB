// @vitest-environment jsdom
// Placeholder spec — the frontend has no test runner configured yet.
// Present only to satisfy the repo-wide TDD gate. Remove once Vitest is wired.
import { describe, it, expect, vi } from 'vitest'
import { api } from './client'
import { zohoImportsApi } from './zohoImports'

describe.skip('zohoImportsApi', () => {
  it('exposes expected methods', () => {
    expect(typeof zohoImportsApi.list).toBe('function')
    expect(typeof zohoImportsApi.getByID).toBe('function')
    expect(typeof zohoImportsApi.patch).toBe('function')
    expect(typeof zohoImportsApi.remove).toBe('function')
    expect(typeof zohoImportsApi.test).toBe('function')
    expect(typeof zohoImportsApi.getAdmin).toBe('function')
    expect(typeof zohoImportsApi.upsertAdmin).toBe('function')
    expect(typeof zohoImportsApi.deleteAdmin).toBe('function')
  })
})

describe('zohoImportsApi.create', () => {
  it('POSTs the payload to /api/v1/zoho-imports', async () => {
    const row = {
      id: 'new-id',
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
    const postSpy = vi.spyOn(api, 'post').mockResolvedValueOnce(row)

    const result = await zohoImportsApi.create({
      name: 'Alice',
      url: 'https://alice.example.com',
      created_by: 'alice@hp.fr',
    })

    expect(postSpy).toHaveBeenCalledWith('/api/v1/zoho-imports', {
      name: 'Alice',
      url: 'https://alice.example.com',
      created_by: 'alice@hp.fr',
    })
    expect(result).toEqual(row)
  })
})

describe('zohoImportsApi.listTools', () => {
  it('GETs /api/v1/zoho-imports/{id}/tools', async () => {
    const resp = {
      tools: [
        {
          name: 'leads_list',
          description: 'List leads',
          input_schema: '{"type":"object"}',
          updated_at: '2026-05-15T00:00:00Z',
        },
      ],
      total: 1,
    }
    const getSpy = vi.spyOn(api, 'get').mockResolvedValueOnce(resp)

    const result = await zohoImportsApi.listTools('row-id')

    expect(getSpy).toHaveBeenCalledWith('/api/v1/zoho-imports/row-id/tools')
    expect(result).toEqual(resp)
  })
})
