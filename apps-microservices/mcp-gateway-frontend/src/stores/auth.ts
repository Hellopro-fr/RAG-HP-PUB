import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export type UserRole = 'admin' | 'read-only' | 'config-only'

const ROLE_LEVELS: Record<UserRole, number> = {
  'admin': 3,
  'read-only': 2,
  'config-only': 1,
}

// SSO mode: identity is held server-side in the gw_session HttpOnly cookie.
// JS never sees the access token. checkSession + logout drop their token
// arguments and rely on credentials:'include' to attach the cookie.
const SSO_MODE = import.meta.env.VITE_SSO_MODE === 'true'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<{ email: string; display_name?: string; role?: UserRole } | null>(null)
  const token = ref<string | null>(SSO_MODE ? null : localStorage.getItem('auth_token'))
  const isLoading = ref(false)

  const isAuthenticated = computed(() => {
    if (SSO_MODE) return user.value !== null
    return user.value !== null && token.value !== null
  })

  const userRole = computed<UserRole>(() => user.value?.role ?? 'config-only')
  const isAdmin = computed(() => userRole.value === 'admin')
  const isReadOnly = computed(() => userRole.value === 'read-only' || isAdmin.value)

  function hasRole(minRole: UserRole): boolean {
    return ROLE_LEVELS[userRole.value] >= ROLE_LEVELS[minRole]
  }

  function setToken(newToken: string) {
    token.value = newToken
    localStorage.setItem('auth_token', newToken)
  }

  function clearToken() {
    token.value = null
    localStorage.removeItem('auth_token')
  }

  async function checkSession(): Promise<boolean> {
    try {
      isLoading.value = true
      const headers: Record<string, string> = {}
      if (!SSO_MODE && token.value) {
        headers['Authorization'] = `Bearer ${token.value}`
      } else if (!SSO_MODE && !token.value) {
        return false
      }
      const response = await fetch('/api/v1/me', {
        headers,
        credentials: SSO_MODE ? 'include' : 'same-origin',
      })
      if (!response.ok) {
        if (!SSO_MODE) clearToken()
        user.value = null
        return false
      }
      const data = await response.json()
      user.value = { email: data.email, display_name: data.display_name, role: data.role as UserRole | undefined }
      return true
    } catch {
      if (!SSO_MODE) clearToken()
      user.value = null
      return false
    } finally {
      isLoading.value = false
    }
  }

  // Legacy direct login. In SSO mode the SPA redirects to /sso/login and never
  // calls this function — keep the implementation for SSO_MODE=false fallback.
  async function login(username: string, password: string): Promise<void> {
    if (SSO_MODE) {
      throw new Error('Direct login disabled in SSO mode — redirect to /sso/login')
    }
    isLoading.value = true
    try {
      const response = await fetch('/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      })

      if (!response.ok) {
        const data = await response.json().catch(() => ({ error: 'Erreur de connexion' }))
        throw new Error(data.error || 'Identifiants invalides')
      }

      const data = await response.json()
      setToken(data.token)
      user.value = { email: data.email, display_name: data.display_name, role: data.role as UserRole | undefined }
    } finally {
      isLoading.value = false
    }
  }

  function redirectToLogin(returnTo?: string) {
    const target = returnTo && returnTo !== '/' ? returnTo : window.location.pathname + window.location.search
    window.location.href = '/sso/login?return_to=' + encodeURIComponent(target)
  }

  async function logout(): Promise<void> {
    let nextURL = '/sso/login'
    try {
      if (SSO_MODE) {
        const res = await fetch('/logout', {
          method: 'POST',
          credentials: 'include',
          headers: { Accept: 'application/json' },
        })
        if (res.ok) {
          const data = await res.json().catch(() => null) as { logout_url?: string } | null
          if (data?.logout_url) {
            // Backend returns the account-service /logout URL so the portal
            // session cookie is also cleared (single-sign-out).
            nextURL = data.logout_url
          }
        }
      } else if (token.value) {
        await fetch('/logout', {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token.value}` }
        })
      }
    } finally {
      if (!SSO_MODE) clearToken()
      user.value = null
      if (SSO_MODE) {
        window.location.href = nextURL
      }
    }
  }

  return {
    user, token, isLoading, isAuthenticated, userRole, isAdmin, isReadOnly,
    hasRole, checkSession, login, logout, redirectToLogin,
    ssoMode: SSO_MODE,
  }
})
