<template>
  <div
    class="mb-4 flex items-center justify-between rounded-lg bg-brand-50/50 dark:bg-brand-500/5 border border-brand-200/60 dark:border-brand-500/20 px-4 py-2.5"
  >
    <div class="flex items-center gap-2 text-sm min-w-0">
      <i class="pi shrink-0 text-brand-500 dark:text-brand-400" :class="icon" />
      <span class="text-gray-700 dark:text-gray-300 truncate">
        <slot>{{ message }}</slot>
      </span>
    </div>
    <router-link
      :to="to"
      class="ml-3 inline-flex items-center gap-1 text-sm font-medium text-brand-600 dark:text-brand-400 hover:underline shrink-0"
    >
      {{ linkLabel }}
      <i class="pi pi-arrow-right text-xs" />
    </router-link>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  to: string
  icon: string
  message?: string
  linkLabel: string
}>()
</script>
