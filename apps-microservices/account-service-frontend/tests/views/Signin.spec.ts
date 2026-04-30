import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import Signin from '../../src/views/Auth/Signin.vue'

const baseQuery = {
  client_id: 'svc',
  redirect_uri: 'https://svc.hellopro.eu/cb',
  state: 'st',
  code_challenge: 'c',
  code_challenge_method: 'S256',
}

async function mountSignin() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/signin', component: Signin },
      { path: '/consent', component: { template: '<div/>' } },
    ],
  })
  await router.push({ path: '/signin', query: baseQuery })
  await router.isReady()
  return mount(Signin, { global: { plugins: [router] } })
}

describe('Signin.vue', () => {
  let originalAssign: typeof window.location.assign
  beforeEach(() => {
    originalAssign = window.location.assign
    Object.defineProperty(window, 'location', {
      value: { ...window.location, assign: vi.fn() },
      writable: true,
    })
  })
  afterEach(() => {
    Object.defineProperty(window.location, 'assign', { value: originalAssign })
    vi.restoreAllMocks()
  })

  it('submits and redirects on success', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ redirect: 'https://svc.hellopro.eu/cb?code=x&state=st' }), {
        status: 200, headers: { 'content-type': 'application/json' },
      })
    )
    const w = await mountSignin()
    await w.find('[data-test=username]').setValue('u@x')
    await w.find('[data-test=password]').setValue('p')
    await w.find('[data-test=signin-form]').trigger('submit.prevent')
    await new Promise((r) => setTimeout(r, 0))
    expect(fetchSpy).toHaveBeenCalled()
    expect((window.location.assign as unknown as ReturnType<typeof vi.fn>))
      .toHaveBeenCalledWith('https://svc.hellopro.eu/cb?code=x&state=st')
  })

  it('shows generic error on access_denied', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ error: 'access_denied' }), { status: 401 })
    )
    const w = await mountSignin()
    await w.find('[data-test=username]').setValue('u@x')
    await w.find('[data-test=password]').setValue('p')
    await w.find('[data-test=signin-form]').trigger('submit.prevent')
    await new Promise((r) => setTimeout(r, 0))
    expect(w.find('[data-test=error]').text()).toMatch(/Invalid username or password/i)
  })
})
