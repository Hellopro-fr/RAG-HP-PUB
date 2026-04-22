export interface PublicServerSummary {
  id: string
  name: string
  server_name: string
  server_version: string
  health_status: string
  tools_count: number
  active_tools_count: number
  resources_count: number
  prompts_count: number
  tags: string[]
}

export interface PublicServerDetail {
  id: string
  name: string
  server_name: string
  server_version: string
  tools_count: number
  tags: string[]
  tools: PublicToolDetail[]
  resources: PublicResourceDetail[]
  prompts: PublicPromptDetail[]
}

export interface PublicToolDetail {
  name: string
  description: string
  input_schema: JsonSchema
}

export interface PublicResourceDetail {
  name: string
  description: string
  mime_type: string
  uri: string
}

export interface PublicPromptDetail {
  name: string
  description: string
  arguments: { name: string; description: string; is_required: boolean }[]
}

export interface JsonSchema {
  type?: string
  properties?: Record<string, JsonSchemaProperty>
  required?: string[]
  description?: string
  [key: string]: unknown
}

export interface JsonSchemaProperty {
  type?: string | string[]
  description?: string
  enum?: unknown[]
  default?: unknown
  items?: JsonSchemaProperty
  properties?: Record<string, JsonSchemaProperty>
  required?: string[]
  oneOf?: JsonSchemaProperty[]
  anyOf?: JsonSchemaProperty[]
  [key: string]: unknown
}

export interface PublicServersListResponse {
  servers: PublicServerSummary[]
  total: number
}
