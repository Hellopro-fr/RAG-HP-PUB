import { api } from './client'
import type { ListResponse } from '@/types/oauth2'
import type { AuditEntry } from '@/types/audit'

export function list(filters: { event?: string; actor_email?: string; client_id?: string }, limit = 20, offset = 0) {
  return api<ListResponse<AuditEntry>>('/api/v1/admin/audit', { query: { ...filters, limit, offset } })
}
