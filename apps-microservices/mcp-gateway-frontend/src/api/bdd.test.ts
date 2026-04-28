import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('./client', () => ({
  api: {
    get: vi.fn(() => Promise.resolve({})),
    post: vi.fn(() => Promise.resolve({})),
    put: vi.fn(() => Promise.resolve({})),
    patch: vi.fn(() => Promise.resolve({})),
    del: vi.fn(() => Promise.resolve(undefined)),
  },
}))

import { api } from './client'
import { bddApi } from './bdd'

const mockedApi = api as unknown as {
  get: ReturnType<typeof vi.fn>
  post: ReturnType<typeof vi.fn>
  put: ReturnType<typeof vi.fn>
  patch: ReturnType<typeof vi.fn>
  del: ReturnType<typeof vi.fn>
}

describe('bddApi', () => {
  beforeEach(() => {
    mockedApi.get.mockClear()
    mockedApi.post.mockClear()
    mockedApi.patch.mockClear()
    mockedApi.del.mockClear()
  })

  it('exposes catalog and used-table CRUD helpers', () => {
    expect(typeof bddApi.catalogDatabases).toBe('function')
    expect(typeof bddApi.catalogTables).toBe('function')
    expect(typeof bddApi.catalogFields).toBe('function')
    expect(typeof bddApi.listUsed).toBe('function')
    expect(typeof bddApi.getUsed).toBe('function')
    expect(typeof bddApi.createUsed).toBe('function')
    expect(typeof bddApi.patchUsed).toBe('function')
    expect(typeof bddApi.deleteUsed).toBe('function')
    expect(typeof bddApi.addField).toBe('function')
    expect(typeof bddApi.patchField).toBe('function')
    expect(typeof bddApi.deleteField).toBe('function')
  })

  describe('catalogTables', () => {
    it('calls GET on the catalog tables path with the search param', () => {
      bddApi.catalogTables(5, 'foo')
      expect(mockedApi.get).toHaveBeenCalledWith(
        '/api/v1/bdd/catalog/databases/5/tables',
        { search: 'foo' },
      )
    })

    it('omits the search param when empty', () => {
      bddApi.catalogTables(5)
      expect(mockedApi.get).toHaveBeenCalledWith(
        '/api/v1/bdd/catalog/databases/5/tables',
        undefined,
      )
    })
  })

  describe('listUsed', () => {
    it('passes both database_id and search when provided', () => {
      bddApi.listUsed({ database_id: 5, search: 'foo' })
      expect(mockedApi.get).toHaveBeenCalledWith(
        '/api/v1/bdd/used/tables',
        { database_id: '5', search: 'foo' },
      )
    })

    it('passes only database_id when search is empty', () => {
      bddApi.listUsed({ database_id: 10 })
      expect(mockedApi.get).toHaveBeenCalledWith(
        '/api/v1/bdd/used/tables',
        { database_id: '10' },
      )
    })

    it('omits params when neither is provided', () => {
      bddApi.listUsed()
      expect(mockedApi.get).toHaveBeenCalledWith(
        '/api/v1/bdd/used/tables',
        undefined,
      )
    })
  })

  describe('addField / patchField paths', () => {
    it('addField posts to the table fields path', () => {
      bddApi.addField('T', { field_name: 'name' })
      expect(mockedApi.post).toHaveBeenCalledWith(
        '/api/v1/bdd/used/tables/T/fields',
        { field_name: 'name' },
      )
    })

    it('patchField patches the specific field path', () => {
      bddApi.patchField('T', 'F', { description: 'd' })
      expect(mockedApi.patch).toHaveBeenCalledWith(
        '/api/v1/bdd/used/tables/T/fields/F',
        { description: 'd' },
      )
    })
  })
})
