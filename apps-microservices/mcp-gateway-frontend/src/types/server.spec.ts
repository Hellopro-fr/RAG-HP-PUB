// Type-only smoke test — server.ts has no runtime, this asserts the
// module compiles. Excluded from production build via tsconfig.app.json.
import type { Server, DocConfigGuide } from './server'

const _g: DocConfigGuide = { authType: '', steps: [] }
const _s = {} as Server
void _g; void _s

describe.skip('server types', () => {
  it('compiles', () => { expect(true).toBe(true) })
})
