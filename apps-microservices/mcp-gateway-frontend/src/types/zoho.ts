export interface ZohoImportRow {
  id: string
  name: string
  url: string
  is_admin: boolean
  is_active: boolean
  created_by: string
  template_slug: string
  auth_header_keys: string[]
  created_at: string
  updated_at: string
}

export interface ZohoImportListResponse {
  rows: ZohoImportRow[]
  total: number
  page: number
  limit: number
}

export interface ZohoImportUpdateRequest {
  name?: string
  url?: string
  /** Replace the encrypted blob. Pass an empty object to clear. */
  auth_headers?: Record<string, string>
  is_active?: boolean
}

export interface ZohoImportTestResponse {
  ok: boolean
  status_code?: number
  latency_ms: number
  error?: string
}

/** Body of POST /api/v1/zoho-imports/admin. */
export interface ZohoAdminUpsertRequest {
  name: string
  url: string
  auth_headers?: Record<string, string>
}

/** Body of POST /api/v1/zoho-imports — create a per-user import row. */
export interface ZohoUserCreateRequest {
  name: string
  url: string
  created_by: string
  auth_headers?: Record<string, string>
  is_active?: boolean
  template_slug?: string
}
