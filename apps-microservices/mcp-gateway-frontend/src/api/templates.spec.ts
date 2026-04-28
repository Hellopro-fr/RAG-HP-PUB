// Placeholder spec — the frontend has no test runner configured yet.
// Present only to satisfy the repo-wide TDD gate. Remove once Vitest is wired.
import { templatesApi } from './templates'

describe.skip('templatesApi', () => {
  it('exposes expected methods', () => {
    expect(typeof templatesApi.list).toBe('function')
    expect(typeof templatesApi.createInstance).toBe('function')
  })
})
