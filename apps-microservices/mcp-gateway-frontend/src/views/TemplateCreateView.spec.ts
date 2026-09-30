// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const createTemplate = vi.fn()
const fetchTemplates = vi.fn()
const push = vi.fn()
const toastSuccess = vi.fn()
vi.mock('@/api/templates', () => ({ templatesApi: {} }))
vi.mock('@/stores/templates', () => ({
  useTemplatesStore: () => ({ createTemplate, fetchTemplates })
}))
vi.mock('@/stores/servers', () => ({ useServersStore: () => ({ tags: [], fetchTags: vi.fn() }) }))
vi.mock('@/composables/useToast', () => ({
  useToast: () => ({ success: toastSuccess, error: vi.fn(), info: vi.fn() })
}))
vi.mock('@/api/client', () => ({ api: {} }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push }) }))

import TemplateCreateView from './TemplateCreateView.vue'
import { ApiError } from '@/types/api'

function render() {
  return mount(TemplateCreateView, {
    global: { stubs: { IconPicker: true, 'router-link': true } }
  })
}

function fakeFile(content: string): File {
  return { name: 't.json', text: () => Promise.resolve(content) } as unknown as File
}

async function pickFile(w: ReturnType<typeof render>, content: string) {
  const input = w.find('#import-json-file')
  Object.defineProperty(input.element, 'files', { value: [fakeFile(content)], configurable: true })
  await input.trigger('change')
  await flushPromises()
}

const submit = (w: ReturnType<typeof render>) => w.find('#tpl-submit').element as HTMLButtonElement

describe('TemplateCreateView', () => {
  beforeEach(() => {
    createTemplate.mockReset()
    fetchTemplates.mockReset()
    push.mockReset()
    toastSuccess.mockReset()
  })

  it('renders the form fields and disables Créer while slug/name are empty', () => {
    const w = render()
    for (const id of [
      'tpl-slug', 'tpl-name', 'tpl-description', 'tpl-kind', 'tpl-runner', 'tpl-command',
      'tpl-args', 'tpl-tool-prefix', 'tpl-tags', 'tpl-default-env', 'tpl-required-env', 'tpl-active'
    ]) {
      expect(w.find(`#${id}`).exists(), id).toBe(true)
    }
    expect((w.find('#tpl-active').element as HTMLInputElement).checked).toBe(true)
    expect(submit(w).disabled).toBe(true)
  })

  it('enables Créer once slug, name and command are valid', async () => {
    const w = render()
    await w.find('#tpl-slug').setValue('my-tpl')
    await w.find('#tpl-name').setValue('My tpl')
    expect(submit(w).disabled).toBe(true) // stdio needs a command
    await w.find('#tpl-command').setValue('mcp-x')
    expect(submit(w).disabled).toBe(false)
    await w.find('#tpl-slug').setValue('New')
    expect(submit(w).disabled).toBe(true)
  })

  it('prefills the form from a JSON file without saving', async () => {
    const w = render()
    await pickFile(w, JSON.stringify({ slug: 'neo4j', name: 'Neo4j', stdio_command: 'mcp-proxy', runner: 'neo4j', tags: ['a', 'b'] }))
    expect((w.find('#tpl-slug').element as HTMLInputElement).value).toBe('neo4j')
    expect((w.find('#tpl-name').element as HTMLInputElement).value).toBe('Neo4j')
    expect((w.find('#tpl-runner').element as HTMLSelectElement).value).toBe('neo4j')
    expect((w.find('#tpl-tags').element as HTMLInputElement).value).toBe('a, b')
    expect(createTemplate).not.toHaveBeenCalled()
  })

  it('lets the admin pick one template from a multi-row file', async () => {
    const w = render()
    await pickFile(w, JSON.stringify({ templates: [
      { slug: 'a', name: 'A', stdio_command: 'x' },
      { slug: 'b', name: 'B', stdio_command: 'y' }
    ] }))
    expect((w.find('#tpl-slug').element as HTMLInputElement).value).toBe('a')
    expect(w.findAll('#import-pick option').map(o => o.text())).toEqual(['a — A', 'b — B'])
    await w.find('#import-pick').setValue(1)
    expect((w.find('#tpl-slug').element as HTMLInputElement).value).toBe('b')
  })

  it('shows a French error for an invalid file', async () => {
    const w = render()
    await pickFile(w, '{nope')
    expect(w.find('#import-error').text()).toMatch(/JSON invalide/)
  })

  it('creates the template then routes to its detail page', async () => {
    createTemplate.mockResolvedValue({ slug: 'my-tpl' })
    const w = render()
    await w.find('#tpl-slug').setValue('my-tpl')
    await w.find('#tpl-name').setValue('My tpl')
    await w.find('#tpl-command').setValue('mcp-x')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(createTemplate).toHaveBeenCalledWith(expect.objectContaining({ slug: 'my-tpl', name: 'My tpl', kind: 'stdio', is_active: true }))
    expect(fetchTemplates).toHaveBeenCalled()
    expect(toastSuccess).toHaveBeenCalledWith('Template créé')
    expect(push).toHaveBeenCalledWith({ name: 'template-detail', params: { slug: 'my-tpl' } })
  })

  it('shows a 409 next to the slug field', async () => {
    createTemplate.mockRejectedValue(new ApiError(409, 'Conflict', { error: 'template slug already used: my-tpl' }))
    const w = render()
    await w.find('#tpl-slug').setValue('my-tpl')
    await w.find('#tpl-name').setValue('My tpl')
    await w.find('#tpl-command').setValue('mcp-x')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(w.find('#tpl-slug-error').text()).toMatch(/already used/)
    expect(w.find('#tpl-submit-error').exists()).toBe(false)
    expect(push).not.toHaveBeenCalled()
  })

  it('shows other errors in the banner and blocks invalid JSON areas', async () => {
    const w = render()
    await w.find('#tpl-slug').setValue('my-tpl')
    await w.find('#tpl-name').setValue('My tpl')
    await w.find('#tpl-command').setValue('mcp-x')
    await w.find('#tpl-default-env').setValue('{oops')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(w.find('#tpl-submit-error').text()).toMatch(/default_env/)
    expect(createTemplate).not.toHaveBeenCalled()
  })

  it('still redirects when the catalog refresh fails after a successful create', async () => {
    createTemplate.mockResolvedValue({ slug: 'my-tpl' })
    fetchTemplates.mockRejectedValue(new Error('boom'))
    const w = render()
    await w.find('#tpl-slug').setValue('my-tpl')
    await w.find('#tpl-name').setValue('My tpl')
    await w.find('#tpl-command').setValue('mcp-x')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(toastSuccess).toHaveBeenCalledWith('Template créé')
    expect(push).toHaveBeenCalledWith({ name: 'template-detail', params: { slug: 'my-tpl' } })
    expect(w.find('#tpl-submit-error').exists()).toBe(false)
  })

  it('does not throw on a malformed file and warns about an unknown runner', async () => {
    const w = render()
    await pickFile(w, JSON.stringify({ slug: 'x', name: 7, stdio_command: 'c', stdio_args: 'oops', tags: 'a', runner: 'mystery' }))
    expect(w.find('#import-error').exists()).toBe(false)
    expect((w.find('#tpl-slug').element as HTMLInputElement).value).toBe('x')
    expect((w.find('#tpl-runner').element as HTMLSelectElement).value).toBe('mystery')
    expect(w.find('#tpl-runner-warning').text()).toMatch(/Valeur inconnue : mystery/)
  })
})
