export interface InstallOption {
  label: string
  note?: string
  code?: string
  noNumber?: boolean
}

export type ExecutorElementType = 'os-install' | 'verify' | 'mcp-config' | 'cli-command' | 'note' | 'text' | 'divider'

// Props shape covers every element type in a single optional bag — keeps
// the legacy `el.props.foo` access pattern working everywhere without a
// discriminated narrowing on every call site. Extend as new element types
// land.
export interface ExecutorElementProps {
  title?: string
  code?: string
  text?: string
  label?: string
  content?: string
  cssClass?: string
  // Legacy alias still used by InstallConfigDetailView; keep until the
  // backend is normalised to `cssClass` everywhere.
  class?: string
  // Only set for `os-install` elements — keyed by OS id ('linux'|'mac'|...).
  install?: Record<string, InstallOption[]>
}

export interface ExecutorElement {
  id: string
  type: ExecutorElementType
  props: ExecutorElementProps
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
  created_at?: string
  updated_at?: string
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
  // UI-only sentinel added by the StepBuilder while editing — survives
  // round-trips so drag/drop key tracking stays stable.
  _id?: string
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
  created_at?: string
  updated_at?: string
}
