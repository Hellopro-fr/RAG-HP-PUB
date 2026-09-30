import type { Neo4jConnectionInput } from '@/components/templates/neo4jConnection'

// Google Templates types — mirror Go DTOs in
// apps-microservices/mcp-gateway-service/internal/api/template_dto.go.
// Field names use snake_case to match the JSON wire format.

export interface RequiredExtraEnvField {
  key: string
  label: string
  required: boolean
}

export interface Template {
  slug: string
  name: string
  description: string
  icon: string
  stdio_command: string
  stdio_args: string[]
  default_env?: Record<string, string>
  required_extra_env: RequiredExtraEnvField[]
  tool_prefix: string
  tags: string[]
  // Template category:
  //   'stdio'      — spawns a subprocess via the runner (ga, gsc, ...)
  //   'http_batch' — catalog shortcut that routes to the generic Google Sheets
  //                  server-import flow (no template instance / runner involvement)
  kind: 'stdio' | 'http_batch'
  // Runner hosting the instances: 'google' (mcp-google-templates-runner) or
  // 'neo4j' (mcp-template-neo4j-service). Absent on older gateways = 'google'.
  runner?: 'google' | 'neo4j'
  instance_count: number
}

export type InstanceStatus = 'pending' | 'running' | 'failed' | 'stopped'

export interface TemplateInstance {
  id: string
  template_slug: string
  name: string
  extra_env?: Record<string, string>
  runner_port?: number
  runner_status: InstanceStatus
  runner_last_error?: string
  mcp_server_id: string
  url?: string
  created_by: string
  created_at: string
  updated_at: string
  stderr_tail?: string
}

export interface TemplateListResponse {
  templates: Template[]
}

export interface TemplateInstanceListResponse {
  instances: TemplateInstance[]
}

export interface CreateInstanceParams {
  template_slug: string
  name: string
  extra_env?: Record<string, string>
  // Google templates: service-account JSON file.
  credentials?: File
  // Neo4j templates: connection fields (sent instead of `credentials`).
  neo4j?: Neo4jConnectionInput
  tags?: string[]
  icon?: string
  tool_prefix?: string
  auto_discover?: boolean
}

export interface RotateNeo4jParams {
  neo4j: Neo4jConnectionInput
  extra_env?: Record<string, string>
}
