import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api, onUnauthorized } from '@/api/client'
import type { CurrentUser } from '@/types/user'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<CurrentUser | null>(null)
  const isLoading = ref(false)
  const isAuthenticated = computed(() => user.value !== null)
  const isAdmin = computed(() => user.value?.is_admin === true)

  onUnauthorized(() => {
    user.value = null
  })

  async function checkSession(): Promise<boolean> {
    try {
      isLoading.value = true
      const me = await api<CurrentUser>('/api/v1/me')
      user.value = me
      return true
    } catch {
      user.value = null
      return false
    } finally {
      isLoading.value = false
    }
  }

  async function login(username: string, password: string): Promise<void> {
    isLoading.value = true
    try {
      const resp = await api<CurrentUser>('/api/v1/login', {
        method: 'POST',
        body: { username, password },
      })
      user.value = resp
    } finally {
      isLoading.value = false
    }
  }

  async function logout(): Promise<void> {
    try {
      await api('/api/v1/logout', { method: 'POST' })
    } finally {
      user.value = null
    }
  }

  return { user, isLoading, isAuthenticated, isAdmin, checkSession, login, logout }
})
