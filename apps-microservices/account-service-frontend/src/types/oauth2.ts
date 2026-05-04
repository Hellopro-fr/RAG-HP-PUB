export interface OAuth2Client {
  id: string
  client_id: string
  name: string
  description?: string
  logo_url?: string
  brand_color?: string
  redirect_uris: string[] | null
  allowed_roles: string[] | null
  logout_webhook_url?: string
  token_ttl_s: number
  refresh_ttl_s: number
  claim_mappings: Record<string, string> | null
  scope?: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface OAuth2ClientCreatePayload {
  name: string
  description?: string
  logo_url?: string
  brand_color?: string
  redirect_uris: string[]
  allowed_roles?: string[]
  logout_webhook_url?: string
  token_ttl_s?: number
  refresh_ttl_s?: number
  claim_mappings?: Record<string, string>
  scope?: string
}

export interface OAuth2ClientCreateResponse {
  id: string
  client_id: string
  client_secret: string
  name: string
  redirect_uris: string[]
}

export interface ListResponse<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}
