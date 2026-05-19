import type { LeexiFilter, ZohoFilter } from './leexi'
import type { RingoverFilter } from './ringover'
import type { BDDFilter } from './bdd'

export interface ServerToolScope {
  server_id: string
  tool_names: string[]
}

export interface ScopeToken {
  id: string
  name: string
  description?: string
  token?: string
  token_prefix: string
  server_ids: string[]
  server_tools: ServerToolScope[]
  instruction_ids?: string[]
  mcp_command: string
  server_name?: string
  allow_http?: boolean
  is_active: boolean
  created_by?: string
  created_at: string
  updated_at: string
  expires_at?: string
  leexi_filter?: LeexiFilter
  zoho_filter?: ZohoFilter
  ringover_filter?: RingoverFilter
  bdd_filter?: BDDFilter
}

export interface TokenListResponse {
  tokens: ScopeToken[]
}

export interface CreateTokenRequest {
  name: string
  description?: string
  server_ids: string[]
  server_tools?: ServerToolScope[]
  instruction_ids?: string[]
  mcp_command?: string
  server_name?: string
  expires_at?: string
  allow_http?: boolean
  leexi_filter?: LeexiFilter
  zoho_filter?: ZohoFilter
  ringover_filter?: RingoverFilter
  bdd_filter?: BDDFilter
}

export interface UpdateTokenRequest extends Partial<CreateTokenRequest> {}
