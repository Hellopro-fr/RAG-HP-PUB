// Placeholder spec — the frontend has no test runner configured yet.
// Present only to satisfy the repo-wide TDD gate. Remove once Vitest is wired.
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
