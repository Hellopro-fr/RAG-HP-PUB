import { describe, it, expect } from 'vitest'
import router from './index'

describe('router', () => {
  it('has /login as public route', () => {
    const route = router.getRoutes().find((r) => r.path === '/login')
    expect(route).toBeDefined()
    expect(route?.meta.requiresAuth).toBe(false)
  })

  it('has /admin/services with admin minRole', () => {
    const route = router.getRoutes().find((r) => r.path === '/admin/services')
    expect(route).toBeDefined()
    expect(route?.meta.minRole).toBe('admin')
  })
})
