import { describe, it, expect } from 'vitest'
import {
  emptyTemplateForm,
  formToRow,
  parseTemplateJson,
  rowToForm
} from './templateJson'
import type { TemplateExportRow } from '@/types/templates'

const row: TemplateExportRow = {
  slug: 'neo4j',
  name: 'Neo4j',
  description: 'Graph',
  icon: 'pi pi-share-alt',
  stdio_command: 'mcp-proxy',
  stdio_args: ['--port', '8000'],
  default_env: { NEO4J_READ_ONLY: 'true' },
  required_extra_env: [{ key: 'K', label: 'L', required: true }],
  tool_prefix: 'neo4j',
  tags: ['graph', 'db'],
  kind: 'stdio',
  runner: 'neo4j',
  is_active: true
}

describe('parseTemplateJson', () => {
  it('accepts a single row object', () => {
    expect(parseTemplateJson(JSON.stringify(row))).toEqual({ rows: [row] })
  })

  it('accepts an export envelope', () => {
    const r = parseTemplateJson(JSON.stringify({ version: 1, templates: [row, { ...row, slug: 'b' }] }))
    expect('rows' in r && r.rows.map(x => x.slug)).toEqual(['neo4j', 'b'])
  })

  it('accepts a bare array', () => {
    const r = parseTemplateJson(JSON.stringify([row]))
    expect('rows' in r && r.rows).toHaveLength(1)
  })

  it('rejects invalid JSON in French', () => {
    const r = parseTemplateJson('{nope')
    expect('error' in r && r.error).toMatch(/JSON invalide/)
  })

  it('rejects an empty envelope', () => {
    const r = parseTemplateJson('{"templates":[]}')
    expect('error' in r && r.error).toMatch(/Aucun template/)
  })

  it('rejects a row without slug', () => {
    const r = parseTemplateJson('{"name":"X"}')
    expect('error' in r && r.error).toMatch(/slug/)
  })

  it('rejects a scalar', () => {
    expect('error' in parseTemplateJson('42')).toBe(true)
  })
})

describe('rowToForm / formToRow', () => {
  it('round-trips a full row', () => {
    const form = rowToForm(row)
    expect(form.stdio_args).toBe('--port\n8000')
    expect(form.tags).toBe('graph, db')
    expect(JSON.parse(form.default_env)).toEqual(row.default_env)
    expect(formToRow(form)).toEqual({ row })
  })

  it('fills defaults for a sparse row', () => {
    const form = rowToForm({ slug: 'a', name: 'A' } as Partial<TemplateExportRow>)
    expect(form.kind).toBe('stdio')
    expect(form.runner).toBe('google')
    expect(form.is_active).toBe(true)
    expect(formToRow(form)).toMatchObject({
      row: { stdio_args: [], tags: [], default_env: {}, required_extra_env: [] }
    })
  })

  it('emptyTemplateForm starts active, stdio, google', () => {
    const f = emptyTemplateForm()
    expect(f).toMatchObject({ slug: '', kind: 'stdio', runner: 'google', is_active: true })
  })

  it('names default_env when its JSON is invalid', () => {
    const r = formToRow({ ...emptyTemplateForm(), default_env: '{oops' })
    expect('error' in r && r.error).toMatch(/default_env/)
  })

  it('names default_env when it is not an object of strings', () => {
    const r = formToRow({ ...emptyTemplateForm(), default_env: '{"A":1}' })
    expect('error' in r && r.error).toMatch(/default_env/)
    const r2 = formToRow({ ...emptyTemplateForm(), default_env: '[]' })
    expect('error' in r2 && r2.error).toMatch(/default_env/)
  })

  it('names required_extra_env when it is not an array', () => {
    const r = formToRow({ ...emptyTemplateForm(), required_extra_env: '{}' })
    expect('error' in r && r.error).toMatch(/required_extra_env/)
    const r2 = formToRow({ ...emptyTemplateForm(), required_extra_env: '[' })
    expect('error' in r2 && r2.error).toMatch(/required_extra_env/)
  })

  it('trims slug/name and drops blank args and tags', () => {
    const r = formToRow({
      ...emptyTemplateForm(),
      slug: ' a ',
      name: ' A ',
      stdio_args: 'x\n\n y \n',
      tags: ' t1 , ,t2'
    })
    expect(r).toMatchObject({ row: { slug: 'a', name: 'A', stdio_args: ['x', 'y'], tags: ['t1', 't2'] } })
  })
})
