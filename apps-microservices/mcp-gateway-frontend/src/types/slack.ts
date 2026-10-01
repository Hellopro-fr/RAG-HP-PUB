// Slack notifications admin types — mirror the mcp-gateway-service Go types
// under internal/api/slack_handlers.go. The webhook URL itself is never
// exposed over the API; only the enabled flag and optional env label.

export interface SlackStatus {
  enabled: boolean
  env_label: string
}

export type SlackTestStatus = 'ok' | 'disabled' | 'error'

export interface SlackTestResponse {
  status: SlackTestStatus
  message: string
}
