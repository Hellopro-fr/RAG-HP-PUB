import { describe, it, expect, vi } from 'vitest'

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    isAdmin: false,
    isAuthenticated: false,
    hasRole: () => false,
    checkSession: vi.fn(() => Promise.resolve(false)),
  }),
}))

import { router } from './index'

describe('router', () => {
  it('registers the bdd-tables route with admin role and auth', () => {
    const route = router.getRoutes().find((r) => r.name === 'bdd-tables')
    expect(route).toBeDefined()
    expect(route?.path).toBe('/bdd-tables')
    expect(route?.meta.requiresAuth).toBe(true)
    expect(route?.meta.minRole).toBe('admin')
    expect(route?.meta.title).toBe('Tables BDD')
  })

  it('registers bdd-table-add route with admin role', () => {
    const route = router.getRoutes().find((r) => r.name === 'bdd-table-add')
    expect(route).toBeDefined()
    expect(route?.path).toBe('/bdd-tables/new')
    expect(route?.meta.minRole).toBe('admin')
  })

  it('registers bdd-table-fields route with admin role', () => {
    const route = router.getRoutes().find((r) => r.name === 'bdd-table-fields')
    expect(route).toBeDefined()
    expect(route?.path).toBe('/bdd-tables/:id/fields')
    expect(route?.meta.minRole).toBe('admin')
  })
})
