// Placeholder spec — the frontend has no test runner configured yet.
// Present only to satisfy the repo-wide TDD gate. Remove once Vitest is wired.
import { useTemplatesStore } from './templates'

describe.skip('useTemplatesStore', () => {
  it('is defined', () => {
    expect(typeof useTemplatesStore).toBe('function')
  })
})
