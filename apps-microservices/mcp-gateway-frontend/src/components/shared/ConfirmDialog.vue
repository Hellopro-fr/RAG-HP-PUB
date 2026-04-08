<template>
  <DialogRoot :open="open" @update:open="emit('update:open', $event)">
    <DialogPortal>
      <DialogOverlay class="fixed inset-0 bg-black/50 z-40" />
      <DialogContent
        class="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg bg-white p-6 shadow-xl"
      >
        <DialogTitle class="text-lg font-semibold text-gray-900">
          {{ title }}
        </DialogTitle>
        <DialogDescription class="mt-2 text-sm text-gray-600">
          {{ message }}
        </DialogDescription>
        <div class="mt-6 flex justify-end gap-3">
          <button
            class="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200"
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
    ? 'bg-red-600 hover:bg-red-700'
    : 'bg-blue-600 hover:bg-blue-700'
)
</script>
