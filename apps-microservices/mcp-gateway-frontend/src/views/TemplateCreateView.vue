<template>
  <div>
    <div class="mb-6 flex items-center gap-4 flex-wrap">
      <button
        type="button"
        class="inline-flex items-center gap-1.5 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
        @click="router.push({ name: 'templates' })"
      >
        <i class="pi pi-arrow-left text-xs" />
        Retour
      </button>
      <h1 class="text-2xl font-bold text-gray-900 dark:text-white">Nouveau template</h1>
      <div class="ml-auto">
        <button
          id="import-json-button"
          type="button"
          class="inline-flex items-center gap-2 px-3 py-1.5 text-xs font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-md hover:bg-gray-50 dark:hover:bg-white/5"
          @click="fileInput?.click()"
        >
          <i class="pi pi-upload text-[11px]" />
          Importer JSON
        </button>
        <input
          id="import-json-file"
          ref="fileInput"
          type="file"
          accept=".json,application/json"
          class="hidden"
          @change="onFile"
        />
      </div>
    </div>

    <div class="max-w-3xl mx-auto">
      <p
        v-if="importError"
        id="import-error"
        class="mb-4 rounded-md bg-error-50 dark:bg-error-500/15 px-3 py-2 text-xs text-error-600 dark:text-error-400"
      >
        <i class="pi pi-exclamation-triangle text-[11px] mr-1" />
        {{ importError }}
      </p>

      <!-- Several templates in the file: pick the one that prefills the form -->
      <div
        v-if="importedRows.length > 1"
        class="mb-4 rounded-md border border-gray-200 dark:border-gray-800 p-4"
      >
        <label for="import-pick" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          Le fichier contient {{ importedRows.length }} templates : choisissez celui à préremplir
        </label>
        <select
          id="import-pick"
          v-model.number="pickedIndex"
          class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
          @change="applyPicked"
        >
          <option v-for="(r, i) in importedRows" :key="i" :value="i">{{ r.slug }} — {{ r.name }}</option>
        </select>
      </div>

      <form
        class="bg-white dark:bg-gray-900 rounded-lg shadow-theme-xs border border-gray-200 dark:border-gray-800 p-6 space-y-4"
        @submit.prevent="handleSubmit"
      >
        <div>
          <label for="tpl-slug" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Slug <span class="text-red-500">*</span>
          </label>
          <input
            id="tpl-slug"
            v-model="form.slug"
            type="text"
            maxlength="32"
            autocomplete="off"
            class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
            placeholder="ex: neo4j"
            @input="slugConflict = ''"
          />
          <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
            Minuscules, chiffres et tirets (32 max). Non modifiable après création.
          </p>
          <p v-if="slugError" id="tpl-slug-error" class="text-xs text-error-600 dark:text-error-400 mt-1">{{ slugError }}</p>
        </div>

        <div>
          <label for="tpl-name" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Nom <span class="text-red-500">*</span>
          </label>
          <input
            id="tpl-name"
            v-model="form.name"
            type="text"
            maxlength="128"
            autocomplete="off"
            class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
          />
        </div>

        <div>
          <label for="tpl-description" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Description</label>
          <textarea id="tpl-description" v-model="form.description" rows="2" class="w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30 font-mono" />
        </div>

        <IconPicker v-model="form.icon" />

        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label for="tpl-kind" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Type</label>
            <select id="tpl-kind" v-model="form.kind" class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30">
              <option value="stdio">stdio</option>
              <option value="http_batch">http_batch</option>
              <option v-if="kindUnknown" :value="form.kind">{{ form.kind }}</option>
            </select>
            <p v-if="kindUnknown" id="tpl-kind-warning" class="text-xs text-warning-600 dark:text-warning-400 mt-1">
              Valeur inconnue : {{ form.kind }} (la passerelle refusera ce template)
            </p>
          </div>
          <div>
            <label for="tpl-runner" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Runner</label>
            <select id="tpl-runner" v-model="form.runner" class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30">
              <option value="google">google</option>
              <option value="neo4j">neo4j</option>
              <option v-if="runnerUnknown" :value="form.runner">{{ form.runner }}</option>
            </select>
            <p v-if="runnerUnknown" id="tpl-runner-warning" class="text-xs text-warning-600 dark:text-warning-400 mt-1">
              Valeur inconnue : {{ form.runner }} (la passerelle refusera ce template)
            </p>
          </div>
        </div>

        <div>
          <label for="tpl-command" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Commande stdio <span v-if="form.kind === 'stdio'" class="text-red-500">*</span>
          </label>
          <input
            id="tpl-command"
            v-model="form.stdio_command"
            type="text"
            maxlength="256"
            autocomplete="off"
            class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
            placeholder="ex: mcp-proxy"
          />
        </div>

        <div>
          <label for="tpl-args" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Arguments stdio</label>
          <textarea id="tpl-args" v-model="form.stdio_args" rows="3" class="w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30 font-mono" />
          <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">Un argument par ligne</p>
        </div>

        <div>
          <label for="tpl-tool-prefix" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Préfixe d'outils</label>
          <input
            id="tpl-tool-prefix"
            v-model="form.tool_prefix"
            type="text"
            maxlength="64"
            class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
            placeholder="myprefix"
          />
          <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">Alphanumérique uniquement</p>
          <p v-if="!toolPrefixValid" class="text-xs text-error-600 dark:text-error-400 mt-1">
            Le préfixe ne doit contenir que des lettres et des chiffres
          </p>
        </div>

        <div>
          <label for="tpl-tags" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Tags</label>
          <input
            id="tpl-tags"
            v-model="form.tags"
            type="text"
            autocomplete="off"
            class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
            placeholder="analytics, google"
          />
          <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">Séparés par des virgules</p>
        </div>

        <div>
          <label for="tpl-default-env" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Variables d'environnement par défaut (JSON)</label>
          <textarea id="tpl-default-env" v-model="form.default_env" rows="4" class="w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30 font-mono" spellcheck="false" />
        </div>

        <div>
          <label for="tpl-required-env" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Variables à renseigner par instance (JSON)</label>
          <textarea id="tpl-required-env" v-model="form.required_extra_env" rows="4" class="w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30 font-mono" spellcheck="false" />
        </div>

        <div class="flex items-center gap-2">
          <input
            id="tpl-active"
            v-model="form.is_active"
            type="checkbox"
            class="rounded border-gray-300 text-brand-500 dark:border-gray-700"
          />
          <label for="tpl-active" class="text-sm text-gray-700 dark:text-gray-300">
            Actif (visible dans le catalogue)
          </label>
        </div>

        <div
          v-if="submitError"
          id="tpl-submit-error"
          class="rounded-md bg-error-50 dark:bg-error-500/15 px-3 py-2 text-xs text-error-600 dark:text-error-400"
        >
          <i class="pi pi-exclamation-triangle text-[11px] mr-1" />
          {{ submitError }}
        </div>

        <div class="flex justify-end gap-3 pt-2">
          <button
            type="button"
            class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-white/5 rounded-md hover:bg-gray-200 dark:hover:bg-gray-700"
            @click="router.push({ name: 'templates' })"
          >
            Annuler
          </button>
          <button
            id="tpl-submit"
            type="submit"
            class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600 disabled:opacity-50"
            :disabled="submitting || !isValid"
          >
            <i v-if="submitting" class="pi pi-spinner pi-spin mr-1" />
            Créer
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useTemplatesStore } from '@/stores/templates'
import { useToast } from '@/composables/useToast'
import { ApiError } from '@/types/api'
import IconPicker from '@/components/servers/IconPicker.vue'
import {
  emptyTemplateForm,
  formToRow,
  parseTemplateJson,
  rowToForm
} from '@/components/templates/templateJson'
import type { TemplateForm } from '@/components/templates/templateJson'
import type { TemplateExportRow } from '@/types/templates'

// Mirrors the gateway: templates.slug is varchar(32); these collide with routes.
const SLUG_RE = /^[a-z0-9][a-z0-9-]{0,31}$/
const RESERVED_SLUGS = ['export', 'import', 'new']

const router = useRouter()
const store = useTemplatesStore()
const toast = useToast()

const form = reactive<TemplateForm>(emptyTemplateForm())
const submitting = ref(false)
const submitError = ref('')
const slugConflict = ref('')
const importError = ref('')
const importedRows = ref<TemplateExportRow[]>([])
const pickedIndex = ref(0)
const fileInput = ref<HTMLInputElement | null>(null)

const slugError = computed(() => {
  if (slugConflict.value) return slugConflict.value
  const slug = form.slug.trim()
  if (!slug) return ''
  if (RESERVED_SLUGS.includes(slug)) return `Le slug « ${slug} » est réservé`
  if (!SLUG_RE.test(slug)) return 'Slug invalide : minuscules, chiffres et tirets uniquement'
  return ''
})

const kindUnknown = computed(() => !['stdio', 'http_batch'].includes(form.kind))
const runnerUnknown = computed(() => !['google', 'neo4j'].includes(form.runner))

const toolPrefixValid = computed(() => /^[a-zA-Z0-9]*$/.test(form.tool_prefix))

const isValid = computed(() => {
  const slug = form.slug.trim()
  if (!slug || !SLUG_RE.test(slug) || RESERVED_SLUGS.includes(slug) || slugConflict.value) return false
  if (!form.name.trim()) return false
  if (form.kind === 'stdio' && !form.stdio_command.trim()) return false
  return toolPrefixValid.value
})

function prefill(row: TemplateExportRow): void {
  Object.assign(form, rowToForm(row))
  slugConflict.value = ''
  submitError.value = ''
}

// Prefill only: nothing is sent until the admin clicks "Créer".
async function onFile(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  importError.value = ''
  importedRows.value = []
  try {
    const parsed = parseTemplateJson(await file.text())
    if ('error' in parsed) {
      importError.value = parsed.error
      return
    }
    importedRows.value = parsed.rows
    pickedIndex.value = 0
    prefill(parsed.rows[0]!)
  } catch {
    importError.value = 'Impossible de lire le fichier'
  } finally {
    // Allow re-selecting the same file.
    input.value = ''
  }
}

function applyPicked(): void {
  const row = importedRows.value[pickedIndex.value]
  if (row) prefill(row)
}

async function handleSubmit(): Promise<void> {
  if (!isValid.value || submitting.value) return
  const built = formToRow(form)
  if ('error' in built) {
    submitError.value = built.error
    return
  }
  submitting.value = true
  submitError.value = ''
  try {
    const created = await store.createTemplate(built.row)
    // Best-effort: the template exists, a failed list refresh is not a failed create.
    try {
      await store.fetchTemplates()
    } catch (refreshError) {
      console.warn('Template list refresh failed', refreshError)
    }
    toast.success('Template créé')
    router.push({ name: 'template-detail', params: { slug: created.slug } })
  } catch (e: unknown) {
    if (e instanceof ApiError) {
      const body = e.body as { error?: string } | undefined
      const message = body?.error ?? e.message
      if (e.status === 409) {
        slugConflict.value = message
      } else {
        submitError.value = message
      }
    } else if (e instanceof Error) {
      submitError.value = e.message
    } else {
      submitError.value = 'Échec de la création'
    }
    toast.error(slugConflict.value || submitError.value)
  } finally {
    submitting.value = false
  }
}
</script>
