<template>
  <div>
    <p class="text-xs text-gray-600 dark:text-gray-400 mb-2">Serveurs non configurés :</p>
    <div
      class="rounded-md border border-amber-200 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/20 divide-y divide-amber-100 dark:divide-amber-800"
    >
      <div
        v-for="server in servers"
        :key="server.id"
        class="flex items-center justify-between px-3 py-2"
      >
        <div class="flex items-center gap-2">
          <img
            v-if="server.icon"
            :src="server.icon"
            :alt="server.name"
            width="20"
            height="20"
            class="h-5 w-5 object-contain"
          />
          <Server v-else class="h-4 w-4 text-amber-700 dark:text-amber-300" aria-hidden="true" />
          <span class="text-sm font-medium text-gray-900 dark:text-gray-100">
            {{ server.name }}
          </span>
        </div>
        <a
          v-if="server.docs_url"
          :href="server.docs_url"
          target="_blank"
          rel="noopener noreferrer"
          class="text-xs font-medium text-brand-600 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/40 rounded px-1 py-0.5"
        >
          Voir documentation &rarr;
        </a>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Server } from 'lucide-vue-next'
import type { AuthorizeServer } from '@/types/oauth2'

defineProps<{
  servers: AuthorizeServer[]
}>()
</script>
