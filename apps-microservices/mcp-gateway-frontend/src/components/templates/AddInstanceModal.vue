<template>
  <DialogRoot :open="open" @update:open="emit('update:open', $event)">
    <DialogPortal>
      <DialogOverlay class="fixed inset-0 bg-black/50 z-50" />
      <DialogContent
        class="fixed left-1/2 top-1/2 z-50 w-full max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-lg bg-white dark:bg-gray-900 p-6 shadow-theme-xl max-h-[90vh] overflow-y-auto"
      >
        <DialogTitle class="text-lg font-semibold text-gray-900 dark:text-white">
          Ajouter une instance {{ template.name }}
        </DialogTitle>
        <DialogDescription class="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Renseignez un nom, les variables requises, et importez le fichier JSON du compte de service.
        </DialogDescription>

        <form class="mt-5 space-y-5" @submit.prevent="submit">
          <!-- Name -->
          <div>
            <label
              for="instance-name"
              class="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1"
            >
              Nom <span class="text-error-500">*</span>
            </label>
            <input
              id="instance-name"
              v-model="name"
              type="text"
              maxlength="255"
              required
              autocomplete="off"
              class="w-full px-3 py-2 text-sm rounded-md border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-brand-500"
              placeholder="Ex: projet-ventes-europe"
            />
          </div>

          <!-- Required extra env -->
          <fieldset
            v-if="template.required_extra_env && template.required_extra_env.length > 0"
            class="space-y-3 border border-gray-200 dark:border-gray-800 rounded-md p-4"
          >
            <legend class="px-1 text-xs font-semibold text-gray-700 dark:text-gray-300">
              Variables d'environnement
            </legend>
            <div
              v-for="field in template.required_extra_env"
              :key="field.key"
              class="space-y-1"
            >
              <label
                :for="`env-${field.key}`"
                class="block text-xs font-medium text-gray-700 dark:text-gray-300"
              >
                {{ field.label }}
                <code class="ml-1 font-mono text-[11px] text-gray-500 dark:text-gray-400">
                  {{ field.key }}
                </code>
                <span v-if="field.required" class="text-error-500">*</span>
              </label>
              <input
                :id="`env-${field.key}`"
                v-model="extraEnv[field.key]"
                type="text"
                :required="field.required"
                autocomplete="off"
                class="w-full px-3 py-2 text-sm rounded-md border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>
          </fieldset>

          <!-- Service account JSON file -->
          <div>
            <label
              for="instance-credentials"
              class="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1"
            >
              Clé JSON du compte de service <span class="text-error-500">*</span>
            </label>
            <input
              id="instance-credentials"
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
              Fichier JSON (max 16 Ko). Le contenu ne quitte jamais le navigateur tant que vous ne cliquez pas sur Créer.
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
              {{ submitting ? 'Création…' : "Créer l'instance" }}
            </button>
          </div>
        </form>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
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
import type { Template, TemplateInstance } from '@/types/templates'

const props = defineProps<{
  template: Template
  open: boolean
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  created: [instance: TemplateInstance]
}>()

const store = useTemplatesStore()

const name = ref('')
const extraEnv = reactive<Record<string, string>>({})
const file = ref<File | null>(null)
const fileInfo = ref('')
const fileError = ref('')
const submitError = ref('')
const submitting = ref(false)

const MAX_SA_JSON_SIZE = 16 * 1024 // matches mcp-gateway-service validation.MaxSAJSONSize

const canSubmit = computed(
  () => !!name.value && !!file.value && !fileError.value && !submitting.value
)

function resetForm(): void {
  name.value = ''
  for (const k of Object.keys(extraEnv)) delete extraEnv[k]
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
  if (f.size > MAX_SA_JSON_SIZE) {
    fileError.value = 'Fichier trop volumineux (max 16 Ko)'
    return
  }
  const text = await f.text()
  try {
    const j = JSON.parse(text) as { type?: string; client_email?: string }
    if (j.type !== 'service_account') {
      fileError.value = `type est "${j.type ?? ''}", attendu "service_account"`
      return
    }
    if (!j.client_email) {
      fileError.value = 'client_email manquant'
      return
    }
    fileInfo.value = j.client_email
  } catch {
    fileError.value = 'JSON invalide'
  }
}

async function submit(): Promise<void> {
  if (!file.value) return
  submitting.value = true
  submitError.value = ''
  try {
    const inst = await store.createInstance({
      template_slug: props.template.slug,
      name: name.value,
      extra_env: Object.keys(extraEnv).length ? { ...extraEnv } : undefined,
      credentials: file.value
    })
    emit('created', inst)
    emit('update:open', false)
  } catch (e: unknown) {
    if (e instanceof ApiError) {
      const body = e.body as { error?: string } | undefined
      submitError.value = body?.error ?? e.message
    } else if (e instanceof Error) {
      submitError.value = e.message
    } else {
      submitError.value = 'Échec de la création'
    }
  } finally {
    submitting.value = false
  }
}
</script>
