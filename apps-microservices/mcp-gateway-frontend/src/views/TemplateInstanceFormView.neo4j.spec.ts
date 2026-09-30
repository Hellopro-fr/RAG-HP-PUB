// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const getTemplate = vi.fn()
vi.mock('@/api/templates', () => ({ templatesApi: { get: (...a: unknown[]) => getTemplate(...a) } }))
vi.mock('@/stores/templates', () => ({ useTemplatesStore: () => ({ createInstance: vi.fn() }) }))
vi.mock('@/stores/servers', () => ({ useServersStore: () => ({ tags: [], fetchTags: vi.fn() }) }))
vi.mock('@/composables/useToast', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }) }))
vi.mock('@/api/client', () => ({ api: {} }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))

import TemplateInstanceFormView from './TemplateInstanceFormView.vue'

const base = {
  slug: 'x', name: 'X', description: '', icon: '', stdio_command: 'cmd', stdio_args: [],
  required_extra_env: [{ key: 'NEO4J_READ_ONLY', label: 'Lecture seule', required: false }],
  tool_prefix: '', tags: [], kind: 'stdio', instance_count: 0
}

async function render(runner?: 'google' | 'neo4j') {
  getTemplate.mockResolvedValue({ ...base, runner })
  const w = mount(TemplateInstanceFormView, {
    props: { slug: 'x' },
    global: { stubs: { StepTabs: true, IconPicker: true, 'router-link': true } }
  })
  await flushPromises()
  return w
}

describe('TemplateInstanceFormView runner branching', () => {
  beforeEach(() => getTemplate.mockReset())

  it('Neo4j template shows the connection fields and read-only checkbox, not the file upload', async () => {
    const w = await render('neo4j')
    for (const id of ['neo4j-uri', 'neo4j-username', 'neo4j-password', 'neo4j-database']) {
      expect(w.find(`#${id}`).exists()).toBe(true)
    }
    expect(w.find('#neo4j-password').attributes('type')).toBe('password')
    expect((w.find('#neo4j-read-only').element as HTMLInputElement).checked).toBe(true)
    expect(w.find('#instance-credentials').exists()).toBe(false)
    expect(w.find('#env-NEO4J_READ_ONLY').exists()).toBe(false)
  })

  it('Google template is unchanged', async () => {
    const w = await render('google')
    expect(w.find('#instance-credentials').exists()).toBe(true)
    expect(w.find('#neo4j-uri').exists()).toBe(false)
  })
})
