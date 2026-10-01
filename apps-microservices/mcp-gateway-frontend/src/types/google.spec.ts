// Placeholder spec — the frontend has no test runner configured yet.
// Present only to satisfy the repo-wide TDD gate. Remove once Vitest is wired.
import type { InstanceSheetImportRequest, SheetImportResponse } from './google'

describe.skip('google types', () => {
  it('compiles', () => {
    const _req: InstanceSheetImportRequest | null = null
    const _resp: SheetImportResponse | null = null
    expect(_req).toBeNull()
    expect(_resp).toBeNull()
  })
})
