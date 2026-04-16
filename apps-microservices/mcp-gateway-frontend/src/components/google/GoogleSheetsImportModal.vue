<template>
  <div class="fixed inset-0 bg-black/50 z-50 flex items-center justify-center" @click.self="emit('close')">
    <div class="bg-white dark:bg-gray-900 rounded-lg shadow-theme-xl p-6 max-w-4xl w-full max-h-[90vh] overflow-y-auto">
      <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-4">
        Importer depuis Google Sheets
      </h2>

      <!-- Not connected -->
      <div v-if="!googleConnected" class="text-center py-8">
        <i class="pi pi-lock text-4xl text-gray-300 dark:text-gray-600 mb-3 block" />
        <p class="text-gray-500 dark:text-gray-400 mb-4">
          Connectez votre compte Google pour importer depuis vos feuilles de calcul.
        </p>
        <router-link
          to="/settings"
          class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600"
          @click="emit('close')"
        >
          Aller aux paramètres
        </router-link>
      </div>

      <!-- Connected: Step flow -->
      <template v-else>
        <!-- Step indicator -->
        <div class="flex items-center gap-2 mb-6">
          <span
            v-for="(label, i) in ['URL', 'Mapping', 'Résultats']"
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

        <!-- Step 0: URL input -->
        <div v-show="currentStep === 0">
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            URL de la feuille Google Sheets
          </label>
          <div class="flex gap-2">
            <input
              v-model="spreadsheetUrl"
              type="text"
              placeholder="https://docs.google.com/spreadsheets/d/..."
              class="flex-1 rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
            />
            <button
              class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600 disabled:opacity-50 shrink-0"
              :disabled="!spreadsheetUrl.trim() || loadingInfo"
              @click="loadSpreadsheetInfo"
            >
              <i v-if="loadingInfo" class="pi pi-spinner pi-spin mr-1" />
              Charger
            </button>
          </div>
          <p v-if="infoError" class="text-xs text-error-500 dark:text-error-400 mt-1">{{ infoError }}</p>

          <!-- Sheet selection -->
          <div v-if="sheetInfo" class="mt-4">
            <p class="text-sm text-gray-700 dark:text-gray-300 mb-2">
              <strong>{{ sheetInfo.title }}</strong> — {{ sheetInfo.sheets.length }} feuille(s)
            </p>
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Feuille à importer
            </label>
            <select
              v-model="selectedSheet"
              class="w-full text-sm border border-gray-300 dark:border-gray-600 rounded-md px-3 py-2 bg-white dark:bg-gray-800 dark:text-gray-200"
              @change="loadPreview"
            >
              <option value="">Sélectionner...</option>
              <option v-for="s in sheetInfo.sheets" :key="s" :value="s">{{ s }}</option>
            </select>
          </div>

          <!-- Preview + go to mapping -->
          <div v-if="preview" class="mt-4">
            <SheetPreview :headers="preview.headers" :rows="preview.rows" :total-rows="preview.total_rows" />
            <button
              class="mt-4 px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600"
              @click="currentStep = 1"
            >
              Configurer le mapping
            </button>
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
          <div v-if="importResult" class="mb-4 p-4 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-800 rounded-md">
            <p class="text-sm font-medium text-gray-800 dark:text-gray-200 mb-2">
              {{ importResult.imported }} importé{{ importResult.imported > 1 ? 's' : '' }},
              {{ importResult.skipped }} ignoré{{ importResult.skipped > 1 ? 's' : '' }},
              {{ importResult.errors }} erreur{{ importResult.errors > 1 ? 's' : '' }}
            </p>
            <ul class="space-y-1 max-h-64 overflow-y-auto">
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
      </template>

      <!-- Footer -->
      <div class="flex justify-end gap-3 pt-4 border-t border-gray-100 dark:border-gray-800 mt-4">
        <button
          type="button"
          class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-white/5 rounded-md hover:bg-gray-200 dark:hover:bg-gray-700"
          @click="emit('close')"
        >
          {{ currentStep === 2 ? 'Fermer' : 'Annuler' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { googleApi } from '@/api/google'
import { useToast } from '@/composables/useToast'
import SheetPreview from './SheetPreview.vue'
import ColumnMappingTable from './ColumnMappingTable.vue'
import type { SheetInfo, SheetPreview as SheetPreviewType, ColumnMapping, SheetImportResponse } from '@/types/google'

const emit = defineEmits<{ close: []; imported: [] }>()
const toast = useToast()

const googleConnected = ref(false)
const currentStep = ref(0)

// Step 0
const spreadsheetUrl = ref('')
const loadingInfo = ref(false)
const infoError = ref('')
const sheetInfo = ref<SheetInfo | null>(null)
const selectedSheet = ref('')
const preview = ref<SheetPreviewType | null>(null)

// Step 1
const columnMapping = ref<ColumnMapping>({ name: '', url: '' })
const autoDiscover = ref(true)
const importing = ref(false)

// Step 2
const importResult = ref<SheetImportResponse | null>(null)

onMounted(async () => {
  try {
    const status = await googleApi.getStatus()
    googleConnected.value = status.connected
  } catch {
    googleConnected.value = false
  }
})

async function loadSpreadsheetInfo() {
  loadingInfo.value = true
  infoError.value = ''
  sheetInfo.value = null
  selectedSheet.value = ''
  preview.value = null

  try {
    sheetInfo.value = await googleApi.getSheetInfo(spreadsheetUrl.value)
    // Auto-select first sheet
    if (sheetInfo.value.sheets.length === 1) {
      selectedSheet.value = sheetInfo.value.sheets[0] ?? ''
      await loadPreview()
    }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'Impossible de charger la feuille'
    infoError.value = msg
  } finally {
    loadingInfo.value = false
  }
}

async function loadPreview() {
  if (!sheetInfo.value || !selectedSheet.value) return
  preview.value = null

  try {
    preview.value = await googleApi.getSheetPreview(sheetInfo.value.spreadsheet_id, selectedSheet.value)
    // Auto-detect column mapping
    autoDetectMapping()
  } catch (err: unknown) {
    toast.error('Impossible de charger la prévisualisation')
  }
}

function autoDetectMapping() {
  if (!preview.value) return

  const normalize = (s: string) => s.toLowerCase().replace(/[\s_-]/g, '')
  const headers = preview.value.headers

  const fieldMap: Record<keyof ColumnMapping, string[]> = {
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
    emit('imported')
  } catch (err: unknown) {
    toast.error(err instanceof Error ? err.message : "Erreur lors de l'import")
  } finally {
    importing.value = false
  }
}
</script>
