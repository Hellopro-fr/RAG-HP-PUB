import { api } from './client'
import type {
  ApiCatalogService,
  CreateApiRequest,
  DetailResp,
  ListResp,
  RescanReport,
  UpdateApiRequest,
} from '@/types/apiCatalog'

const base = '/api/v1/admin/api'

export function list(limit = 100, offset = 0, filter = '') {
  return api<ListResp>(base, { query: { limit, offset, filter } })
}

export function get(id: string) {
  return api<DetailResp>(`${base}/${encodeURIComponent(id)}`)
}

export function create(payload: CreateApiRequest) {
  return api<ApiCatalogService>(base, { method: 'POST', body: payload })
}

export function update(id: string, payload: UpdateApiRequest) {
  return api<ApiCatalogService>(`${base}/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: payload,
  })
}

export function remove(id: string) {
  return api<{ deleted: boolean }>(`${base}/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  })
}

export function rescanAll() {
  return api<RescanReport>(`${base}/rescan`, { method: 'POST' })
}

export function rescanOne(id: string) {
  return api<RescanReport>(`${base}/${encodeURIComponent(id)}/rescan`, {
    method: 'POST',
  })
}
