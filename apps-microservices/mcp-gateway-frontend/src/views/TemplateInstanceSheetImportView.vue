<template>
  <div>
    <!-- Page header -->
    <div class="mb-6 flex items-center gap-4">
      <button
        type="button"
        class="inline-flex items-center gap-1.5 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
        @click="router.push({ name: 'template-detail', params: { slug } })"
      >
        <i class="pi pi-arrow-left text-xs" />
        Retour
      </button>
      <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
        {{ template ? `Import Sheets — ${template.name}` : 'Import depuis Sheets' }}
      </h1>
    </div>

    <div class="max-w-3xl mx-auto">
      <!-- Connection check -->
      <div v-if="checkingConnection" class="flex items-center justify-center py-20">
        <i class="pi pi-spinner pi-spin text-2xl text-gray-400 dark:text-gray-500" />
      </div>

      <!-- Not connected to Google -->
      <div v-else-if="!googleConnected" class="text-center py-12">
        <i class="pi pi-lock text-4xl text-gray-300 dark:text-gray-600 mb-3 block" />
        <p class="text-gray-500 dark:text-gray-400 mb-4">
          Connectez votre compte Google pour importer depuis vos feuilles de calcul.
        </p>
        <router-link
          to="/settings"
          class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600"
        >
          Aller aux paramètres
        </router-link>
      </div>

      <!-- Template missing -->
      <div
        v-else-if="!template && !loadingTemplate"
        class="text-center py-12 text-gray-500 dark:text-gray-400"
      >
        <i class="pi pi-exclamation-circle text-4xl mb-3 block" />
        <p>Template introuvable.</p>
        <router-link
          :to="{ name: 'templates' }"
          class="text-xs text-brand-500 hover:text-brand-600 mt-2 inline-block"
        >
          Retour au catalogue
        </router-link>
      </div>

      <template v-else-if="template">
        <!-- Step tabs -->
        <StepTabs
          :steps="stepLabels"
          :current-step="currentStep"
          :completed-steps="completedSteps"
          @update:current-step="goToStep"
        />

        <div class="bg-white dark:bg-gray-900 rounded-lg shadow-theme-xs border border-gray-200 dark:border-gray-800 p-6">
          <!-- Step 0: Sélection -->
          <div v-show="currentStep === 0" class="space-y-4">
            <!-- Spreadsheet ID / URL input (Drive list API is blocked by some
                 Workspace domain policies — paste-ID uses the Sheets API only). -->
            <div>
              <label for="spreadsheet-id" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                ID ou URL du Spreadsheet <span class="text-red-500">*</span>
              </label>
              <div class="flex gap-2">
                <input
                  id="spreadsheet-id"
                  v-model="spreadsheetIdInput"
                  type="text"
                  :disabled="loadingSheetInfo"
                  class="h-11 flex-1 rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30 disabled:opacity-60"
                  placeholder="Collez l'ID ou l'URL complète du spreadsheet"
                  @keyup.enter="loadSheetInfoFromInput"
                />
                <button
                  type="button"
                  :disabled="!spreadsheetIdInput.trim() || loadingSheetInfo"
                  class="px-4 py-2 text-sm font-medium text-white bg-brand-500 hover:bg-brand-600 disabled:opacity-50 disabled:cursor-not-allowed rounded-md flex items-center gap-2 shrink-0"
                  @click="loadSheetInfoFromInput"
                >
                  <i v-if="loadingSheetInfo" class="pi pi-spinner pi-spin text-xs" />
                  <i v-else class="pi pi-check text-xs" />
                  Charger
                </button>
              </div>
              <p v-if="sheetInfo" class="text-xs text-gray-500 dark:text-gray-400 mt-2">
                <i class="pi pi-file text-[11px] mr-1" />
                <strong>{{ sheetInfo.title }}</strong>
                <span class="text-gray-400 dark:text-gray-500 ml-2">— {{ sheetInfo.sheets.length }} feuille(s)</span>
              </p>
              <p v-else class="text-xs text-gray-400 dark:text-gray-500 mt-1">
                Exemple : <code class="font-mono">1A2b...xYz</code> ou <code class="font-mono">https://docs.google.com/spreadsheets/d/.../edit</code>
              </p>
            </div>

            <!-- Sheet dropdown -->
            <div v-if="sheetInfo">
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Feuille à importer <span class="text-red-500">*</span>
              </label>
              <div class="flex flex-wrap gap-2">
                <button
                  v-for="s in sheetInfo.sheets"
                  :key="s"
                  type="button"
                  :class="[
                    'px-3 py-1.5 text-sm rounded-lg border transition-colors',
                    selectedSheet === s
                      ? 'bg-brand-500 text-white border-brand-500'
                      : 'border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
                  ]"
                  @click="selectSheet(s)"
                >
                  {{ s }}
                </button>
              </div>
            </div>

            <!-- Preview (read-only) -->
            <SheetPreview v-if="preview" :headers="preview.headers" :rows="preview.rows" :total-rows="preview.total_rows" />
          </div>

          <!-- Step 1: Mapping -->
          <div v-show="currentStep === 1" class="space-y-4">
            <div v-if="!preview" class="text-sm text-gray-500 dark:text-gray-400">
              Aucune prévisualisation disponible.
            </div>
            <template v-else>
              <!-- Required column mappings -->
              <div class="space-y-3 border border-gray-200 dark:border-gray-800 rounded-md p-4">
                <p class="text-xs font-semibold text-gray-700 dark:text-gray-300">
                  Mapping des colonnes
                </p>

                <div>
                  <label for="map-name" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Colonne Nom <span class="text-red-500">*</span>
                  </label>
                  <select
                    id="map-name"
                    v-model="nameColumn"
                    class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90"
                  >
                    <option value="">—</option>
                    <option v-for="h in preview.headers" :key="h" :value="h">{{ h }}</option>
                  </select>
                </div>

                <div>
                  <label for="map-creds" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Colonne Credentials JSON <span class="text-red-500">*</span>
                  </label>
                  <select
                    id="map-creds"
                    v-model="credentialsColumn"
                    class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90"
                  >
                    <option value="">—</option>
                    <option v-for="h in preview.headers" :key="h" :value="h">{{ h }}</option>
                  </select>
                  <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
                    Cellule contenant la clé de service complète (JSON) en texte brut.
                  </p>
                </div>

                <!-- Dynamic per-field mappings -->
                <div
                  v-for="field in template.required_extra_env || []"
                  :key="field.key"
                  class="space-y-1"
                >
                  <label
                    :for="`map-env-${field.key}`"
                    class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
                  >
                    {{ field.label }}
                    <code class="ml-1 font-mono text-[11px] text-gray-500 dark:text-gray-400">
                      {{ field.key }}
                    </code>
                    <span v-if="field.required" class="text-red-500">*</span>
                  </label>
                  <select
                    :id="`map-env-${field.key}`"
                    v-model="extraEnvColumns[field.key]"
                    class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90"
                  >
                    <option value="">—</option>
                    <option v-for="h in preview.headers" :key="h" :value="h">{{ h }}</option>
                  </select>
                </div>
              </div>

              <!-- Overrides -->
              <div class="space-y-3 border border-gray-200 dark:border-gray-800 rounded-md p-4">
                <p class="text-xs font-semibold text-gray-700 dark:text-gray-300">
                  Overrides appliqués à toutes les instances
                </p>

                <div>
                  <label for="name-prefix" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Préfixe de nom
                  </label>
                  <input
                    id="name-prefix"
                    v-model="namePrefix"
                    type="text"
                    class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
                    placeholder="Ex: prod-"
                  />
                </div>

                <div>
                  <label for="fixed-tags" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Tags fixes (séparés par virgule)
                  </label>
                  <input
                    id="fixed-tags"
                    v-model="fixedTags"
                    type="text"
                    class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
                    placeholder="ex: ga4, prod"
                  />
                </div>

                <div>
                  <label for="fixed-tool-prefix" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Préfixe d'outils (alphanumérique)
                  </label>
                  <input
                    id="fixed-tool-prefix"
                    v-model="fixedToolPrefix"
                    type="text"
                    pattern="[a-zA-Z0-9]*"
                    class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
                    placeholder="myprefix"
                  />
                </div>

                <IconPicker v-model="fixedIcon" />

                <div class="flex items-center gap-2">
                  <input
                    id="sheet-instance-discover"
                    v-model="autoDiscover"
                    type="checkbox"
                    class="rounded border-gray-300 text-brand-500 dark:border-gray-700"
                  />
                  <label for="sheet-instance-discover" class="text-sm text-gray-700 dark:text-gray-300">
                    Découvrir automatiquement les outils après création
                  </label>
                </div>
              </div>
            </template>
          </div>

          <!-- Step 2: Résultats -->
          <div v-show="currentStep === 2" class="space-y-4">
            <div v-if="importResult">
              <p class="text-sm font-medium text-gray-800 dark:text-gray-200 mb-3">
                {{ importResult.total }} total —
                {{ importResult.imported }} importé{{ importResult.imported > 1 ? 's' : '' }},
                {{ importResult.skipped }} ignoré{{ importResult.skipped > 1 ? 's' : '' }},
                {{ importResult.errors }} erreur{{ importResult.errors > 1 ? 's' : '' }}
              </p>
              <ul class="space-y-1 max-h-96 overflow-y-auto">
                <li
                  v-for="item in importResult.results"
                  :key="item.row"
                  class="flex items-center gap-2 text-sm"
                >
                  <i
                    :class="{
                      'pi pi-check-circle text-success-600 dark:text-success-400': item.status === 'imported',
                      'pi pi-question-circle text-warning-500 dark:text-warning-400': item.status === 'skipped',
                      'pi pi-times-circle text-error-500 dark:text-error-400': item.status === 'error'
                    }"
                    class="text-sm"
                  />
                  <span class="text-gray-400 dark:text-gray-500 text-xs">L{{ item.row }}</span>
                  <span class="font-medium text-gray-800 dark:text-gray-200">{{ item.name || '—' }}</span>
                  <span v-if="item.message" class="text-gray-500 dark:text-gray-400">— {{ item.message }}</span>
                </li>
              </ul>
            </div>
          </div>
        </div>

        <!-- Navigation -->
        <div class="flex justify-between mt-6">
          <button
            v-if="currentStep > 0 && currentStep < 2"
            type="button"
            class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-white/5 rounded-md hover:bg-gray-200 dark:hover:bg-gray-700"
            @click="currentStep--"
          >
            Précédent
          </button>
          <div v-else />

          <div class="flex gap-3">
            <button
              type="button"
              class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-white/5 rounded-md hover:bg-gray-200 dark:hover:bg-gray-700"
              @click="close"
            >
              {{ currentStep === 2 ? 'Fermer' : 'Annuler' }}
            </button>

            <button
              v-if="currentStep === 0"
              type="button"
              class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600 disabled:opacity-50"
              :disabled="!isStep0Valid"
              @click="currentStep = 1"
            >
              Suivant
            </button>

            <button
              v-if="currentStep === 1"
              type="button"
              class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600 disabled:opacity-50"
              :disabled="!isStep1Valid || importing"
              @click="handleImport"
            >
              <i v-if="importing" class="pi pi-spinner pi-spin mr-1" />
              Importer {{ preview?.total_rows || 0 }} ligne(s)
            </button>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { googleApi } from '@/api/google'
import { templatesApi } from '@/api/templates'
import { useToast } from '@/composables/useToast'
import StepTabs from '@/components/shared/StepTabs.vue'
import SheetPreview from '@/components/google/SheetPreview.vue'
import IconPicker from '@/components/servers/IconPicker.vue'
import type {
  SheetInfo,
  SheetPreview as SheetPreviewType,
  SheetImportResponse
} from '@/types/google'
import type { Template } from '@/types/templates'

const props = defineProps<{ slug: string }>()

const router = useRouter()
const toast = useToast()

const stepLabels = ['Sélection', 'Mapping', 'Résultats']

// Connection state
const checkingConnection = ref(true)
const googleConnected = ref(false)

// Template state
const loadingTemplate = ref(false)
const template = ref<Template | null>(null)

// Step state
const currentStep = ref(0)

// Step 0: selection — paste-ID flow only. The Drive list API is blocked by
// some Workspace domain policies (domainPolicy 403); pasting the ID uses the
// Sheets API directly which is unaffected.
const spreadsheetIdInput = ref('')
const loadingSheetInfo = ref(false)
const sheetInfo = ref<SheetInfo | null>(null)
const selectedSheet = ref('')
const preview = ref<SheetPreviewType | null>(null)

// Step 1: mapping
const nameColumn = ref('')
const credentialsColumn = ref('')
const extraEnvColumns = reactive<Record<string, string>>({})
const namePrefix = ref('')
const fixedTags = ref('')
const fixedToolPrefix = ref('')
const fixedIcon = ref('')
const autoDiscover = ref(true)

// Step 2: results
const importing = ref(false)
const importResult = ref<SheetImportResponse | null>(null)

const isStep0Valid = computed(() => {
  return Boolean(sheetInfo.value && selectedSheet.value && preview.value)
})

const isStep1Valid = computed(() => {
  if (!template.value) return false
  if (!nameColumn.value || !credentialsColumn.value) return false
  if (fixedToolPrefix.value && !/^[a-zA-Z0-9]*$/.test(fixedToolPrefix.value)) return false
  for (const field of template.value.required_extra_env || []) {
    if (field.required && !(extraEnvColumns[field.key] || '').trim()) {
      return false
    }
  }
  return true
})

const completedSteps = computed(() => {
  const completed: number[] = []
  if (isStep0Valid.value) completed.push(0)
  if (isStep0Valid.value && isStep1Valid.value) completed.push(1)
  return completed
})

onMounted(async () => {
  // Google connection check.
  try {
    const status = await googleApi.getStatus()
    googleConnected.value = status.connected
  } catch {
    googleConnected.value = false
  } finally {
    checkingConnection.value = false
  }

  // Template — slug comes from the route so there's no selector.
  loadingTemplate.value = true
  try {
    template.value = await templatesApi.get(props.slug)
  } catch {
    template.value = null
  } finally {
    loadingTemplate.value = false
  }
})

// normaliseSpreadsheetInput wraps a raw ID in a full Sheets URL so the backend
// URL parser always has something to extract from. Pass-through for URLs.
function normaliseSpreadsheetInput(raw: string): string {
  const trimmed = raw.trim()
  if (!trimmed) return ''
  if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) return trimmed
  return `https://docs.google.com/spreadsheets/d/${trimmed}/edit`
}

async function loadSheetInfoFromInput(): Promise<void> {
  const url = normaliseSpreadsheetInput(spreadsheetIdInput.value)
  if (!url) return
  loadingSheetInfo.value = true
  sheetInfo.value = null
  selectedSheet.value = ''
  preview.value = null
  try {
    sheetInfo.value = await googleApi.getSheetInfo(url)
    if (sheetInfo.value.sheets.length === 1) {
      await selectSheet(sheetInfo.value.sheets[0] ?? '')
    }
  } catch (e: unknown) {
    toast.error(e instanceof Error ? e.message : 'Impossible de charger le spreadsheet')
  } finally {
    loadingSheetInfo.value = false
  }
}

async function selectSheet(name: string) {
  if (!sheetInfo.value || !name) return
  selectedSheet.value = name
  preview.value = null
  try {
    preview.value = await googleApi.getSheetPreview(sheetInfo.value.spreadsheet_id, name)
    autoDetectMapping()
  } catch {
    toast.error('Impossible de charger la prévisualisation')
  }
}

// Best-effort header auto-detection — name and credentials columns first,
// then every required_extra_env key by case-insensitive match.
function autoDetectMapping() {
  if (!preview.value || !template.value) return
  const normalize = (s: string) => s.toLowerCase().replace(/[\s_-]/g, '')
  const headers = preview.value.headers

  const findHeader = (candidates: string[]): string => {
    for (const h of headers) {
      const n = normalize(h)
      if (candidates.includes(n)) return h
    }
    return ''
  }

  nameColumn.value = nameColumn.value || findHeader(['name', 'nom', 'instancename'])
  credentialsColumn.value = credentialsColumn.value || findHeader(['credentials', 'creds', 'credentialsjson', 'serviceaccount'])

  for (const field of template.value.required_extra_env || []) {
    if (extraEnvColumns[field.key]) continue
    const keyNorm = normalize(field.key)
    const labelNorm = normalize(field.label)
    const match = headers.find(h => {
      const n = normalize(h)
      return n === keyNorm || n === labelNorm
    })
    if (match) extraEnvColumns[field.key] = match
  }
}

function goToStep(step: number) {
  if (step < currentStep.value || completedSteps.value.includes(step)) {
    currentStep.value = step
  }
}

async function handleImport() {
  if (!sheetInfo.value || !selectedSheet.value) return
  importing.value = true
  try {
    // Only send non-empty mappings — backend only requires `required: true` keys.
    const envCleaned: Record<string, string> = {}
    for (const [k, v] of Object.entries(extraEnvColumns)) {
      if (v && v.trim()) envCleaned[k] = v
    }
    importResult.value = await googleApi.importInstancesFromSheet({
      spreadsheet_id: sheetInfo.value.spreadsheet_id,
      sheet_name: selectedSheet.value,
      template_slug: props.slug,
      name_column: nameColumn.value,
      credentials_column: credentialsColumn.value,
      extra_env_columns: Object.keys(envCleaned).length ? envCleaned : undefined,
      name_prefix: namePrefix.value || undefined,
      fixed_tags: fixedTags.value || undefined,
      fixed_tool_prefix: fixedToolPrefix.value || undefined,
      fixed_icon: fixedIcon.value || undefined,
      auto_discover: autoDiscover.value || undefined
    })
    currentStep.value = 2
  } catch (err: unknown) {
    toast.error(err instanceof Error ? err.message : "Erreur lors de l'import")
  } finally {
    importing.value = false
  }
}

function close() {
  router.push({ name: 'template-detail', params: { slug: props.slug } })
}
</script>
