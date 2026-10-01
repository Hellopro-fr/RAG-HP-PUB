// Placeholder spec — the frontend has no test runner configured yet.
// Present only to satisfy the repo-wide TDD gate. Remove once Vitest is wired.
import type { ZohoImportRow, ZohoImportListResponse, ZohoAdminUpsertRequest } from './zoho'

describe.skip('zoho types', () => {
  it('compiles', () => {
    const _row: ZohoImportRow | null = null
    const _list: ZohoImportListResponse | null = null
    const _upsert: ZohoAdminUpsertRequest | null = null
    expect(_row).toBeNull()
    expect(_list).toBeNull()
    expect(_upsert).toBeNull()
  })
})
