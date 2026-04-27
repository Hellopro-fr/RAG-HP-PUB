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
  description: string
  upstream_field_id?: number
  created_at?: string
  updated_at?: string
}

export interface BDDUsedTable {
  id: string
  database_id: number
  table_name: string
  description: string
  upstream_table_id?: number
  created_by?: string
  created_at?: string
  updated_at?: string
  fields: BDDUsedField[]
}

export interface BDDFilter { used_table_ids: string[] }
