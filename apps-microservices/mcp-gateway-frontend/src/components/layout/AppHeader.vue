<template>
  <header class="sticky top-0 z-30 flex items-center justify-between border-b border-gray-200 bg-white px-4 py-3 shadow-sm lg:px-6">
    <!-- Left side -->
    <div class="flex items-center gap-3">
      <button
        class="rounded-md p-1.5 text-gray-500 hover:bg-gray-100 hover:text-gray-700 lg:hidden"
        @click="$emit('toggle-sidebar')"
      >
        <i class="pi pi-bars text-lg" />
      </button>
      <h1 class="text-lg font-semibold text-gray-900">
        {{ pageTitle }}
      </h1>
    </div>

    <!-- Right side -->
    <div class="flex items-center gap-4">
      <span class="hidden text-sm text-gray-500 sm:inline">
        {{ authStore.user?.email }}
      </span>
      <button
        class="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-700"
        @click="handleLogout"
      >
        <i class="pi pi-sign-out text-sm" />
        <span class="hidden sm:inline">Déconnexion</span>
      </button>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

defineEmits<{
  'toggle-sidebar': []
}>()

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const pageTitle = computed(() => {
  return (route.meta.title as string | undefined) || 'MCP Gateway'
})

async function handleLogout() {
  await authStore.logout()
  router.push('/login')
}
</script>
