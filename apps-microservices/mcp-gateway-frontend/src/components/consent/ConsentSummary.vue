<template>
  <div class="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-5">
    <div class="flex items-start gap-3 mb-4">
      <div
        class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gray-100 dark:bg-gray-800"
      >
        <Shield class="h-4 w-4 text-gray-600 dark:text-gray-400" />
      </div>
      <div>
        <h3 class="font-semibold text-gray-900 dark:text-white">
          Récapitulatif de l'autorisation
        </h3>
        <p class="text-sm text-gray-600 dark:text-gray-400 leading-relaxed mt-0.5">
          Connecter {{ articleAndNames }} via MCP
        </p>
      </div>
    </div>

    <div class="grid grid-cols-3 gap-3">
      <div class="rounded-md bg-gray-100 dark:bg-gray-800/50 p-3 text-center">
        <div class="flex items-center justify-center gap-1.5 mb-1">
          <Server class="h-4 w-4 text-gray-600 dark:text-gray-400" />
        </div>
        <div class="text-2xl font-bold text-gray-900 dark:text-white">{{ totalServers }}</div>
        <div class="text-xs text-gray-600 dark:text-gray-400">Total serveurs</div>
      </div>
      <div class="rounded-md bg-brand-50 dark:bg-brand-500/15 p-3 text-center">
        <div class="flex items-center justify-center gap-1.5 mb-1">
          <Shield class="h-4 w-4 text-brand-600 dark:text-brand-400" />
        </div>
        <div class="text-2xl font-bold text-brand-600 dark:text-brand-400">
          {{ enabledServers }}
        </div>
        <div class="text-xs text-gray-600 dark:text-gray-400">Activés</div>
      </div>
      <div class="rounded-md bg-gray-100 dark:bg-gray-800/50 p-3 text-center">
        <div class="flex items-center justify-center gap-1.5 mb-1">
          <Server class="h-4 w-4 text-gray-600 dark:text-gray-400" />
        </div>
        <div class="text-2xl font-bold text-gray-900 dark:text-white">{{ requiredServers }}</div>
        <div class="text-xs text-gray-600 dark:text-gray-400">Requis</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Shield, Server } from 'lucide-vue-next'

const props = defineProps<{
  totalServers: number
  enabledServers: number
  requiredServers: number
  serverNames: string[]
}>()

const articleAndNames = computed(() => {
  const names = props.serverNames
  if (names.length === 0) return 'les serveurs MCP'
  if (names.length === 1) return `le ${names[0]}`
  return names.join(', ')
})
</script>
