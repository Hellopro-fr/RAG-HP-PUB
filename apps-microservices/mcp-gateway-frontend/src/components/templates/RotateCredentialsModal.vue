<template>
  <DialogRoot :open="open" @update:open="emit('update:open', $event)">
    <DialogPortal>
      <DialogOverlay class="fixed inset-0 bg-black/50 z-50" />
      <DialogContent
        class="fixed left-1/2 top-1/2 z-50 w-full max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-lg bg-white dark:bg-gray-900 p-6 shadow-theme-xl max-h-[90vh] overflow-y-auto"
      >
        <DialogTitle class="text-lg font-semibold text-gray-900 dark:text-white">
          Renouveler la clé &mdash; {{ instance?.name ?? '' }}
        </DialogTitle>
        <DialogDescription class="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Téléversez une nouvelle clé JSON de compte de service. L'instance sera
          redémarrée avec les nouvelles identifiants. L'ancienne clé est détruite.
        </DialogDescription>

        <form class="mt-5 space-y-5" @submit.prevent="submit">
          <!-- Service account JSON file -->
          <div>
            <label
              for="rotate-credentials"
              class="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1"
            >
              Nouvelle clé JSON du compte de service <span class="text-error-500">*</span>
            </label>
            <input
              id="rotate-credentials"
              type="file"
              accept="application/json,.json"
              required
              class="block w-full text-sm text-gray-700 dark:text-gray-300 file:mr-3 file:py-2 file:px-3 file:rounded file:border-0 file:text-xs file:font-medium file:bg-brand-50 file:text-brand-600 dark:file:bg-brand-500/15 dark:file:text-brand-400 hover:file:bg-brand-100 dark:hover:file:bg-brand-500/25"
              @change="onFile"
            />
            <p
              v-if="fileInfo"
              class="mt-2 text-xs text-success-600 dark:text-success-400 flex items-center gap-1"
            >
              <i class="pi pi-check-circle text-[11px]" />
              {{ fileInfo }}
            </p>
            <p
              v-if="fileError"
              class="mt-2 text-xs text-error-600 dark:text-error-400 flex items-center gap-1"
            >
              <i class="pi pi-exclamation-triangle text-[11px]" />
              {{ fileError }}
            </p>
            <p class="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
              Fichier JSON (max 16 Ko). Le contenu ne quitte jamais le navigateur tant que vous ne cliquez pas sur Renouveler.
            </p>
          </div>

          <!-- Submit error -->
          <div
            v-if="submitError"
            class="rounded-md bg-error-50 dark:bg-error-500/15 px-3 py-2 text-xs text-error-600 dark:text-error-400"
          >
            <i class="pi pi-exclamation-triangle text-[11px] mr-1" />
            {{ submitError }}
          </div>

          <!-- Footer -->
          <div class="flex justify-end gap-3 pt-2">
            <button
              type="button"
              class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-white/5 rounded-md hover:bg-gray-200 dark:hover:bg-gray-700"
              :disabled="submitting"
              @click="emit('update:open', false)"
            >
              Annuler
            </button>
            <button
              type="submit"
              class="px-4 py-2 text-sm font-medium text-white bg-brand-500 hover:bg-brand-600 rounded-md disabled:opacity-50 disabled:cursor-not-allowed"
              :disabled="!canSubmit"
            >
              {{ submitting ? 'Rotation…' : 'Renouveler' }}
            </button>
          </div>
        </form>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  DialogRoot,
  DialogPortal,
  DialogOverlay,
  DialogContent,
  DialogTitle,
  DialogDescription
} from 'radix-vue'
import { useTemplatesStore } from '@/stores/templates'
import { ApiError } from '@/types/api'
import { validateSaJson } from './validateSaJson'
import type { TemplateInstance } from '@/types/templates'

const props = defineProps<{
  instance: TemplateInstance | null
  open: boolean
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  rotated: []
}>()

const store = useTemplatesStore()

const file = ref<File | null>(null)
const fileInfo = ref('')
const fileError = ref('')
const submitError = ref('')
const submitting = ref(false)

const canSubmit = computed(
  () => !!file.value && !fileError.value && !submitting.value && !!props.instance
)

function resetForm(): void {
  file.value = null
  fileInfo.value = ''
  fileError.value = ''
  submitError.value = ''
  submitting.value = false
}

watch(
  () => props.open,
  (o) => {
    if (!o) resetForm()
  }
)

async function onFile(e: Event): Promise<void> {
  const target = e.target as HTMLInputElement
  const f = target.files?.[0] ?? null
  file.value = f
  fileInfo.value = ''
  fileError.value = ''
  if (!f) return
  const result = await validateSaJson(f)
  if (!result.ok) {
    fileError.value = result.error ?? 'JSON invalide'
    return
  }
  fileInfo.value = result.clientEmail ?? ''
}

async function submit(): Promise<void> {
  if (!file.value || !props.instance) return
  submitting.value = true
  submitError.value = ''
  try {
    await store.rotateCredentials(props.instance.id, file.value)
    emit('rotated')
    emit('update:open', false)
  } catch (e: unknown) {
    if (e instanceof ApiError) {
      const body = e.body as { error?: string } | undefined
      submitError.value = body?.error ?? e.message
    } else if (e instanceof Error) {
      submitError.value = e.message
    } else {
      submitError.value = 'Échec de la rotation'
    }
  } finally {
    submitting.value = false
  }
}
</script>
