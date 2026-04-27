import { describe, it, expect } from 'vitest'
import { bddApi } from './bdd'

describe('bddApi', () => {
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
})
