import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export type UserRole = 'admin' | 'read-only' | 'config-only'

const ROLE_LEVELS: Record<UserRole, number> = {
  'admin': 3,
  'read-only': 2,
  'config-only': 1,
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref<{ email: string; display_name?: string; role?: UserRole } | null>(null)
  const token = ref<string | null>(localStorage.getItem('auth_token'))
  const isLoading = ref(false)

  const isAuthenticated = computed(() => user.value !== null && token.value !== null)

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
    if (!token.value) return false
    try {
      isLoading.value = true
      const response = await fetch('/api/v1/me', {
        headers: { 'Authorization': `Bearer ${token.value}` }
      })
      if (!response.ok) {
        clearToken()
        user.value = null
        return false
      }
      const data = await response.json()
      user.value = { email: data.email, display_name: data.display_name, role: data.role as UserRole | undefined }
      return true
    } catch {
      clearToken()
      user.value = null
      return false
    } finally {
      isLoading.value = false
    }
  }

  async function login(username: string, password: string): Promise<void> {
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

  async function logout(): Promise<void> {
    try {
      if (token.value) {
        await fetch('/logout', {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token.value}` }
        })
      }
    } finally {
      clearToken()
      user.value = null
    }
  }

  return { user, token, isLoading, isAuthenticated, userRole, isAdmin, isReadOnly, hasRole, checkSession, login, logout }
})
