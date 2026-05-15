<template>
  <button
    type="button"
    :disabled="disabled"
    :title="label"
    :aria-label="label"
    :class="['inline-flex items-center justify-center w-8 h-8 rounded-md border text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed', toneClasses]"
    @click="$emit('click', $event)"
  >
    <i :class="['pi', icon, 'text-xs']" />
  </button>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  icon: string
  label: string
  tone?: 'neutral' | 'brand' | 'danger'
  disabled?: boolean
}>()

defineEmits<{ click: [e: MouseEvent] }>()

const toneClasses = computed(() => {
  switch (props.tone) {
    case 'brand':
      return 'border-brand-300 dark:border-brand-700 text-brand-600 dark:text-brand-400 hover:bg-brand-50 dark:hover:bg-brand-500/10'
    case 'danger':
      return 'border-error-300 dark:border-error-700 text-error-600 hover:bg-error-50 dark:hover:bg-error-500/10'
    default:
      return 'border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5'
  }
})
</script>
