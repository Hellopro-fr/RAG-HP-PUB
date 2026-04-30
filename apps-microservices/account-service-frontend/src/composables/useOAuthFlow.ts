import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { postJson } from './useApi'

export interface OAuthParams {
  client_id: string
  redirect_uri: string
  state: string
  code_challenge: string
  code_challenge_method: 'S256'
}

export function useOAuthFlow() {
  const route = useRoute()

  const params = computed<OAuthParams | null>(() => {
    const q = route.query
    if (!q.client_id || !q.redirect_uri || !q.state ||
        !q.code_challenge || q.code_challenge_method !== 'S256') {
      return null
    }
    return {
      client_id: String(q.client_id),
      redirect_uri: String(q.redirect_uri),
      state: String(q.state),
      code_challenge: String(q.code_challenge),
      code_challenge_method: 'S256',
    }
  })

  async function submitLogin(email: string, password: string) {
    const p = params.value
    if (!p) throw new Error('missing_oauth_params')
    return await postJson<{ redirect?: string; next?: string }>('/authorize', {
      email, password, ...p,
    })
  }

  return { params, submitLogin }
}
