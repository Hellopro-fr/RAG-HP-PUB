import { api } from './client'
import { ApiError } from '@/types/api'
import type {
  ZohoImportRow,
  ZohoImportListResponse,
  ZohoImportUpdateRequest,
  ZohoImportTestResponse,
  ZohoAdminUpsertRequest,
  ZohoUserCreateRequest,
} from '@/types/zoho'

const BASE = '/api/v1/zoho-imports'

export interface ListParams {
  isAdmin?: boolean
  search?: string
  page?: number
  limit?: number
}

export const zohoImportsApi = {
  list(params: ListParams = {}): Promise<ZohoImportListResponse> {
    const qs: Record<string, string> = {}
    if (params.isAdmin !== undefined) qs.is_admin = String(params.isAdmin)
    if (params.search) qs.search = params.search
    if (params.page !== undefined) qs.page = String(params.page)
    if (params.limit !== undefined) qs.limit = String(params.limit)
    return api.get<ZohoImportListResponse>(BASE, qs)
  },

  getByID(id: string): Promise<ZohoImportRow> {
    return api.get<ZohoImportRow>(`${BASE}/${encodeURIComponent(id)}`)
  },

  patch(id: string, patch: ZohoImportUpdateRequest): Promise<ZohoImportRow> {
    return api.patch<ZohoImportRow>(`${BASE}/${encodeURIComponent(id)}`, patch)
  },

  remove(id: string): Promise<void> {
    return api.del<void>(`${BASE}/${encodeURIComponent(id)}`)
  },

  test(id: string): Promise<ZohoImportTestResponse> {
    return api.post<ZohoImportTestResponse>(`${BASE}/${encodeURIComponent(id)}/test`, {})
  },

  discover(id: string): Promise<{ ok: boolean; tools: number }> {
    return api.post<{ ok: boolean; tools: number }>(`${BASE}/${encodeURIComponent(id)}/discover`, {})
  },

  create(payload: ZohoUserCreateRequest): Promise<ZohoImportRow> {
    return api.post<ZohoImportRow>(BASE, payload)
  },

  getAdmin(): Promise<ZohoImportRow | null> {
    return api.get<ZohoImportRow>(`${BASE}/admin`).catch((e: unknown) => {
      if (e instanceof ApiError && e.status === 404) {
        return null
      }
      throw e
    })
  },

  upsertAdmin(payload: ZohoAdminUpsertRequest): Promise<ZohoImportRow> {
    return api.post<ZohoImportRow>(`${BASE}/admin`, payload)
  },

  deleteAdmin(): Promise<void> {
    return api.del<void>(`${BASE}/admin`)
  },
}
