import { describe, it, expect } from 'vitest'
import config from '../vite.config'

describe('vite.config', () => {
  it('exports a config with plugins and test settings', async () => {
    const resolved = typeof config === 'function' ? await config({ mode: 'test', command: 'serve' }) : config
    expect(Array.isArray(resolved.plugins)).toBe(true)
    expect((resolved as { test?: unknown }).test).toBeDefined()
  })
})
