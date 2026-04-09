import { api } from './client'
import type { AuditLogResult } from '@/types/audit'

const BASE = '/api/v1'

export interface AuditFilter {
  user_email?: string
  action?: string
  resource_type?: string
  date_from?: string
  date_to?: string
  page?: number
  per_page?: number
}

export const auditApi = {
  list(filter: AuditFilter = {}): Promise<AuditLogResult> {
    const params: Record<string, string> = {}
    Object.entries(filter).forEach(([key, value]) => {
      if (value !== undefined && value !== '') {
        params[key] = String(value)
      }
    })
    return api.get<AuditLogResult>(`${BASE}/audit-logs`, Object.keys(params).length ? params : undefined)
  }
}
