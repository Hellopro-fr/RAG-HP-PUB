<template>
  <DialogRoot :open="open" @update:open="emit('update:open', $event)">
    <DialogPortal>
      <DialogOverlay class="fixed inset-0 bg-black/50 z-50" />
      <DialogContent
        class="fixed left-1/2 top-1/2 z-50 w-full max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-lg bg-white dark:bg-gray-900 p-6 shadow-theme-xl max-h-[90vh] overflow-y-auto"
      >
        <DialogTitle class="text-lg font-semibold text-gray-900 dark:text-white">
          Importer des templates
        </DialogTitle>
        <DialogDescription class="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Téléversez un fichier JSON exporté précédemment. Les templates existants
          (identifiés par <code class="text-xs">slug</code>) seront mis à jour ; les nouveaux seront créés.
          Les instances et les identifiants ne sont pas concernés.
        </DialogDescription>

        <form class="mt-5 space-y-5" @submit.prevent="submit">
          <div>
            <label
              for="import-templates-file"
              class="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1"
            >
              Fichier JSON <span class="text-error-500">*</span>
            </label>
            <input
              id="import-templates-file"
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
              Fichier JSON (max 256 Ko). Le fichier est analysé dans le navigateur avant envoi.
            </p>
          </div>

          <div
            v-if="submitError"
            class="rounded-md bg-error-50 dark:bg-error-500/15 px-3 py-2 text-xs text-error-600 dark:text-error-400"
          >
            <i class="pi pi-exclamation-triangle text-[11px] mr-1" />
            {{ submitError }}
          </div>

          <div
            v-if="submitSuccess"
            class="rounded-md bg-success-50 dark:bg-success-500/15 px-3 py-2 text-xs text-success-600 dark:text-success-400"
          >
            <i class="pi pi-check-circle text-[11px] mr-1" />
            {{ submitSuccess }}
          </div>

          <div class="flex justify-end gap-3 pt-2">
            <button
              type="button"
              class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-white/5 rounded-md hover:bg-gray-200 dark:hover:bg-gray-700"
              :disabled="submitting"
              @click="emit('update:open', false)"
            >
              Fermer
            </button>
            <button
              type="submit"
              class="px-4 py-2 text-sm font-medium text-white bg-brand-500 hover:bg-brand-600 rounded-md disabled:opacity-50 disabled:cursor-not-allowed"
              :disabled="!canSubmit"
            >
              {{ submitting ? 'Import…' : 'Importer' }}
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

// 256 KB — must match the backend cap in handleImportTemplates. Checking
// client-side keeps users from waiting on a round-trip for a payload that
// will be rejected anyway.
const MAX_IMPORT_BYTES = 256 * 1024

const props = defineProps<{
  open: boolean
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  imported: []
}>()

const store = useTemplatesStore()

const file = ref<File | null>(null)
const fileInfo = ref('')
const fileError = ref('')
const submitError = ref('')
const submitSuccess = ref('')
const submitting = ref(false)

const canSubmit = computed(() => !!file.value && !fileError.value && !submitting.value)

function resetForm(): void {
  file.value = null
  fileInfo.value = ''
  fileError.value = ''
  submitError.value = ''
  submitSuccess.value = ''
  submitting.value = false
}

// Reset the form whenever the modal closes so the next open starts clean.
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
  submitSuccess.value = ''
  if (!f) return
  if (f.size > MAX_IMPORT_BYTES) {
    fileError.value = `Fichier trop volumineux (${Math.round(f.size / 1024)} Ko, max 256 Ko)`
    return
  }
  // Client-side parse: surface obvious errors and give the user a quick
  // count of rows in the payload before they commit.
  try {
    const text = await f.text()
    const parsed = JSON.parse(text)
    const count = Array.isArray(parsed?.templates) ? parsed.templates.length : 0
    if (count === 0) {
      fileError.value = 'Aucun template trouvé dans ce fichier'
      return
    }
    fileInfo.value = `${count} template${count > 1 ? 's' : ''} dans le fichier`
  } catch {
    fileError.value = 'Fichier JSON invalide'
  }
}

async function submit(): Promise<void> {
  if (!file.value) return
  submitting.value = true
  submitError.value = ''
  submitSuccess.value = ''
  try {
    const result = await store.importCatalog(file.value)
    submitSuccess.value = `Importé : ${result.imported}`
    emit('imported')
    // Leave the modal open briefly so the user sees the success message,
    // then close on their own click. This mirrors RotateCredentialsModal's
    // UX — no auto-dismiss.
  } catch (e: unknown) {
    if (e instanceof ApiError) {
      const body = e.body as { error?: string } | undefined
      submitError.value = body?.error ?? e.message
    } else if (e instanceof Error) {
      submitError.value = e.message
    } else {
      submitError.value = "Échec de l'import"
    }
  } finally {
    submitting.value = false
  }
}
</script>
