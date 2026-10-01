import { describe, it, expect } from 'vitest'
import type { CurrentUser } from './user'

describe('CurrentUser type', () => {
  it('shape compiles with required fields', () => {
    const u: CurrentUser = { email: 'a@x', is_admin: true, is_allowed: true }
    expect(u.email).toBe('a@x')
    expect(u.is_admin).toBe(true)
  })
})
