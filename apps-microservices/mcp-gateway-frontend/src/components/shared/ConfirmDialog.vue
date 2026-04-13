<template>
  <DialogRoot :open="open" @update:open="emit('update:open', $event)">
    <DialogPortal>
      <DialogOverlay class="fixed inset-0 bg-black/50 z-50" />
      <DialogContent
        class="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg bg-white dark:bg-gray-900 p-6 shadow-theme-xl"
      >
        <DialogTitle class="text-lg font-semibold text-gray-900 dark:text-white">
          {{ title }}
        </DialogTitle>
        <DialogDescription class="mt-2 text-sm text-gray-600 dark:text-gray-400">
          {{ message }}
        </DialogDescription>
        <div class="mt-6 flex justify-end gap-3">
          <button
            class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-white/5 rounded-md hover:bg-gray-200 dark:hover:bg-gray-700"
            @click="emit('update:open', false)"
          >
            Annuler
          </button>
          <button
            class="px-4 py-2 text-sm font-medium text-white rounded-md"
            :class="confirmClass"
            @click="emit('confirm')"
          >
            {{ confirmLabel }}
          </button>
        </div>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<script setup lang="ts">
import {
  DialogRoot,
  DialogPortal,
  DialogOverlay,
  DialogContent,
  DialogTitle,
  DialogDescription
} from 'radix-vue'
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  open: boolean
  title: string
  message: string
  confirmLabel?: string
  variant?: 'danger' | 'primary'
}>(), {
  confirmLabel: 'Confirmer',
  variant: 'danger'
})

const emit = defineEmits<{
  'update:open': [value: boolean]
  confirm: []
}>()

const confirmClass = computed(() =>
  props.variant === 'danger'
    ? 'bg-error-600 hover:bg-error-700'
    : 'bg-brand-500 hover:bg-brand-600'
)
</script>
