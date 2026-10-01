// Placeholder spec — Vitest config not wired for this frontend yet.
// Excluded from production build via tsconfig.app.json.
import { safeHtml, sanitizeHtml } from './safeHtml'

describe.skip('v-safe-html directive', () => {
  it('exposes mounted + updated hooks', () => {
    expect(typeof safeHtml.mounted).toBe('function')
    expect(typeof safeHtml.updated).toBe('function')
    expect(typeof sanitizeHtml).toBe('function')
  })
})
