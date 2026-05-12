// Google Sheets import types

export interface GoogleStatus {
  connected: boolean
  email?: string
}

export interface SpreadsheetListItem {
  id: string
  name: string
  modified_time: string
  web_view_link: string
}

export interface SheetInfo {
  spreadsheet_id: string
  title: string
  sheets: string[]
}

export interface SheetPreview {
  headers: string[]
  rows: string[][]
  total_rows: number
}

export interface ColumnMapping {
  [key: string]: string | undefined
  name: string
  url: string
  auth_headers?: string
  tags?: string
  transport_preference?: string
  connect_timeout_ms?: string
  tool_prefix?: string
  icon?: string
  mcp_transport?: string
  mcp_command?: string
  mcp_args?: string
  mcp_env?: string
  doc_slug?: string
  doc_description?: string
  // Optional — when set, each row's cell at this column header becomes the
  // created_by stamped on the imported mcp_servers row. Empty falls back to
  // the connected user.
  created_by?: string
}

export interface SheetImportRequest {
  spreadsheet_id: string
  sheet_name: string
  column_mapping: ColumnMapping
  auto_discover: boolean
  name_prefix?: string
  fixed_tags?: string
  fixed_tool_prefix?: string
  fixed_icon?: string
  disable_documentation?: boolean
  // Non-empty when the import was launched from the templates catalog
  // (e.g. custom-http). Stamped on every imported mcp_servers row so the
  // docs / docs-admin lists can filter template-origin rows uniformly.
  template_slug?: string
}

export interface SheetImportResultEntry {
  row: number
  name: string
  status: 'imported' | 'skipped' | 'error'
  message?: string
}

export interface SheetImportResponse {
  total: number
  imported: number
  skipped: number
  errors: number
  results: SheetImportResultEntry[]
}

// Request body for POST /api/v1/google/sheets/import-instances — batch-creates
// template instances from a Google Sheet. Mirrors the server-import shape but
// scoped to a single template selected via template_slug.
export interface InstanceSheetImportRequest {
  spreadsheet_id: string
  sheet_name: string
  template_slug: string
  name_column: string
  credentials_column: string
  // Template required_extra_env key -> sheet column header.
  extra_env_columns?: Record<string, string>
  auto_discover?: boolean
  fixed_tags?: string
  fixed_tool_prefix?: string
  fixed_icon?: string
  name_prefix?: string
  // Optional — sheet column whose cell value sets the template instance's
  // created_by. Empty/unmapped falls back to the connected user.
  created_by_column?: string
}
