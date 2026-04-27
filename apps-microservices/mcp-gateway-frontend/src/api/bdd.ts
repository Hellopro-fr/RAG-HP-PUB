import { api } from './client'
import type {
  BDDDatabase,
  BDDCatalogTable,
  BDDCatalogField,
  BDDUsedTable,
  BDDUsedField,
} from '@/types/bdd'

const BASE = '/api/v1'

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
  listUsed: (database_id?: number, search = '') => {
    const params: Record<string, string> = {}
    if (database_id !== undefined) params.database_id = String(database_id)
    if (search) params.search = search
    return api.get<{ tables: BDDUsedTable[] }>(
      `${BASE}/bdd/used/tables`,
      Object.keys(params).length > 0 ? params : undefined,
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
