<template>
  <div class="min-h-screen bg-gray-50 dark:bg-gray-950">
    <header class="sticky top-0 z-10 bg-white border-b border-gray-200 dark:bg-gray-900 dark:border-gray-800">
      <div class="max-w-5xl mx-auto px-6 py-3 flex items-center justify-between">
        <router-link to="/docs" class="flex items-center gap-3 no-underline">
          <img src="/images/servers/hp-logo.svg" alt="Hellopro" class="w-9 h-9" />
          <div>
            <h1 class="text-lg font-semibold text-gray-900 dark:text-white leading-tight">MCP Gateway</h1>
            <p class="text-xs text-gray-500 dark:text-gray-400">Documentation</p>
          </div>
        </router-link>
        <div class="flex items-center gap-3">
          <!-- <ThemeToggler /> -->
          <!-- <router-link
            to="/login"
            class="text-sm font-medium text-brand-500 hover:text-brand-600 dark:text-brand-400 dark:hover:text-brand-300"
          >
            Connexion
          </router-link> -->
        </div>
      </div>
    </header>
    <main class="max-w-5xl mx-auto px-6 py-8">
      <slot />
    </main>
  </div>
</template>

<script setup lang="ts">
// import ThemeToggler from '@/components/common/ThemeToggler.vue';
</script>
