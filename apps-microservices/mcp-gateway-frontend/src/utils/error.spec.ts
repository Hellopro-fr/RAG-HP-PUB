// Placeholder spec — Vitest config not wired for this frontend yet.
// Excluded from production build via tsconfig.app.json. Remove the .skip
// once Vitest is wired.
import { toErrorMessage } from './error'

describe.skip('toErrorMessage', () => {
  it('is defined', () => {
    expect(typeof toErrorMessage).toBe('function')
  })
})
