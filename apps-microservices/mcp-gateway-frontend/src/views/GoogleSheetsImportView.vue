<template>
  <div>
    <!-- Page header -->
    <div class="mb-6 flex items-center gap-4">
      <button
        type="button"
        class="inline-flex items-center gap-1.5 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
        @click="router.push('/servers')"
      >
        <i class="pi pi-arrow-left text-xs" />
        Retour
      </button>
      <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
        Import Google Sheets
      </h1>
    </div>

    <div class="max-w-3xl mx-auto">
      <!-- Loading -->
      <div v-if="checkingConnection" class="flex items-center justify-center py-20">
        <i class="pi pi-spinner pi-spin text-2xl text-gray-400 dark:text-gray-500" />
      </div>

      <!-- Not connected -->
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

      <template v-else>
        <!-- Step tabs -->
        <StepTabs
          :steps="stepLabels"
          :current-step="currentStep"
          :completed-steps="completedSteps"
          @update:current-step="goToStep"
        />

        <!-- Card container -->
        <div class="bg-white dark:bg-gray-900 rounded-lg shadow-theme-xs border border-gray-200 dark:border-gray-800 p-6">

          <!-- Step 0: Spreadsheet ID -->
          <div v-show="currentStep === 0" class="space-y-4">
            <div>
              <label for="spreadsheet-id" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                ID du Spreadsheet <span class="text-red-500">*</span>
              </label>
              <input
                id="spreadsheet-id"
                v-model="spreadsheetId"
                type="text"
                class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
                placeholder="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms"
              />
              <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
                <i v-if="loadingInfo" class="pi pi-spinner pi-spin mr-1" />
                <template v-else>
                  L'ID se trouve dans l'URL : docs.google.com/spreadsheets/d/<strong>ID_ICI</strong>/edit
                </template>
              </p>
            </div>

            <!-- Sheet info (loaded after entering ID) -->
            <div v-if="sheetInfo" class="p-4 rounded-lg border border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50">
              <p class="text-sm font-medium text-gray-900 dark:text-white mb-3">
                <i class="pi pi-table mr-1" />
                {{ sheetInfo.title }}
              </p>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Feuille à importer
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

            <!-- Preview -->
            <SheetPreview v-if="preview" :headers="preview.headers" :rows="preview.rows" :total-rows="preview.total_rows" />
          </div>

          <!-- Step 1: Column mapping -->
          <div v-show="currentStep === 1" class="space-y-4">
            <!-- Name prefix -->
            <div>
              <label for="name-prefix" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Préfixe des noms de serveur
              </label>
              <input
                id="name-prefix"
                v-model="namePrefix"
                type="text"
                class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
                placeholder="ex: prod-"
              />
              <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
                Ajouté devant chaque nom de serveur importé (optionnel)
              </p>
            </div>

            <ColumnMappingTable
              v-if="preview"
              :headers="preview.headers"
              v-model="columnMapping"
              v-model:fixed-tags="fixedTags"
              v-model:fixed-tool-prefix="fixedToolPrefix"
            />

            <!-- Icon picker -->
            <IconPicker v-model="fixedIcon" />

            <div class="flex items-center gap-2">
              <input
                id="gsheet-discover"
                v-model="autoDiscover"
                type="checkbox"
                class="rounded border-gray-300 text-brand-500 dark:border-gray-700"
              />
              <label for="gsheet-discover" class="text-sm text-gray-700 dark:text-gray-300">
                Découvrir automatiquement après import
              </label>
            </div>
          </div>

          <!-- Step 2: Results -->
          <div v-show="currentStep === 2" class="space-y-4">
            <div v-if="importResult">
              <p class="text-sm font-medium text-gray-800 dark:text-gray-200 mb-3">
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
                  <span class="font-medium text-gray-800 dark:text-gray-200">{{ item.name }}</span>
                  <span v-if="item.message" class="text-gray-500 dark:text-gray-400">— {{ item.message }}</span>
                </li>
              </ul>
            </div>
          </div>
        </div>

        <!-- Navigation buttons -->
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
              @click="router.push('/servers')"
            >
              {{ currentStep === 2 ? 'Fermer' : 'Annuler' }}
            </button>

            <!-- Step 0 → 1: Next -->
            <button
              v-if="currentStep === 0 && preview"
              type="button"
              class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600"
              @click="currentStep = 1"
            >
              Suivant
            </button>

            <!-- Step 1 → 2: Import -->
            <button
              v-if="currentStep === 1"
              type="button"
              class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600 disabled:opacity-50"
              :disabled="!columnMapping.name || !columnMapping.url || importing"
              @click="handleImport"
            >
              <i v-if="importing" class="pi pi-spinner pi-spin mr-1" />
              Importer {{ preview?.total_rows || 0 }} ligne(s)
            </button>

            <!-- Step 2: New import -->
            <button
              v-if="currentStep === 2"
              type="button"
              class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600"
              @click="resetFlow"
            >
              Nouvel import
            </button>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { googleApi } from '@/api/google'
import { useToast } from '@/composables/useToast'
import StepTabs from '@/components/shared/StepTabs.vue'
import SheetPreview from '@/components/google/SheetPreview.vue'
import ColumnMappingTable from '@/components/google/ColumnMappingTable.vue'
import IconPicker from '@/components/servers/IconPicker.vue'
import type {
  SheetInfo,
  SheetPreview as SheetPreviewType,
  ColumnMapping,
  SheetImportResponse
} from '@/types/google'

const router = useRouter()
const toast = useToast()

const stepLabels = ['Sélection', 'Mapping', 'Résultats']
const checkingConnection = ref(true)
const googleConnected = ref(false)
const currentStep = ref(0)

// Step 0
const spreadsheetId = ref('')
const loadingInfo = ref(false)
const sheetInfo = ref<SheetInfo | null>(null)
const selectedSheet = ref('')
const preview = ref<SheetPreviewType | null>(null)

// Step 1
const namePrefix = ref('')
const columnMapping = ref<ColumnMapping>({ name: '', url: '' })
const fixedTags = ref('')
const fixedToolPrefix = ref('')
const fixedIcon = ref('')
const autoDiscover = ref(true)
const importing = ref(false)

// Step 2
const importResult = ref<SheetImportResponse | null>(null)

const completedSteps = computed(() => {
  const completed: number[] = []
  if (preview.value) completed.push(0)
  if (preview.value && columnMapping.value.name && columnMapping.value.url) completed.push(1)
  return completed
})

let debounceTimer: ReturnType<typeof setTimeout> | null = null

watch(spreadsheetId, (val) => {
  if (debounceTimer) clearTimeout(debounceTimer)
  if (val.trim()) {
    debounceTimer = setTimeout(() => loadSpreadsheetInfo(), 600)
  } else {
    sheetInfo.value = null
    selectedSheet.value = ''
    preview.value = null
  }
})

onMounted(async () => {
  try {
    const status = await googleApi.getStatus()
    googleConnected.value = status.connected
  } catch {
    googleConnected.value = false
  } finally {
    checkingConnection.value = false
  }
})

function goToStep(step: number) {
  if (step < currentStep.value || completedSteps.value.includes(step)) {
    currentStep.value = step
  }
}

async function loadSpreadsheetInfo() {
  if (!spreadsheetId.value.trim()) return
  loadingInfo.value = true
  sheetInfo.value = null
  selectedSheet.value = ''
  preview.value = null

  try {
    sheetInfo.value = await googleApi.getSheetInfo(spreadsheetId.value.trim())
    if (sheetInfo.value.sheets.length === 1) {
      await selectSheet(sheetInfo.value.sheets[0] ?? '')
    }
  } catch {
    toast.error("Impossible de charger la feuille. Vérifiez l'ID et vos droits d'accès.")
  } finally {
    loadingInfo.value = false
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

function autoDetectMapping() {
  if (!preview.value) return

  const normalize = (s: string) => s.toLowerCase().replace(/[\s_-]/g, '')
  const headers = preview.value.headers

  const fieldMap: Record<string, string[]> = {
    name: ['name', 'servername', 'nom', 'nomserveur'],
    url: ['url', 'serverurl', 'adresse', 'endpoint'],
    auth_headers: ['authheaders', 'headers', 'auth'],
    tags: ['tags', 'tag', 'etiquettes'],
    transport_preference: ['transportpreference', 'transport'],
    connect_timeout_ms: ['connecttimeoutms', 'timeout'],
    tool_prefix: ['toolprefix', 'prefix'],
    icon: ['icon', 'icone'],
    mcp_transport: ['mcptransport'],
    mcp_command: ['mcpcommand', 'command', 'commande'],
    mcp_args: ['mcpargs', 'args', 'arguments'],
    mcp_env: ['mcpenv', 'env', 'environnement'],
    doc_slug: ['docslug', 'slug'],
    doc_description: ['docdescription', 'description'],
  }

  const newMapping: Record<string, string> = {}
  for (const [field, aliases] of Object.entries(fieldMap)) {
    for (const header of headers) {
      const normalized = normalize(header)
      if (aliases.includes(normalized)) {
        newMapping[field] = header
        break
      }
    }
  }
  columnMapping.value = { name: '', url: '', ...newMapping } as ColumnMapping
}

async function handleImport() {
  if (!sheetInfo.value || !selectedSheet.value) return
  importing.value = true

  try {
    importResult.value = await googleApi.importFromSheet({
      spreadsheet_id: sheetInfo.value.spreadsheet_id,
      sheet_name: selectedSheet.value,
      column_mapping: columnMapping.value,
      auto_discover: autoDiscover.value,
      name_prefix: namePrefix.value || undefined,
      fixed_tags: fixedTags.value || undefined,
      fixed_tool_prefix: fixedToolPrefix.value || undefined,
      fixed_icon: fixedIcon.value || undefined,
    })
    currentStep.value = 2
  } catch (err: unknown) {
    toast.error(err instanceof Error ? err.message : "Erreur lors de l'import")
  } finally {
    importing.value = false
  }
}

function resetFlow() {
  currentStep.value = 0
  spreadsheetId.value = ''
  sheetInfo.value = null
  selectedSheet.value = ''
  preview.value = null
  namePrefix.value = ''
  columnMapping.value = { name: '', url: '' }
  fixedTags.value = ''
  fixedToolPrefix.value = ''
  fixedIcon.value = ''
  importResult.value = null
}
</script>
