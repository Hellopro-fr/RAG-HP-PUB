import { api } from './client'
import type {
  BDDDatabase,
  BDDCatalogTable,
  BDDCatalogField,
  BDDUsedTable,
  BDDUsedField,
  BDDUsedListResponse,
} from '@/types/bdd'

const BASE = '/api/v1'

export interface BDDUsedListParams {
  database_id?: number  // omit or 0 = all
  search?: string
  page?: number          // default 1
  limit?: number         // default 20
}

export const bddApi = {
  // catalog (read-only proxy — gateway -> upstream)
  catalogDatabases: () =>
    api.get<{ databases: BDDDatabase[] }>(`${BASE}/bdd/catalog/databases`),
  catalogTables: (db: number, search = '') =>
    api.get<{ tables: BDDCatalogTable[] }>(
      `${BASE}/bdd/catalog/databases/${db}/tables`,
      search ? { search } : undefined,
    ),
  catalogFields: (db: number, upstreamTableId: number) =>
    api.get<{ fields: BDDCatalogField[] }>(
      `${BASE}/bdd/catalog/databases/${db}/tables/${upstreamTableId}/fields`,
    ),

  // gateway-owned registry (CRUD)
  listUsed: (params: BDDUsedListParams = {}) => {
    const query: Record<string, string> = {}
    if (params.database_id !== undefined && params.database_id !== 0) {
      query.database_id = String(params.database_id)
    }
    if (params.search) {
      query.search = params.search
    }
    if (params.page !== undefined) {
      query.page = String(params.page)
    }
    if (params.limit !== undefined) {
      query.limit = String(params.limit)
    }
    return api.get<BDDUsedListResponse>(
      `${BASE}/bdd/used/tables`,
      Object.keys(query).length > 0 ? query : undefined,
    )
  },
  getUsed: (id: string) =>
    api.get<BDDUsedTable>(`${BASE}/bdd/used/tables/${id}`),
  createUsed: (body: {
    database_id: number
    table_name: string
    description?: string
    upstream_table_id?: number
    fields: { field_name: string; description?: string; upstream_field_id?: number }[]
  }) => api.post<BDDUsedTable>(`${BASE}/bdd/used/tables`, body),
  patchUsed: (id: string, body: { description: string }) =>
    api.patch<BDDUsedTable>(`${BASE}/bdd/used/tables/${id}`, body),
  deleteUsed: (id: string) =>
    api.del<void>(`${BASE}/bdd/used/tables/${id}`),
  addField: (id: string, body: { field_name: string; description?: string; upstream_field_id?: number }) =>
    api.post<BDDUsedField>(`${BASE}/bdd/used/tables/${id}/fields`, body),
  patchField: (id: string, fid: string, body: { description: string }) =>
    api.patch<BDDUsedField>(`${BASE}/bdd/used/tables/${id}/fields/${fid}`, body),
  deleteField: (id: string, fid: string) =>
    api.del<void>(`${BASE}/bdd/used/tables/${id}/fields/${fid}`),
}
