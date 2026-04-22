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
  credentials: File
  tags?: string[]
  icon?: string
  tool_prefix?: string
  auto_discover?: boolean
}
