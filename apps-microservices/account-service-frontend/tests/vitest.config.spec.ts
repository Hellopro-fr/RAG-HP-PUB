import { describe, expect, it } from 'vitest'

describe('vitest.config', () => {
  it('loads the config module', async () => {
    const mod = await import('../vitest.config')
    expect(mod.default).toBeDefined()
  })
})
