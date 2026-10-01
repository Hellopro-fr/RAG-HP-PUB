export interface AuditEntry {
  id: number
  event: string
  actor_email?: string
  target_email?: string
  client_id?: string
  ip_addr?: string
  user_agent?: string
  metadata?: unknown
  created_at: string
}
