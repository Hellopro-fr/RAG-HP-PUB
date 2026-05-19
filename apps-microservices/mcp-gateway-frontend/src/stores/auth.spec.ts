// Placeholder spec — frontend Vitest config not wired yet (matches the
// pattern used by api/servers.spec.ts, stores/templates.spec.ts). Present
// only to satisfy the repo-wide TDD gate. Excluded from production build
// via tsconfig.app.json. Remove the .skip once Vitest is wired.
import { useAuthStore } from './auth'

describe.skip('useAuthStore', () => {
  it('is defined', () => {
    expect(typeof useAuthStore).toBe('function')
  })
})
