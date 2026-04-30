import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { postJson } from './useApi'

/**
 * Login flow composable.
 *
 * Supports two modes:
 *   1. Service-name mode (preferred): /signin?service=<name>&next=<path>
 *      Submits to POST /login. Backend looks up the service, validates
 *      creds with HelloPro, issues a one-shot login_session bound to
 *      the service, returns the consumer redirect URL.
 *   2. OAuth mode (legacy): /signin?client_id=...&redirect_uri=...&state=...
 *      &code_challenge=...&code_challenge_method=S256
 *      Submits to POST /authorize. Kept for backward compatibility.
 */

export interface ServiceParams {
  service: string
  next: string
}

export interface OAuthParams {
  client_id: string
  redirect_uri: string
  state: string
  code_challenge: string
  code_challenge_method: 'S256'
}

export type FlowParams =
  | { mode: 'service'; params: ServiceParams }
  | { mode: 'oauth'; params: OAuthParams }
  | null

export function useOAuthFlow() {
  const route = useRoute()

  const flow = computed<FlowParams>(() => {
    const q = route.query
    if (q.service) {
      return {
        mode: 'service',
        params: {
          service: String(q.service),
          next: String(q.next || '/'),
        },
      }
    }
    if (
      q.client_id &&
      q.redirect_uri &&
      q.state &&
      q.code_challenge &&
      q.code_challenge_method === 'S256'
    ) {
      return {
        mode: 'oauth',
        params: {
          client_id: String(q.client_id),
          redirect_uri: String(q.redirect_uri),
          state: String(q.state),
          code_challenge: String(q.code_challenge),
          code_challenge_method: 'S256',
        },
      }
    }
    return null
  })

  // Backwards-compat alias used by older tests/consumers.
  const params = computed(() => (flow.value?.mode === 'oauth' ? flow.value.params : null))

  async function submitLogin(username: string, password: string) {
    const f = flow.value
    if (!f) throw new Error('missing_login_params')
    if (f.mode === 'service') {
      return await postJson<{ redirect?: string }>('/login', {
        service: f.params.service,
        username,
        password,
        next: f.params.next,
      })
    }
    return await postJson<{ redirect?: string; next?: string }>('/authorize', {
      username,
      password,
      ...f.params,
    })
  }

  return { flow, params, submitLogin }
}
