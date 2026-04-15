export interface InstallOption {
  label: string
  note?: string
  code?: string
  noNumber?: boolean
}

export type ExecutorElementType = 'os-install' | 'verify' | 'mcp-config' | 'cli-command' | 'note' | 'text' | 'divider'

export interface ExecutorElement {
  id: string
  type: ExecutorElementType
  props: Record<string, any>
}

export interface InstallExecutor {
  id: number
  slug: string
  label: string
  sub: string
  description: string
  intro: string
  icon: string
  color: string
  install: Record<string, InstallOption[]>
  verify: string
  mcp_config: string
  cli_add_cmd: string
  note_label: string
  note_text: string
  note_class: string
  content: ExecutorElement[]
  display_order: number
  is_active: boolean
}

export interface ConfigStepTable {
  field: string
  value: string
}

export interface ConfigStep {
  title: string
  description: string
  code?: string
  codeField?: string
  hasExecutorSelector?: boolean
  table?: ConfigStepTable[]
}

export interface InstallConfig {
  id: number
  slug: string
  label: string
  description: string
  icon: string
  color: string
  content: ConfigStep[]
  display_order: number
  is_active: boolean
}
