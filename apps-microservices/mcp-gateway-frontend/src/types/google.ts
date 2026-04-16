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
}

export interface SheetImportRequest {
  spreadsheet_id: string
  sheet_name: string
  column_mapping: ColumnMapping
  auto_discover: boolean
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
