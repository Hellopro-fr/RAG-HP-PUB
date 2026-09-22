// Type-only smoke test — server.ts has no runtime, this asserts the
// module compiles. Excluded from production build via tsconfig.app.json.
import { describe, it, expect } from 'vitest'
import type { Server, DocConfigGuide } from './server'
import { MIN_ROLE_OPTIONS, minRoleLabel } from './server'

const _g: DocConfigGuide = { authType: '', steps: [] }
const _s = {} as Server
void _g; void _s

describe.skip('server types', () => {
  it('compiles', () => { expect(true).toBe(true) })
})

describe('min_role options', () => {
  it('offers public plus the three gateway roles, public first', () => {
    expect(MIN_ROLE_OPTIONS.map((o) => o.value)).toEqual([
      '',
      'config-only',
      'read-only',
      'admin',
    ])
  })

  it('labels the empty value as public rather than leaving it blank', () => {
    expect(minRoleLabel('')).toBe('Public')
  })

  it('labels a gated value with its role', () => {
    expect(minRoleLabel('admin')).toBe('Admin')
  })

  it('falls back to the raw value for an unknown role', () => {
    expect(minRoleLabel('wizard')).toBe('wizard')
  })
})
