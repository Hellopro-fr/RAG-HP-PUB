<template>
  <div class="flex items-center justify-end gap-3 py-3 text-sm text-gray-600 dark:text-gray-300">
    <button
      type="button"
      class="inline-flex items-center justify-center h-8 w-8 rounded-md border border-gray-300 bg-white text-gray-700 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300 dark:hover:bg-gray-800"
      :disabled="!canPrev"
      aria-label="Page precedente"
      @click="goPrev"
    >
      <i class="pi pi-chevron-left text-xs" />
    </button>
    <span class="tabular-nums">
      Page {{ currentPage }} / {{ totalPages }}
    </span>
    <button
      type="button"
      class="inline-flex items-center justify-center h-8 w-8 rounded-md border border-gray-300 bg-white text-gray-700 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300 dark:hover:bg-gray-800"
      :disabled="!canNext"
      aria-label="Page suivante"
      @click="goNext"
    >
      <i class="pi pi-chevron-right text-xs" />
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  page: number
  limit: number
  total: number
}>()

const emit = defineEmits<{
  (e: 'update:page', value: number): void
}>()

const totalPages = computed(() => {
  if (props.limit <= 0 || props.total <= 0) return 1
  return Math.max(1, Math.ceil(props.total / props.limit))
})

const currentPage = computed(() => {
  if (props.page < 1) return 1
  if (props.page > totalPages.value) return totalPages.value
  return props.page
})

const canPrev = computed(() => currentPage.value > 1)
const canNext = computed(() => currentPage.value * props.limit < props.total)

function goPrev() {
  if (!canPrev.value) return
  emit('update:page', currentPage.value - 1)
}

function goNext() {
  if (!canNext.value) return
  emit('update:page', currentPage.value + 1)
}
</script>
