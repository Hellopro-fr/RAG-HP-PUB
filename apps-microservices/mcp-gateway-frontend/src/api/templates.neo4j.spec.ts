import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('./client', () => ({
  api: { postMultipart: vi.fn().mockResolvedValue({}) }
}))

import { api } from './client'
import { templatesApi } from './templates'

const postMultipart = api.postMultipart as unknown as ReturnType<typeof vi.fn>
const conn = { uri: 'bolt://neo4j:7687', username: 'reader', password: 's3cret', database: 'graph' }

describe('templatesApi Neo4j payloads', () => {
  beforeEach(() => postMultipart.mockClear())

  it('createInstance sends neo4j fields and no credentials file', async () => {
    await templatesApi.createInstance({
      template_slug: 'neo4j',
      name: 'prod',
      extra_env: { NEO4J_READ_ONLY: 'true' },
      neo4j: conn
    })
    const [url, fd] = postMultipart.mock.calls[0] as [string, FormData]
    expect(url).toBe('/api/v1/template-instances')
    expect(fd.get('neo4j_uri')).toBe('bolt://neo4j:7687')
    expect(fd.get('neo4j_database')).toBe('graph')
    expect(fd.get('credentials')).toBeNull()
    expect(fd.get('extra_env')).toBe('{"NEO4J_READ_ONLY":"true"}')
  })

  it('rotate sends neo4j fields and extra_env', async () => {
    await templatesApi.rotate('inst-1', { neo4j: conn, extra_env: { NEO4J_READ_ONLY: 'false' } })
    const [url, fd] = postMultipart.mock.calls[0] as [string, FormData]
    expect(url).toBe('/api/v1/template-instances/inst-1/rotate-credentials')
    expect(fd.get('neo4j_password')).toBe('s3cret')
    expect(fd.get('extra_env')).toBe('{"NEO4J_READ_ONLY":"false"}')
    expect(fd.get('credentials')).toBeNull()
  })

  it('rotate with a File keeps the Google upload', async () => {
    const file = new File(['{}'], 'sa.json', { type: 'application/json' })
    await templatesApi.rotate('inst-2', file)
    const [, fd] = postMultipart.mock.calls[0] as [string, FormData]
    expect(fd.get('credentials')).toBeInstanceOf(File)
    expect(fd.get('neo4j_uri')).toBeNull()
  })
})
