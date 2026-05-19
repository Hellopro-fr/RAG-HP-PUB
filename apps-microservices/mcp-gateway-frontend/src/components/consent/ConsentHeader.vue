<template>
  <header class="border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
    <div class="mx-auto max-w-3xl px-4 py-6">
      <div class="flex flex-col items-center gap-4 text-center">
        <div class="flex h-12 w-12 items-center justify-center rounded-full bg-brand-500">
          <KeyRound class="h-6 w-6 text-white" />
        </div>
        <div class="space-y-3">
          <h1 class="text-xl font-semibold text-gray-900 dark:text-white">
            Demande d'autorisation
          </h1>
          <div class="flex items-center justify-center gap-3">
            <div
              class="flex h-8 w-8 items-center justify-center rounded-full bg-gray-100 dark:bg-gray-800 text-xs font-medium text-gray-700 dark:text-gray-300"
            >
              {{ initials }}
            </div>
            <span class="font-medium text-gray-900 dark:text-white">{{ clientName }}</span>
          </div>
          <p class="text-sm text-gray-600 dark:text-gray-400 max-w-md">
            demande l'autorisation d'accéder à vos serveurs MCP en votre nom
          </p>
        </div>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { KeyRound } from 'lucide-vue-next'

const props = defineProps<{
  clientName: string
}>()

const initials = computed(() =>
  (props.clientName || '??').slice(0, 2).toUpperCase(),
)
</script>
