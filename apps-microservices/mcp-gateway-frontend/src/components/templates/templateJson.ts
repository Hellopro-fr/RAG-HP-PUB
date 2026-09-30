// Pure helpers behind the "Créer un template" page: parse a template JSON file
// (single row, export envelope or bare array) and convert between the export
// row the gateway expects and the text-based form the admin edits.
import type { TemplateExportRow } from '@/types/templates'

export interface TemplateForm {
  slug: string
  name: string
  description: string
  icon: string
  kind: 'stdio' | 'http_batch'
  runner: 'google' | 'neo4j'
  stdio_command: string
  // One argument per line.
  stdio_args: string
  tool_prefix: string
  // Comma-separated.
  tags: string
  // Pretty JSON text.
  default_env: string
  required_extra_env: string
  is_active: boolean
}

export function parseTemplateJson(text: string): { rows: TemplateExportRow[] } | { error: string } {
  let data: unknown
  try {
    data = JSON.parse(text)
  } catch {
    return { error: 'Fichier JSON invalide' }
  }
  let items: unknown[]
  if (Array.isArray(data)) {
    items = data
  } else if (data && typeof data === 'object') {
    const envelope = (data as { templates?: unknown }).templates
    items = Array.isArray(envelope) ? envelope : [data]
  } else {
    return { error: 'Le fichier ne contient aucun template' }
  }
  if (items.length === 0) {
    return { error: 'Aucun template trouvé dans le fichier' }
  }
  for (let i = 0; i < items.length; i++) {
    const item = items[i] as { slug?: unknown } | null
    if (!item || typeof item !== 'object' || typeof item.slug !== 'string' || !item.slug.trim()) {
      return { error: `Template n°${i + 1} sans slug` }
    }
  }
  return { rows: items as TemplateExportRow[] }
}

export function emptyTemplateForm(): TemplateForm {
  return {
    slug: '',
    name: '',
    description: '',
    icon: '',
    kind: 'stdio',
    runner: 'google',
    stdio_command: '',
    stdio_args: '',
    tool_prefix: '',
    tags: '',
    default_env: '{}',
    required_extra_env: '[]',
    is_active: true
  }
}

export function rowToForm(row: Partial<TemplateExportRow>): TemplateForm {
  return {
    slug: row.slug ?? '',
    name: row.name ?? '',
    description: row.description ?? '',
    icon: row.icon ?? '',
    kind: row.kind === 'http_batch' ? 'http_batch' : 'stdio',
    runner: row.runner === 'neo4j' ? 'neo4j' : 'google',
    stdio_command: row.stdio_command ?? '',
    stdio_args: (row.stdio_args ?? []).join('\n'),
    tool_prefix: row.tool_prefix ?? '',
    tags: (row.tags ?? []).join(', '),
    default_env: JSON.stringify(row.default_env ?? {}, null, 2),
    required_extra_env: JSON.stringify(row.required_extra_env ?? [], null, 2),
    is_active: row.is_active ?? true
  }
}

export function formToRow(form: TemplateForm): { row: TemplateExportRow } | { error: string } {
  let defaultEnv: unknown
  try {
    defaultEnv = JSON.parse(form.default_env.trim() || '{}')
  } catch {
    return { error: 'default_env : JSON invalide' }
  }
  if (
    !defaultEnv ||
    typeof defaultEnv !== 'object' ||
    Array.isArray(defaultEnv) ||
    Object.values(defaultEnv).some(v => typeof v !== 'string')
  ) {
    return { error: 'default_env : un objet {"CLE": "valeur"} (valeurs texte) est attendu' }
  }
  let required: unknown
  try {
    required = JSON.parse(form.required_extra_env.trim() || '[]')
  } catch {
    return { error: 'required_extra_env : JSON invalide' }
  }
  if (!Array.isArray(required)) {
    return { error: 'required_extra_env : un tableau est attendu' }
  }
  return {
    row: {
      slug: form.slug.trim(),
      name: form.name.trim(),
      description: form.description,
      icon: form.icon,
      stdio_command: form.stdio_command.trim(),
      stdio_args: form.stdio_args.split('\n').map(s => s.trim()).filter(Boolean),
      default_env: defaultEnv as Record<string, string>,
      required_extra_env: required as Array<Record<string, unknown>>,
      tool_prefix: form.tool_prefix,
      tags: form.tags.split(',').map(s => s.trim()).filter(Boolean),
      kind: form.kind,
      runner: form.runner,
      is_active: form.is_active
    }
  }
}
