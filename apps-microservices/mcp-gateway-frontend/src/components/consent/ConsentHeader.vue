<template>
  <header
    class="sticky top-0 z-10 bg-white border-b border-gray-200 dark:bg-gray-900 dark:border-gray-800"
  >
    <div class="max-w-5xl mx-auto px-6 py-3 flex items-center justify-between">
      <router-link
        to="/docs"
        class="flex items-center gap-3 no-underline focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/40 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-gray-900 rounded"
      >
        <img src="/images/servers/hp-logo.svg" alt="Hellopro" width="36" height="36" class="w-9 h-9" />
        <div>
          <h1 class="text-lg font-semibold text-gray-900 dark:text-white leading-tight">
            MCP Gateway
          </h1>
          <p class="text-xs text-gray-500 dark:text-gray-400">Autorisation</p>
        </div>
      </router-link>
    </div>
  </header>
</template>

<script setup lang="ts">
defineProps<{
  clientName: string
}>()
</script>
