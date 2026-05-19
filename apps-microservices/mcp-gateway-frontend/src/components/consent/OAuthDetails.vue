<template>
  <div class="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-5">
    <div class="flex items-start gap-3 mb-4">
      <div
        class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gray-100 dark:bg-gray-800"
      >
        <Info class="h-4 w-4 text-gray-600 dark:text-gray-400" />
      </div>
      <div>
        <h3 class="font-semibold text-gray-900 dark:text-white">Détails OAuth2</h3>
        <p class="text-sm text-gray-600 dark:text-gray-400 mt-0.5">
          Informations techniques sur cette demande
        </p>
      </div>
    </div>

    <div class="grid gap-3 sm:grid-cols-2">
      <div class="rounded-md bg-gray-100 dark:bg-gray-800/50 p-3">
        <div class="flex items-center gap-2 mb-1">
          <Key class="h-3.5 w-3.5 text-gray-600 dark:text-gray-400" />
          <span
            class="text-xs font-medium uppercase tracking-wide text-gray-600 dark:text-gray-400"
          >
            Client ID
          </span>
        </div>
        <code class="text-xs font-mono text-gray-900 dark:text-white break-all">
          {{ clientId }}
        </code>
      </div>
      <div class="rounded-md bg-gray-100 dark:bg-gray-800/50 p-3">
        <div class="flex items-center gap-2 mb-1">
          <Globe class="h-3.5 w-3.5 text-gray-600 dark:text-gray-400" />
          <span
            class="text-xs font-medium uppercase tracking-wide text-gray-600 dark:text-gray-400"
          >
            Redirect URI
          </span>
        </div>
        <code class="text-xs font-mono text-gray-900 dark:text-white break-all">
          {{ redirectUri }}
        </code>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Info, Key, Globe } from 'lucide-vue-next'

defineProps<{
  clientId: string
  redirectUri: string
}>()
</script>
