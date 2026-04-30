<script setup lang="ts">
defineProps<{ title: string; subtitle?: string }>()
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900 p-6">
    <div class="w-full max-w-md bg-white dark:bg-gray-800 rounded-lg shadow p-8">
      <h1 class="text-2xl font-semibold text-gray-900 dark:text-white">{{ title }}</h1>
      <p v-if="subtitle" class="mt-2 text-sm text-gray-500 dark:text-gray-400">{{ subtitle }}</p>
      <div class="mt-6"><slot /></div>
    </div>
  </div>
</template>
