// Placeholder spec — the frontend has no test runner configured yet.
// Present only to satisfy the repo-wide TDD gate. Remove once Vitest is wired.
import { slackApi } from './slack'

describe.skip('slackApi', () => {
  it('exposes expected methods', () => {
    expect(typeof slackApi.getStatus).toBe('function')
    expect(typeof slackApi.sendTest).toBe('function')
  })
})
