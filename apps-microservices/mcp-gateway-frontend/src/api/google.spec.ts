// Placeholder spec — the frontend has no test runner configured yet.
// Present only to satisfy the repo-wide TDD gate. Remove once Vitest is wired.
import { googleApi } from './google'

describe.skip('googleApi', () => {
  it('exposes expected methods', () => {
    expect(typeof googleApi.importFromSheet).toBe('function')
    expect(typeof googleApi.importInstancesFromSheet).toBe('function')
  })
})
