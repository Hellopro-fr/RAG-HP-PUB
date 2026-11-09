import { api } from './client'

export interface AdminGroup {
  id: string
  name: string
  description: string
  member_count: number
  created_by?: string
  created_at: string
  updated_at: string
}

export interface AdminGroupMember {
  email: string
  display_name?: string
  is_allowed: boolean
  added_by?: string
  added_at: string
}

export interface AdminGroupDetail extends AdminGroup {
  members: AdminGroupMember[]
}

const base = '/api/v1/admin/groups'

export function list() {
  return api<{ items: AdminGroup[]; total: number }>(base)
}
export function get(id: string) {
  return api<AdminGroupDetail>(`${base}/${encodeURIComponent(id)}`)
}
export function create(name: string, description: string) {
  return api<AdminGroup>(base, { method: 'POST', body: { name, description } })
}
export function update(id: string, name: string, description: string) {
  return api<AdminGroup>(`${base}/${encodeURIComponent(id)}`, { method: 'PUT', body: { name, description } })
}
export function remove(id: string) {
  return api<void>(`${base}/${encodeURIComponent(id)}`, { method: 'DELETE' })
}
export function addMember(id: string, email: string) {
  return api<{ status: string }>(`${base}/${encodeURIComponent(id)}/members`, { method: 'POST', body: { email } })
}
export function removeMember(id: string, email: string) {
  return api<void>(`${base}/${encodeURIComponent(id)}/members/${encodeURIComponent(email)}`, { method: 'DELETE' })
}
