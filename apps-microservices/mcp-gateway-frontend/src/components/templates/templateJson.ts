// Pure helpers behind the "Créer un template" page: parse a template JSON file
// (single row, export envelope or bare array) and convert between the export
// row the gateway expects and the text-based form the admin edits.
import type { TemplateExportRow } from '@/types/templates'

export interface TemplateForm {
  slug: string
  name: string
  description: string
  icon: string
  // Plain strings: an unknown value from an imported file is kept as-is so
  // the gateway answers 400 instead of the UI silently rewriting it.
  kind: string
  runner: string
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

// Imported files are untrusted: coerce every field to the type the form needs.
function str(v: unknown): string {
  if (typeof v === 'string') return v
  if (typeof v === 'number') return String(v)
  return ''
}

function strList(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : []
}

export function rowToForm(row: Partial<TemplateExportRow>): TemplateForm {
  const r = row as Record<string, unknown>
  const env = r.default_env
  const required = r.required_extra_env
  return {
    slug: str(r.slug),
    name: str(r.name),
    description: str(r.description),
    icon: str(r.icon),
    kind: str(r.kind) || 'stdio',
    runner: str(r.runner) || 'google',
    stdio_command: str(r.stdio_command),
    stdio_args: strList(r.stdio_args).join('\n'),
    tool_prefix: str(r.tool_prefix),
    tags: strList(r.tags).join(', '),
    default_env: JSON.stringify(env && typeof env === 'object' && !Array.isArray(env) ? env : {}, null, 2),
    required_extra_env: JSON.stringify(Array.isArray(required) ? required : [], null, 2),
    is_active: typeof r.is_active === 'boolean' ? r.is_active : true
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
      kind: form.kind as TemplateExportRow['kind'],
      runner: form.runner as TemplateExportRow['runner'],
      is_active: form.is_active
    }
  }
}
