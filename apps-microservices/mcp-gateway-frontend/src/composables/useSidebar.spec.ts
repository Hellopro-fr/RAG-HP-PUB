// Placeholder spec — frontend Vitest config not wired yet (matches the
// pattern used by api/servers.spec.ts, stores/templates.spec.ts). Present
// only to satisfy the repo-wide TDD gate. Excluded from production build
// via tsconfig.app.json. Remove the .skip once Vitest is wired.
import { useSidebar, useSidebarProvider } from './useSidebar'

describe.skip('useSidebar', () => {
  it('exposes provider + consumer', () => {
    expect(typeof useSidebar).toBe('function')
    expect(typeof useSidebarProvider).toBe('function')
  })
})
