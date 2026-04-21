<template>
  <div class="mb-4 rounded-lg border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800/50">
    <button
      type="button"
      class="flex w-full items-center justify-between px-4 py-3 text-left"
      @click="open = !open"
    >
      <span class="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-200">
        <i class="pi pi-filter text-xs text-gray-400 dark:text-gray-500" />
        {{ title }}
        <span
          v-if="activeCount > 0"
          class="inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 text-xs font-medium rounded-full bg-brand-100 text-brand-700 dark:bg-brand-500/20 dark:text-brand-300"
        >
          {{ activeCount }}
        </span>
      </span>
      <i
        class="pi text-xs text-gray-400 dark:text-gray-500 transition-transform"
        :class="open ? 'pi-chevron-up' : 'pi-chevron-down'"
      />
    </button>
    <div v-show="open" class="border-t border-gray-200 dark:border-gray-700 p-4">
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        <slot />
      </div>
      <div v-if="activeCount > 0" class="mt-4 flex justify-end">
        <button
          type="button"
          class="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-gray-600 dark:text-gray-300 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700"
          @click="$emit('reset')"
        >
          <i class="pi pi-times text-xs" />
          Reinitialiser
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const props = withDefaults(defineProps<{
  title?: string
  activeCount: number
  defaultOpen?: boolean
}>(), {
  title: 'Filtres',
  defaultOpen: false,
})

defineEmits<{
  (e: 'reset'): void
}>()

const open = ref(props.defaultOpen)
</script>
