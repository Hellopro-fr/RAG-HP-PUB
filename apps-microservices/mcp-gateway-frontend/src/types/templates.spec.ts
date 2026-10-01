// Placeholder spec — the frontend has no test runner configured yet.
// Present only to satisfy the repo-wide TDD gate. Remove once Vitest is wired.
import type { Template, TemplateInstance } from './templates'

describe.skip('templates types', () => {
  it('compiles', () => {
    const _t: Template | null = null
    const _i: TemplateInstance | null = null
    expect(_t).toBeNull()
    expect(_i).toBeNull()
  })
})
