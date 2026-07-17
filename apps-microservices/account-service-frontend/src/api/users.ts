import { api } from './client'
import type { ListResponse } from '@/types/oauth2'

export interface AdminUser {
  email: string
  display_name?: string
  is_admin: boolean
  is_allowed: boolean
  last_login_at?: string
  created_at: string
}

export interface AdminSession {
  id: string
  sid: string
  client_id: string
  created_at: string
  last_used_at?: string
  expires_at: string
  revoked: boolean
  revoked_reason?: string
}

export function list(limit = 20, offset = 0) {
  return api<ListResponse<AdminUser>>('/api/v1/admin/users', { query: { limit, offset } })
}
export function promote(email: string) {
  return api<{ status: string }>(`/api/v1/admin/users/${encodeURIComponent(email)}/promote`, { method: 'POST' })
}
export function demote(email: string) {
  return api<{ status: string }>(`/api/v1/admin/users/${encodeURIComponent(email)}/demote`, { method: 'POST' })
}
export function block(email: string) {
  return api<{ status: string }>(`/api/v1/admin/users/${encodeURIComponent(email)}/block`, { method: 'POST' })
}
export function unblock(email: string) {
  return api<{ status: string }>(`/api/v1/admin/users/${encodeURIComponent(email)}/unblock`, { method: 'POST' })
}
export function revoke(email: string) {
  return api<{ status: string }>(`/api/v1/admin/users/${encodeURIComponent(email)}/revoke`, { method: 'POST' })
}

export function listSessions(email: string) {
  return api<{ items: AdminSession[]; total: number }>(`/api/v1/admin/users/${encodeURIComponent(email)}/sessions`)
}
export function revokeSession(sid: string) {
  return api<{ status: string }>(`/api/v1/admin/sessions/${encodeURIComponent(sid)}/revoke`, { method: 'POST' })
}
