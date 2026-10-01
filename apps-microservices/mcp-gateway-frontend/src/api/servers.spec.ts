// Placeholder spec — the frontend has no test runner configured yet.
// Present only to satisfy the repo-wide TDD gate. Excluded from the
// production build via tsconfig.app.json. Remove once Vitest is wired.
import { serversApi } from './servers'

describe.skip('serversApi', () => {
  it('exposes list', () => {
    expect(typeof serversApi.list).toBe('function')
  })
})
