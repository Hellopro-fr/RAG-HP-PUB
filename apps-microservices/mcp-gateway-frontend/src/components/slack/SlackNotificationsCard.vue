<template>
  <div class="rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800 p-5">
    <div class="flex items-center justify-between flex-wrap gap-4">
      <div class="flex items-center gap-3">
        <div class="h-10 w-10 rounded-full bg-[#4A154B]/10 dark:bg-[#4A154B]/30 flex items-center justify-center">
          <!-- Slack mark -->
          <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
            <path d="M5.042 15.165a2.528 2.528 0 01-2.52 2.523A2.528 2.528 0 010 15.165a2.527 2.527 0 012.522-2.52h2.52v2.52zM6.313 15.165a2.527 2.527 0 012.521-2.52 2.527 2.527 0 012.521 2.52v6.313A2.528 2.528 0 018.834 24a2.528 2.528 0 01-2.521-2.522v-6.313z" fill="#E01E5A"/>
            <path d="M8.834 5.042a2.528 2.528 0 01-2.521-2.52A2.528 2.528 0 018.834 0a2.528 2.528 0 012.521 2.522v2.52H8.834zM8.834 6.313a2.528 2.528 0 012.521 2.521 2.528 2.528 0 01-2.521 2.521H2.522A2.528 2.528 0 010 8.834a2.528 2.528 0 012.522-2.521h6.312z" fill="#36C5F0"/>
            <path d="M18.956 8.834a2.528 2.528 0 012.522-2.521A2.528 2.528 0 0124 8.834a2.528 2.528 0 01-2.522 2.521h-2.522v-2.521zM17.688 8.834a2.528 2.528 0 01-2.523 2.521 2.527 2.527 0 01-2.52-2.521V2.522A2.527 2.527 0 0115.165 0a2.528 2.528 0 012.523 2.522v6.312z" fill="#2EB67D"/>
            <path d="M15.165 18.956a2.528 2.528 0 012.523 2.522A2.528 2.528 0 0115.165 24a2.527 2.527 0 01-2.52-2.522v-2.522h2.52zM15.165 17.688a2.527 2.527 0 01-2.52-2.523 2.526 2.526 0 012.52-2.52h6.313A2.527 2.527 0 0124 15.165a2.528 2.528 0 01-2.522 2.523h-6.313z" fill="#ECB22E"/>
          </svg>
        </div>
        <div>
          <h3 class="font-semibold text-gray-900 dark:text-white">Slack</h3>
          <p v-if="loading" class="text-sm text-gray-500 dark:text-gray-400">
            <i class="pi pi-spinner pi-spin mr-1" />Chargement...
          </p>
          <p v-else-if="status?.enabled" class="text-sm text-green-600 dark:text-green-400">
            Activé<span v-if="status.env_label"> — env : <code class="text-xs">{{ status.env_label }}</code></span>
          </p>
          <p v-else class="text-sm text-gray-500 dark:text-gray-400">
            Désactivé — <code class="text-xs">SLACK_WEBHOOK_URL</code> non configuré
          </p>
        </div>
      </div>

      <button
        type="button"
        @click="handleTest"
        :disabled="!status?.enabled || testing"
        class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-lg hover:bg-brand-600 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <i v-if="testing" class="pi pi-spinner pi-spin mr-1" />
        <i v-else class="pi pi-send mr-1" />
        Envoyer un test
      </button>
    </div>

    <!-- Inline result banner: keeps the outcome visible after the toast fades,
         so the admin can re-read the delivery error without re-running the test. -->
    <div
      v-if="lastResult"
      class="mt-4 p-3 rounded-lg text-sm"
      :class="resultBannerClasses"
      role="status"
    >
      <p class="font-medium">{{ resultTitle }}</p>
      <p v-if="lastResult.message" class="mt-1 opacity-90 break-words">{{ lastResult.message }}</p>
    </div>

    <p class="mt-3 text-xs text-gray-400 dark:text-gray-500">
      Notifications envoyées : serveur DOWN/UP, régression d'outils, accès non autorisé, arrêt du gateway, panic.
      Le webhook est défini via <code>SLACK_WEBHOOK_URL</code> (redémarrage requis en cas de changement).
    </p>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { slackApi } from '@/api/slack'
import { useToast } from '@/composables/useToast'
import type { SlackStatus, SlackTestResponse } from '@/types/slack'

const toast = useToast()
const loading = ref(true)
const testing = ref(false)
const status = ref<SlackStatus | null>(null)
const lastResult = ref<SlackTestResponse | null>(null)

const resultTitle = computed(() => {
  if (!lastResult.value) return ''
  switch (lastResult.value.status) {
    case 'ok': return 'Message de test envoyé'
    case 'disabled': return 'Notifications Slack désactivées'
    case 'error': return 'Échec de l\'envoi'
    default: return 'Résultat'
  }
})

const resultBannerClasses = computed(() => {
  if (!lastResult.value) return ''
  switch (lastResult.value.status) {
    case 'ok':
      return 'bg-green-50 text-green-800 dark:bg-green-900/30 dark:text-green-300'
    case 'disabled':
      return 'bg-gray-50 text-gray-800 dark:bg-gray-900/30 dark:text-gray-300'
    case 'error':
      return 'bg-red-50 text-red-800 dark:bg-red-900/30 dark:text-red-300'
    default:
      return 'bg-gray-50 text-gray-800 dark:bg-gray-900/30 dark:text-gray-300'
  }
})

async function loadStatus() {
  loading.value = true
  try {
    status.value = await slackApi.getStatus()
  } catch {
    status.value = { enabled: false, env_label: '' }
    toast.error('Impossible de lire le statut Slack')
  } finally {
    loading.value = false
  }
}

async function handleTest() {
  testing.value = true
  lastResult.value = null
  try {
    const res = await slackApi.sendTest()
    lastResult.value = res
    if (res.status === 'ok') {
      toast.success('Message de test envoyé')
    } else if (res.status === 'disabled') {
      toast.info('Notifications Slack désactivées')
    } else {
      toast.error('Échec : ' + res.message)
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Erreur inconnue'
    lastResult.value = { status: 'error', message }
    toast.error('Échec : ' + message)
  } finally {
    testing.value = false
  }
}

onMounted(loadStatus)
</script>
