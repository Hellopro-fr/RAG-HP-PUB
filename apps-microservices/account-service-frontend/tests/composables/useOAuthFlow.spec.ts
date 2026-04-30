import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent, h } from 'vue'

import { useOAuthFlow } from '../../src/composables/useOAuthFlow'

const Probe = defineComponent({
  setup() {
    const flow = useOAuthFlow()
    return { flow }
  },
  render() {
    return h('div', { 'data-params': JSON.stringify(this.flow.params) })
  },
})

async function mountWithQuery(query: Record<string, string>) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/signin', component: Probe }],
  })
  await router.push({ path: '/signin', query })
  await router.isReady()
  return mount(Probe, { global: { plugins: [router] } })
}

describe('useOAuthFlow.params', () => {
  it('returns null when required params missing', async () => {
    const w = await mountWithQuery({ client_id: 'svc' })
    expect(w.attributes('data-params')).toBe('null')
  })
  it('returns parsed params when all present', async () => {
    const w = await mountWithQuery({
      client_id: 'svc',
      redirect_uri: 'https://svc.hellopro.eu/cb',
      state: 's',
      code_challenge: 'c',
      code_challenge_method: 'S256',
    })
    const parsed = JSON.parse(w.attributes('data-params')!)
    expect(parsed.client_id).toBe('svc')
    expect(parsed.code_challenge_method).toBe('S256')
  })
})
