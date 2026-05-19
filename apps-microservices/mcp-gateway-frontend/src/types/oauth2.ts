import type { ServerToolScope } from './token'
import type { LeexiFilter, ZohoFilter } from './leexi'
import type { RingoverFilter } from './ringover'
import type { BDDFilter } from './bdd'

export interface OAuth2Client {
  id: string
  name: string
  description?: string
  client_secret?: string
  secret_prefix: string
  server_ids: string[]
  server_tools: ServerToolScope[]
  instruction_ids?: string[]
  access_token_ttl: number
  is_active: boolean
  created_by?: string
  created_at: string
  updated_at: string
  expires_at?: string
  redirect_uris?: string[]
  grant_types?: string[]
  dynamically_registered: boolean
  leexi_filter?: LeexiFilter
  zoho_filter?: ZohoFilter
  ringover_filter?: RingoverFilter
  bdd_filter?: BDDFilter
}

export interface OAuth2ClientListResponse {
  clients: OAuth2Client[]
}

export interface CreateOAuth2ClientRequest {
  name: string
  description?: string
  redirect_uris?: string[]
  server_ids: string[]
  server_tools?: ServerToolScope[]
  instruction_ids?: string[]
  access_token_ttl?: number
  expires_at?: string
  leexi_filter?: LeexiFilter
  zoho_filter?: ZohoFilter
  ringover_filter?: RingoverFilter
  bdd_filter?: BDDFilter
}

export interface UpdateOAuth2ClientRequest extends Partial<CreateOAuth2ClientRequest> {}

export interface AuthorizeInfo {
  client_name: string
  servers: AuthorizeServer[]
  has_session: boolean
  has_consent: boolean
  csrf_token?: string
}

export interface AuthorizeServer {
  id: string
  name: string
  tools: AuthorizeTool[]
  configured?: boolean
  docs_url?: string
}

export interface AuthorizeTool {
  name: string
  description?: string
}

export interface AuthorizeLoginRequest {
  username: string
  password: string
  client_id: string
  redirect_uri: string
  code_challenge: string
  code_challenge_method: string
  state: string
}

export interface AuthorizeLoginResponse {
  success: boolean
  client_name: string
  servers: AuthorizeServer[]
  csrf_token: string
  error?: string
}

export interface AuthorizeConsentRequest {
  client_id: string
  redirect_uri: string
  code_challenge: string
  code_challenge_method: string
  state: string
  csrf_token: string
  server_ids: string[]
  tool_ids?: string[]
}

export interface AuthorizeConsentResponse {
  redirect_url: string
}
