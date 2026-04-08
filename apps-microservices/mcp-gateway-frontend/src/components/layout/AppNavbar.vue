<template>
  <nav class="bg-white border-b border-gray-200 px-6 py-3">
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-6">
        <h1 class="text-lg font-bold text-gray-900">MCP Gateway</h1>
        <div class="flex gap-1">
          <RouterLink
            v-for="tab in tabs"
            :key="tab.to"
            :to="tab.to"
            class="px-4 py-2 rounded-md text-sm font-medium transition-colors"
            :class="[
              route.path === tab.to
                ? 'bg-blue-100 text-blue-700'
                : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
            ]"
          >
            {{ tab.label }}
          </RouterLink>
        </div>
      </div>
      <div class="flex items-center gap-4">
        <span class="text-sm text-gray-500">{{ authStore.user?.email }}</span>
        <button
          class="text-sm text-gray-500 hover:text-gray-700"
          @click="handleLogout"
        >
          Déconnexion
        </button>
      </div>
    </div>
  </nav>
</template>

<script setup lang="ts">
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const tabs = [
  { to: '/servers', label: 'Serveurs' },
  { to: '/tokens', label: 'Config MCP' },
  { to: '/oauth2', label: 'OAuth2' }
]

async function handleLogout() {
  await authStore.logout()
  router.push('/login')
}
</script>
