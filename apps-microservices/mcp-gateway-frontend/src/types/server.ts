export interface ServerToolName {
  name: string
  description?: string
  is_active: boolean
}

export interface ServerTool {
  name: string
  description?: string
  input_schema?: Record<string, unknown>
  is_active: boolean
}

export interface ServerResource {
  uri: string
  name: string
  description?: string
  mime_type?: string
}

export interface PromptArgument {
  name: string
  description?: string
  is_required: boolean
}

export interface ServerPrompt {
  name: string
  description?: string
  arguments?: PromptArgument[]
}

export interface Server {
  id: string
  name: string
  url: string
  message_url: string
  transport_type: string
  server_name: string
  server_version: string
  transport_preference: string
  connect_timeout_ms: number
  is_active: boolean
  health_status: string
  last_health_check?: string
  last_error?: string
  last_discovered_at?: string
  tool_prefix: string
  tools_count: number
  tool_names: ServerToolName[]
  resources_count: number
  prompts_count: number
  tags: string[]
  mcp_transport: string
  mcp_command?: string
  mcp_args?: string[]
  mcp_env?: Record<string, string>
  has_auth_headers: boolean
  created_by?: string
  created_at: string
  updated_at: string
}

export interface ServerDetail extends Server {
  tools: ServerTool[]
  resources: ServerResource[]
  prompts: ServerPrompt[]
}

export interface ServerListResponse {
  servers: Server[]
  total: number
}

export interface CreateServerRequest {
  name: string
  url?: string
  transport_type?: string
  transport_preference?: string
  connect_timeout_ms?: number
  mcp_transport?: string
  mcp_command?: string
  mcp_args?: string[]
  mcp_env?: Record<string, string>
  auth_headers?: Record<string, string>
  tags?: string[]
  tool_prefix?: string
  auto_discover?: boolean
}

export interface UpdateServerRequest extends Partial<CreateServerRequest> {}

export interface ImportResult {
  imported: number
  skipped: number
  errors: number
  details: ImportResultDetail[]
}

export interface ImportResultDetail {
  name: string
  status: 'imported' | 'skipped' | 'error'
  message?: string
}
