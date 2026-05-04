import { api } from './client'
import type { ListResponse, OAuth2Client, OAuth2ClientCreatePayload, OAuth2ClientCreateResponse } from '@/types/oauth2'

export function list(limit = 20, offset = 0) {
  return api<ListResponse<OAuth2Client>>('/api/v1/admin/services', { query: { limit, offset } })
}
export function get(id: string) {
  return api<OAuth2Client>(`/api/v1/admin/services/${encodeURIComponent(id)}`)
}
export function create(payload: OAuth2ClientCreatePayload) {
  return api<OAuth2ClientCreateResponse>('/api/v1/admin/services', { method: 'POST', body: payload })
}
export function update(id: string, payload: Partial<OAuth2ClientCreatePayload>) {
  return api<OAuth2Client>(`/api/v1/admin/services/${encodeURIComponent(id)}`, { method: 'PUT', body: payload })
}
export function remove(id: string) {
  return api<void>(`/api/v1/admin/services/${encodeURIComponent(id)}`, { method: 'DELETE' })
}
export function rotateSecret(id: string) {
  return api<{ client_secret: string }>(`/api/v1/admin/services/${encodeURIComponent(id)}/rotate-secret`, { method: 'POST' })
}
export function testWebhook(id: string) {
  return api<{ status: number }>(`/api/v1/admin/services/${encodeURIComponent(id)}/test-webhook`, { method: 'POST' })
}
