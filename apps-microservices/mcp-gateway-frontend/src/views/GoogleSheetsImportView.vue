<template>
  <div>
    <PageBreadcrumb page-title="Import Google Sheets" />

    <!-- Loading status -->
    <div v-if="checkingConnection" class="text-center py-12">
      <i class="pi pi-spinner pi-spin text-2xl text-brand-500" />
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

    <!-- Connected -->
    <template v-else>
      <!-- Step indicator -->
      <div class="flex items-center gap-2 mb-6 mt-6">
        <span
          v-for="(label, i) in ['Sélection', 'Mapping', 'Résultats']"
          :key="i"
          :class="[
            'px-3 py-1 text-xs font-medium rounded-full',
            currentStep === i
              ? 'bg-brand-500 text-white'
              : currentStep > i
                ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                : 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400'
          ]"
        >
          {{ label }}
        </span>
      </div>

      <!-- Step 0: Spreadsheet selection -->
      <div v-show="currentStep === 0">

        <!-- URL fallback mode -->
        <template v-if="!driveAvailable">
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            URL de la feuille Google Sheets
          </label>
          <div class="flex gap-2 mb-4">
            <input
              v-model="spreadsheetUrl"
              type="text"
              placeholder="https://docs.google.com/spreadsheets/d/..."
              class="flex-1 rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
            />
            <button
              class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600 disabled:opacity-50 shrink-0"
              :disabled="!spreadsheetUrl.trim() || loadingInfo"
              @click="loadFromUrl"
            >
              <i v-if="loadingInfo" class="pi pi-spinner pi-spin mr-1" />
              Charger
            </button>
          </div>
        </template>

        <!-- Drive list mode -->
        <template v-else>
          <!-- Search bar -->
          <div class="flex gap-2 mb-4">
            <div class="relative flex-1">
              <i class="pi pi-search absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm" />
              <input
                v-model="searchQuery"
                type="text"
                placeholder="Rechercher une feuille de calcul..."
                class="w-full pl-9 pr-4 py-2.5 rounded-lg border border-gray-300 bg-transparent text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
                @input="debouncedSearch"
              />
            </div>
            <button
              class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700"
              :disabled="loadingSpreadsheets"
              @click="loadSpreadsheets"
            >
              <i v-if="loadingSpreadsheets" class="pi pi-spinner pi-spin mr-1" />
              <i v-else class="pi pi-refresh mr-1" />
              Actualiser
            </button>
          </div>

          <!-- Spreadsheet list -->
          <div v-if="loadingSpreadsheets && spreadsheets.length === 0" class="text-center py-8">
            <i class="pi pi-spinner pi-spin text-2xl text-brand-500" />
          </div>

          <div v-else-if="spreadsheets.length === 0" class="text-center py-8 text-gray-500 dark:text-gray-400">
            <i class="pi pi-file-excel text-4xl mb-3 block" />
            <p>Aucune feuille de calcul trouvée</p>
          </div>

          <div v-else class="grid grid-cols-1 gap-3">
            <div
              v-for="doc in spreadsheets"
              :key="doc.id"
              :class="[
                'rounded-xl border p-4 cursor-pointer transition-colors',
                selectedSpreadsheet?.id === doc.id
                  ? 'border-brand-500 bg-brand-50 dark:bg-brand-500/10 dark:border-brand-400'
                  : 'border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800 hover:border-gray-300 dark:hover:border-gray-600'
              ]"
              @click="selectSpreadsheet(doc)"
            >
              <div class="flex items-center gap-3">
                <div class="h-10 w-10 rounded-lg bg-green-100 dark:bg-green-900/30 flex items-center justify-center shrink-0">
                  <i class="pi pi-file-excel text-green-600 dark:text-green-400" />
                </div>
                <div class="min-w-0 flex-1">
                  <p class="text-sm font-medium text-gray-900 dark:text-white truncate">
                    {{ doc.name }}
                  </p>
                  <p class="text-xs text-gray-500 dark:text-gray-400">
                    Modifié le {{ formatDate(doc.modified_time) }}
                  </p>
                </div>
                <i v-if="selectedSpreadsheet?.id === doc.id" class="pi pi-check-circle text-brand-500" />
              </div>
            </div>
          </div>
        </template>

        <!-- Sheet tab selection (after selecting a spreadsheet) -->
        <div v-if="sheetInfo" class="mt-6 p-4 rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800">
          <p class="text-sm font-medium text-gray-900 dark:text-white mb-3">
            <i class="pi pi-table mr-1" />
            {{ sheetInfo.title }} — {{ sheetInfo.sheets.length }} feuille(s)
          </p>
          <div class="flex flex-wrap gap-2">
            <button
              v-for="s in sheetInfo.sheets"
              :key="s"
              :class="[
                'px-3 py-1.5 text-sm rounded-lg border transition-colors',
                selectedSheet === s
                  ? 'bg-brand-500 text-white border-brand-500'
                  : 'border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
              ]"
              @click="selectSheet(s)"
            >
              {{ s }}
            </button>
          </div>
        </div>

        <!-- Preview -->
        <div v-if="preview" class="mt-4">
          <SheetPreview :headers="preview.headers" :rows="preview.rows" :total-rows="preview.total_rows" />
          <div class="flex justify-end mt-4">
            <button
              class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600"
              @click="currentStep = 1"
            >
              Configurer le mapping
              <i class="pi pi-arrow-right ml-1" />
            </button>
          </div>
        </div>
      </div>

      <!-- Step 1: Column mapping -->
      <div v-show="currentStep === 1">
        <ColumnMappingTable
          v-if="preview"
          :headers="preview.headers"
          v-model="columnMapping"
        />

        <!-- Auto-discover -->
        <div class="flex items-center gap-2 mt-4">
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

        <div class="flex gap-2 mt-4">
          <button
            class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-white/5 rounded-md hover:bg-gray-200 dark:hover:bg-gray-700"
            @click="currentStep = 0"
          >
            <i class="pi pi-arrow-left mr-1" />
            Retour
          </button>
          <button
            class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600 disabled:opacity-50"
            :disabled="!columnMapping.name || !columnMapping.url || importing"
            @click="handleImport"
          >
            <i v-if="importing" class="pi pi-spinner pi-spin mr-1" />
            Importer {{ preview?.total_rows || 0 }} ligne(s)
          </button>
        </div>
      </div>

      <!-- Step 2: Results -->
      <div v-show="currentStep === 2">
        <div v-if="importResult" class="p-4 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl">
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
        <div class="flex gap-2 mt-4">
          <router-link
            to="/servers"
            class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600"
          >
            Voir les serveurs
          </router-link>
          <button
            class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-white/5 rounded-md hover:bg-gray-200 dark:hover:bg-gray-700"
            @click="resetFlow"
          >
            Nouvel import
          </button>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { googleApi } from '@/api/google'
import { useToast } from '@/composables/useToast'
import PageBreadcrumb from '@/components/common/PageBreadcrumb.vue'
import SheetPreview from '@/components/google/SheetPreview.vue'
import ColumnMappingTable from '@/components/google/ColumnMappingTable.vue'
import type {
  SpreadsheetListItem,
  SheetInfo,
  SheetPreview as SheetPreviewType,
  ColumnMapping,
  SheetImportResponse
} from '@/types/google'

const toast = useToast()

const checkingConnection = ref(true)
const googleConnected = ref(false)
const currentStep = ref(0)

// Step 0: Spreadsheet selection
const driveAvailable = ref(true)
const spreadsheetUrl = ref('')
const loadingInfo = ref(false)
const searchQuery = ref('')
const loadingSpreadsheets = ref(false)
const spreadsheets = ref<SpreadsheetListItem[]>([])
const selectedSpreadsheet = ref<SpreadsheetListItem | null>(null)
const sheetInfo = ref<SheetInfo | null>(null)
const selectedSheet = ref('')
const preview = ref<SheetPreviewType | null>(null)

// Step 1: Mapping
const columnMapping = ref<ColumnMapping>({ name: '', url: '' })
const autoDiscover = ref(true)
const importing = ref(false)

// Step 2: Results
const importResult = ref<SheetImportResponse | null>(null)

let searchTimeout: ReturnType<typeof setTimeout> | null = null

onMounted(async () => {
  try {
    const status = await googleApi.getStatus()
    googleConnected.value = status.connected
    if (status.connected) {
      await loadSpreadsheets()
    }
  } catch {
    googleConnected.value = false
  } finally {
    checkingConnection.value = false
  }
})

function debouncedSearch() {
  if (searchTimeout) clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => loadSpreadsheets(), 400)
}

async function loadSpreadsheets() {
  loadingSpreadsheets.value = true
  try {
    spreadsheets.value = await googleApi.listSpreadsheets(searchQuery.value || undefined)
  } catch {
    // Drive API blocked (e.g. domain policy) — fall back to URL input
    driveAvailable.value = false
  } finally {
    loadingSpreadsheets.value = false
  }
}

async function loadFromUrl() {
  if (!spreadsheetUrl.value.trim()) return
  loadingInfo.value = true
  sheetInfo.value = null
  selectedSheet.value = ''
  preview.value = null

  try {
    sheetInfo.value = await googleApi.getSheetInfo(spreadsheetUrl.value)
    if (sheetInfo.value.sheets.length === 1) {
      await selectSheet(sheetInfo.value.sheets[0] ?? '')
    }
  } catch {
    toast.error('Impossible de charger la feuille. Vérifiez l\'URL et vos droits d\'accès.')
  } finally {
    loadingInfo.value = false
  }
}

async function selectSpreadsheet(doc: SpreadsheetListItem) {
  selectedSpreadsheet.value = doc
  sheetInfo.value = null
  selectedSheet.value = ''
  preview.value = null

  try {
    // Use the spreadsheet ID directly (no URL parsing needed)
    sheetInfo.value = await googleApi.getSheetInfo(doc.id)
    if (sheetInfo.value.sheets.length === 1) {
      await selectSheet(sheetInfo.value.sheets[0] ?? '')
    }
  } catch {
    toast.error('Impossible de charger les feuilles')
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
  selectedSpreadsheet.value = null
  sheetInfo.value = null
  selectedSheet.value = ''
  preview.value = null
  columnMapping.value = { name: '', url: '' }
  importResult.value = null
  loadSpreadsheets()
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString('fr-FR', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  } catch {
    return iso
  }
}
</script>
