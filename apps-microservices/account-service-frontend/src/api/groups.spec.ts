import { afterEach, describe, expect, it, vi } from 'vitest'
import * as groupsApi from './groups'

function mockFetch(status = 200, body: unknown = {}) {
  const fn = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    statusText: 'x',
    json: () => Promise.resolve(body),
  })
  vi.stubGlobal('fetch', fn)
  return fn
}

describe('groups api', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('creates a group with name and description', async () => {
    const f = mockFetch(201, { id: 'g1' })
    await groupsApi.create('Data', 'Équipe data')
    expect(f).toHaveBeenCalledWith('/api/v1/admin/groups', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ name: 'Data', description: 'Équipe data' }),
    }))
  })

  it('encodes the member email in the removal path', async () => {
    const f = mockFetch(204)
    await groupsApi.removeMember('g1', 'a+b@example.com')
    expect(f.mock.calls[0][0]).toBe('/api/v1/admin/groups/g1/members/a%2Bb%40example.com')
    expect(f.mock.calls[0][1].method).toBe('DELETE')
  })
})
