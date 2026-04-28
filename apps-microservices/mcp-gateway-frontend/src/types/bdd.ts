export const HELLOPRO_DATABASES = [
  { id: 1,  name: 'Hellopro BO',   slug: 'bo'   },
  { id: 5,  name: 'Hellopro Data', slug: 'data' },
  { id: 10, name: 'Hellopro IA',   slug: 'ia'   },
] as const

export type HelloproDatabase   = typeof HELLOPRO_DATABASES[number]
export type HelloproDatabaseId = HelloproDatabase['id']

export interface BDDDatabase     { id: number; name: string }

export interface BDDCatalogTable {
  id: number
  database_id: number
  table_name: string
  description?: string
  field_count?: number
}

export interface BDDCatalogField {
  id: number
  table_id: number
  field_name: string
  field_type?: string
  is_nullable?: boolean
  description?: string
}

export interface BDDUsedField {
  id: string
  used_table_id: string
  field_name: string
  field_type?: string
  description: string
  upstream_field_id?: number
  created_at?: string
  updated_at?: string
}

// BDDRelations is the persisted shape of the per-table `relations` column.
// Two flavours come back from the upstream catalog: an empty array (no
// relations) and an object keyed by target table. We keep the union as-is
// so round-trips are byte-stable.
export type BDDRelations = Record<string, string> | unknown[] | null

export interface BDDUsedTable {
  id: string
  database_id: number
  table_name: string
  description: string
  upstream_table_id?: number
  rows: number | null
  primary_key: string
  default_order_by: string
  relations: BDDRelations
  notes: string
  is_active: boolean
  created_by?: string
  created_at?: string
  updated_at?: string
  fields: BDDUsedField[]
}

export interface BDDFilter { used_table_ids: string[] }

export interface BDDUsedListResponse {
  tables: BDDUsedTable[]
  total: number
  page: number
  limit: number
}

export interface BDDMeta {
  description: string
  usage: string
  updated_at?: string
  updated_by?: string
}

// Per-column shape inside the doc payload.
export interface BDDDocColumn {
  type: string
  desc: string
}

// Per-table shape inside the doc payload.
export interface BDDDocTable {
  description: string
  rows: number | null
  primary_key: string | null
  default_order_by: string | null
  columns: Record<string, BDDDocColumn>
  relations: BDDRelations
  notes: string
}

// Top-level shape returned by GET /bdd/used/tables/doc — `_meta` plus
// dynamic table-name keys.
export type BDDDocPayload = {
  _meta: { description: string; last_updated: string; usage: string }
} & Record<string, BDDDocTable>
