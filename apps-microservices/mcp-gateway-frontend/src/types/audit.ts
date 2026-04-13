export interface AuditLog {
  id: number
  user_email: string
  action: string
  resource_type: string
  resource_id: string
  request_method: string
  request_path: string
  request_body?: string
  response_status: number
  response_body?: string
  ip_address: string
  created_at: string
}

export interface AuditLogResult {
  logs: AuditLog[]
  total: number
  page: number
  pages: number
}
