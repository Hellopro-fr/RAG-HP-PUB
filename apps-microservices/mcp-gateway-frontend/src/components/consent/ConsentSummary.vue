<template>
  <div class="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-5">
    <div class="flex items-start gap-3">
      <div
        class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gray-100 dark:bg-gray-800"
      >
        <Shield class="h-4 w-4 text-gray-600 dark:text-gray-400" aria-hidden="true" />
      </div>
      <div>
        <h3 class="font-semibold text-gray-900 dark:text-white">
          Récapitulatif de l'autorisation
        </h3>
        <p class="text-base text-gray-600 dark:text-gray-400 leading-relaxed mt-0.5">
          Connecter avec le MCP {{ clientName }}
        </p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Shield } from 'lucide-vue-next'

defineProps<{
  clientName: string
}>()
</script>
