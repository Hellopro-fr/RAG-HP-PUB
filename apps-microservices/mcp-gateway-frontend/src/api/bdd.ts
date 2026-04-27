import { api } from './client'
import type {
  BDDDatabase,
  BDDCatalogTable,
  BDDCatalogField,
  BDDUsedTable,
  BDDUsedField,
} from '@/types/bdd'

export const bddApi = {
  // catalog (read-only proxy — gateway -> upstream)
  catalogDatabases: () =>
    api.get<{ databases: BDDDatabase[] }>('/api/v1/bdd/catalog/databases'),
  catalogTables: (db: number, search = '') => {
    const qs = search ? `?search=${encodeURIComponent(search)}` : ''
    return api.get<{ tables: BDDCatalogTable[] }>(`/api/v1/bdd/catalog/databases/${db}/tables${qs}`)
  },
  catalogFields: (db: number, upstreamTableId: number) =>
    api.get<{ fields: BDDCatalogField[] }>(
      `/api/v1/bdd/catalog/databases/${db}/tables/${upstreamTableId}/fields`,
    ),

  // gateway-owned registry (CRUD)
  listUsed: (database_id?: number, search = '') => {
    const params = [
      database_id !== undefined ? `database_id=${database_id}` : '',
      search ? `search=${encodeURIComponent(search)}` : '',
    ].filter(Boolean).join('&')
    const suffix = params ? `?${params}` : ''
    return api.get<{ tables: BDDUsedTable[] }>(`/api/v1/bdd/used/tables${suffix}`)
  },
  getUsed: (id: string) =>
    api.get<BDDUsedTable>(`/api/v1/bdd/used/tables/${id}`),
  createUsed: (body: {
    database_id: number
    table_name: string
    description?: string
    upstream_table_id?: number
    fields: { field_name: string; description?: string; upstream_field_id?: number }[]
  }) => api.post<BDDUsedTable>('/api/v1/bdd/used/tables', body),
  patchUsed: (id: string, body: { description: string }) =>
    api.patch<BDDUsedTable>(`/api/v1/bdd/used/tables/${id}`, body),
  deleteUsed: (id: string) =>
    api.del<void>(`/api/v1/bdd/used/tables/${id}`),
  addField: (id: string, body: { field_name: string; description?: string; upstream_field_id?: number }) =>
    api.post<BDDUsedField>(`/api/v1/bdd/used/tables/${id}/fields`, body),
  patchField: (id: string, fid: string, body: { description: string }) =>
    api.patch<BDDUsedField>(`/api/v1/bdd/used/tables/${id}/fields/${fid}`, body),
  deleteField: (id: string, fid: string) =>
    api.del<void>(`/api/v1/bdd/used/tables/${id}/fields/${fid}`),
}
