// Type-only smoke test — install-guide.ts has no runtime, this asserts
// the module compiles. Excluded from production build via tsconfig.app.json.
import type { ExecutorElement, InstallExecutor, InstallConfig } from './install-guide'

const _el: ExecutorElement = { id: '', type: 'text', props: { content: '' } }
const _ex = {} as InstallExecutor
const _cf = {} as InstallConfig
void _el; void _ex; void _cf

describe.skip('install-guide types', () => {
  it('compiles', () => { expect(true).toBe(true) })
})
