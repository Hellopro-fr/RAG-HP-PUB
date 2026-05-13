<template>
  <DialogRoot :open="open" @update:open="emit('update:open', $event)">
    <DialogPortal>
      <DialogOverlay class="fixed inset-0 bg-black/50 z-50" />
      <DialogContent
        class="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg bg-white dark:bg-gray-900 p-6 shadow-theme-xl"
      >
        <DialogTitle class="text-base font-semibold text-gray-900 dark:text-white mb-3">
          {{ title }}
        </DialogTitle>
        <DialogDescription class="sr-only">
          Formulaire de modification d'un import Zoho
        </DialogDescription>

        <form class="space-y-3" @submit.prevent="onSubmit">
          <div>
            <label class="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">Nom</label>
            <input
              v-model="form.name"
              type="text"
              class="w-full h-9 text-sm rounded-md border border-gray-300 dark:border-gray-600 px-3 bg-white dark:bg-gray-800 dark:text-gray-200"
            />
          </div>
          <div>
            <label class="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">URL upstream</label>
            <input
              v-model="form.url"
              type="url"
              required
              class="w-full h-9 text-sm rounded-md border border-gray-300 dark:border-gray-600 px-3 bg-white dark:bg-gray-800 dark:text-gray-200"
            />
          </div>
          <div>
            <label class="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
              Auth headers (JSON)
              <span class="text-gray-400 dark:text-gray-500">— laissez vide pour ne pas modifier</span>
            </label>
            <textarea
              v-model="form.authHeadersJSON"
              rows="4"
              placeholder='{"Authorization":"Bearer ..."}'
              class="w-full text-xs font-mono rounded-md border border-gray-300 dark:border-gray-600 px-3 py-2 bg-white dark:bg-gray-800 dark:text-gray-200"
            />
            <p v-if="parseError" class="text-xs text-error-500 mt-1">{{ parseError }}</p>
          </div>
          <div class="flex gap-2 justify-end pt-2">
            <button
              type="button"
              class="px-3 py-1.5 text-sm rounded-md border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300"
              @click="close"
            >
              Annuler
            </button>
            <button
              type="submit"
              :disabled="submitting"
              class="px-3 py-1.5 text-sm rounded-md text-white bg-brand-500 hover:bg-brand-600 disabled:opacity-50"
            >
              {{ submitting ? '...' : 'Enregistrer' }}
            </button>
          </div>
        </form>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<script setup lang="ts">
import { ref, watch, reactive } from 'vue'
import {
  DialogRoot,
  DialogPortal,
  DialogOverlay,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from 'radix-vue'
import type { ZohoImportRow, ZohoImportUpdateRequest } from '@/types/zoho'

const props = defineProps<{
  open: boolean
  row: ZohoImportRow | null
  title: string
}>()

const emit = defineEmits<{
  'update:open': [v: boolean]
  submit: [patch: ZohoImportUpdateRequest]
}>()

const form = reactive({
  name: '',
  url: '',
  authHeadersJSON: '',
})
const parseError = ref('')
const submitting = ref(false)

watch(
  () => props.row,
  (r) => {
    form.name = r?.name ?? ''
    form.url = r?.url ?? ''
    form.authHeadersJSON = ''
    parseError.value = ''
  },
  { immediate: true }
)

function close() {
  emit('update:open', false)
}

function onSubmit() {
  parseError.value = ''
  const patch: ZohoImportUpdateRequest = {}

  if (props.row && form.name !== props.row.name) patch.name = form.name
  if (props.row && form.url !== props.row.url) patch.url = form.url
  if (!props.row) {
    if (form.name) patch.name = form.name
    if (form.url) patch.url = form.url
  }

  if (form.authHeadersJSON.trim()) {
    try {
      const parsed = JSON.parse(form.authHeadersJSON)
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        patch.auth_headers = parsed
      } else {
        parseError.value = 'Doit être un objet JSON {"clé":"valeur"}.'
        return
      }
    } catch {
      parseError.value = 'JSON invalide.'
      return
    }
  }

  submitting.value = true
  emit('submit', patch)
  submitting.value = false
}
</script>
