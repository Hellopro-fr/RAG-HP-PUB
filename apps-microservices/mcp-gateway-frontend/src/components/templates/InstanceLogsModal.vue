<template>
  <DialogRoot :open="open" @update:open="emit('update:open', $event)">
    <DialogPortal>
      <DialogOverlay class="fixed inset-0 bg-black/50 z-50" />
      <DialogContent
        class="fixed left-1/2 top-1/2 z-50 w-full max-w-3xl -translate-x-1/2 -translate-y-1/2 rounded-lg bg-white dark:bg-gray-900 p-6 shadow-theme-xl max-h-[90vh] overflow-y-auto"
      >
        <DialogTitle class="text-lg font-semibold text-gray-900 dark:text-white">
          Logs &mdash; {{ instance?.name ?? '' }}
        </DialogTitle>
        <DialogDescription class="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Dernières lignes de sortie d'erreur du runner.
        </DialogDescription>

        <div class="mt-5">
          <!-- Loading -->
          <div
            v-if="loading"
            class="text-center py-12"
          >
            <i class="pi pi-spinner pi-spin text-2xl text-brand-500" />
          </div>

          <!-- Error -->
          <div
            v-else-if="fetchError"
            class="rounded-md bg-error-50 dark:bg-error-500/15 px-3 py-2 text-xs text-error-600 dark:text-error-400"
          >
            <i class="pi pi-exclamation-triangle text-[11px] mr-1" />
            {{ fetchError }}
          </div>

          <!-- Logs content -->
          <pre
            v-else
            class="font-mono text-xs whitespace-pre-wrap bg-gray-950 text-gray-100 rounded-md p-4 max-h-[60vh] overflow-y-auto border border-gray-800"
          >{{ stderrTail || 'Aucun log pour le moment.' }}</pre>
        </div>

        <!-- Footer -->
        <div class="mt-5 flex justify-end">
          <button
            type="button"
            class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-white/5 rounded-md hover:bg-gray-200 dark:hover:bg-gray-700"
            @click="emit('update:open', false)"
          >
            Fermer
          </button>
        </div>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import {
  DialogRoot,
  DialogPortal,
  DialogOverlay,
  DialogContent,
  DialogTitle,
  DialogDescription
} from 'radix-vue'
import { templatesApi } from '@/api/templates'
import { ApiError } from '@/types/api'
import type { TemplateInstance } from '@/types/templates'

const props = defineProps<{
  instance: TemplateInstance | null
  open: boolean
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
}>()

const loading = ref(false)
const stderrTail = ref('')
const fetchError = ref('')

async function loadLogs(id: string): Promise<void> {
  loading.value = true
  fetchError.value = ''
  stderrTail.value = ''
  try {
    const fresh = await templatesApi.getInstance(id)
    stderrTail.value = fresh.stderr_tail ?? ''
  } catch (e: unknown) {
    if (e instanceof ApiError) {
      const body = e.body as { error?: string } | undefined
      fetchError.value = body?.error ?? e.message
    } else if (e instanceof Error) {
      fetchError.value = e.message
    } else {
      fetchError.value = 'Échec du chargement des logs'
    }
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.open, props.instance?.id] as const,
  ([isOpen, id]) => {
    if (isOpen && typeof id === 'string') {
      loadLogs(id)
    } else if (!isOpen) {
      stderrTail.value = ''
      fetchError.value = ''
    }
  },
  { immediate: true }
)
</script>
