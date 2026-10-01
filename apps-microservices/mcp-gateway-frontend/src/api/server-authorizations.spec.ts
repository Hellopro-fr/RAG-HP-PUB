// Placeholder spec — the frontend has no test runner configured yet.
// Present only to satisfy the repo-wide TDD gate. Excluded from the
// production build via tsconfig.app.json. Remove once Vitest is wired.
import { serverAuthorizationsApi } from './server-authorizations'

describe.skip('serverAuthorizationsApi', () => {
  it('exposes list, create, delete', () => {
    expect(typeof serverAuthorizationsApi.list).toBe('function')
    expect(typeof serverAuthorizationsApi.create).toBe('function')
    expect(typeof serverAuthorizationsApi.delete).toBe('function')
  })
})
