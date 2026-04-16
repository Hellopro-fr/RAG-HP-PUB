<template>
  <div class="rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800 p-5">
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-3">
        <div class="h-10 w-10 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
          <svg class="w-5 h-5 text-red-600 dark:text-red-400" viewBox="0 0 24 24" fill="currentColor">
            <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" />
            <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
            <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
            <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
          </svg>
        </div>
        <div>
          <h3 class="font-semibold text-gray-900 dark:text-white">Google</h3>
          <p v-if="status?.connected" class="text-sm text-green-600 dark:text-green-400">
            Connecté : {{ status.email }}
          </p>
          <p v-else class="text-sm text-gray-500 dark:text-gray-400">
            Non connecté
          </p>
        </div>
      </div>

      <div>
        <button
          v-if="status?.connected"
          @click="handleDisconnect"
          :disabled="loading"
          class="px-4 py-2 text-sm font-medium text-red-600 border border-red-300 rounded-lg hover:bg-red-50 dark:text-red-400 dark:border-red-600 dark:hover:bg-red-900/20 disabled:opacity-50"
        >
          <i v-if="loading" class="pi pi-spinner pi-spin mr-1" />
          Déconnecter
        </button>
        <button
          v-else
          @click="handleConnect"
          :disabled="loading"
          class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-lg hover:bg-brand-600 disabled:opacity-50"
        >
          <i v-if="loading" class="pi pi-spinner pi-spin mr-1" />
          Connecter
        </button>
      </div>
    </div>
    <p class="mt-3 text-xs text-gray-400 dark:text-gray-500">
      Accès en lecture seule à vos feuilles de calcul Google pour l'import de serveurs MCP.
    </p>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { googleApi } from '@/api/google'
import { useToast } from '@/composables/useToast'
import type { GoogleStatus } from '@/types/google'

const toast = useToast()
const loading = ref(false)
const status = ref<GoogleStatus | null>(null)

async function loadStatus() {
  try {
    status.value = await googleApi.getStatus()
  } catch {
    status.value = { connected: false }
  }
}

async function handleConnect() {
  loading.value = true
  try {
    const { url } = await googleApi.getAuthUrl()
    window.location.href = url
  } catch (err: unknown) {
    toast.error('Impossible de se connecter à Google')
    loading.value = false
  }
}

async function handleDisconnect() {
  loading.value = true
  try {
    await googleApi.disconnect()
    status.value = { connected: false }
    toast.success('Compte Google déconnecté')
  } catch {
    toast.error('Impossible de déconnecter le compte Google')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadStatus()

  // Handle callback redirect params
  const params = new URLSearchParams(window.location.search)
  if (params.get('google') === 'connected') {
    toast.success('Compte Google connecté avec succès')
    window.history.replaceState({}, '', '/settings')
    loadStatus()
  } else if (params.get('google') === 'error') {
    toast.error(params.get('message') || 'Échec de la connexion Google')
    window.history.replaceState({}, '', '/settings')
  }
})
</script>
