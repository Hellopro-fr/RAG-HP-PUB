<template>
  <div>
    <PageBreadcrumb page-title="Guides d'installation" />

    <!-- Loading -->
    <div v-if="loading" class="text-center py-12">
      <i class="pi pi-spinner pi-spin text-2xl text-brand-500" />
    </div>

    <PageHeaderTabs
      v-else
      v-model="activeTab"
      :tabs="tabs"
    >
      <template #actions>
        <button
          v-if="activeTab === 'configs'"
          class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600"
          @click="$router.push('/install-guides-admin/configs/new')"
        >
          Ajouter une configuration
        </button>
        <button
          v-if="activeTab === 'executors'"
          class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600"
          @click="$router.push('/install-guides-admin/executors/new')"
        >
          Ajouter un executeur
        </button>
        <button
          class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700"
          @click="handleBatchImport"
        >
          Importer JSON
        </button>
        <button
          class="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700"
          @click="handleExportAll"
        >
          <i class="pi pi-download text-xs" />
          Exporter tout
        </button>
      </template>

      <!-- Success message -->
      <div
        v-if="successMsg"
        class="mb-4 rounded-lg p-3 text-sm bg-success-50 dark:bg-success-500/10 border border-success-200 dark:border-success-500/30 text-success-800 dark:text-success-300"
      >
        {{ successMsg }}
      </div>

      <!-- Filters -->
      <FilterPanel
        :active-count="activeFilterCount"
        @reset="resetFilters"
      >
        <label class="flex flex-col gap-1 text-sm">
          <span class="text-gray-600 dark:text-gray-400">Libelle</span>
          <input
            v-model="filters.search"
            type="text"
            placeholder="Rechercher..."
            class="px-3 py-2 text-sm border border-gray-300 rounded-md bg-white dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200 placeholder:text-gray-400"
          />
        </label>
        <label class="flex flex-col gap-1 text-sm">
          <span class="text-gray-600 dark:text-gray-400">Statut</span>
          <select
            v-model="filters.status"
            class="px-3 py-2 text-sm border border-gray-300 rounded-md bg-white dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200"
          >
            <option value="">Tous</option>
            <option value="active">Actif</option>
            <option value="inactive">Inactif</option>
          </select>
        </label>
      </FilterPanel>

      <!-- Configs tab -->
      <div v-if="activeTab === 'configs'">
        <div v-if="!filteredConfigs.length" class="text-center py-12 text-gray-500">
          <i class="pi pi-cog text-4xl mb-3 block" />
          <p>{{ activeFilterCount > 0 ? 'Aucune configuration ne correspond aux filtres' : 'Aucune configuration MCP' }}</p>
        </div>
        <div v-else-if="activeFilterCount > 0" class="space-y-3">
          <div
            v-for="cfg in filteredConfigs"
            :key="cfg.id"
            class="flex items-center justify-between rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800/50 px-4 py-3"
          >
            <div class="flex items-center gap-3">
              <div
                class="w-8 h-8 rounded-lg flex items-center justify-center"
                :class="cfg.color"
              >
                <i class="pi text-sm" :class="cfg.icon" />
              </div>
              <div>
                <p class="text-sm font-semibold text-gray-900 dark:text-white">{{ cfg.label }}</p>
                <p class="text-xs text-gray-500 dark:text-gray-400">{{ cfg.slug }}</p>
              </div>
            </div>
            <div class="flex items-center gap-2">
              <button
                class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium cursor-pointer transition-colors"
                :class="cfg.is_active
                  ? 'bg-success-100 text-success-700 dark:bg-success-500/20 dark:text-success-400 hover:bg-success-200 dark:hover:bg-success-500/30'
                  : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'"
                @click="toggleActive('config', cfg)"
              >
                {{ cfg.is_active ? 'Actif' : 'Inactif' }}
              </button>
              <button
                class="p-1.5 text-gray-500 hover:text-brand-500"
                @click="$router.push(`/install-guides-admin/configs/${cfg.id}/edit`)"
              >
                <i class="pi pi-pencil text-sm" />
              </button>
              <button
                class="p-1.5 text-gray-500 hover:text-error-500"
                @click="deleteItem('config', cfg.id, cfg.label)"
              >
                <i class="pi pi-trash text-sm" />
              </button>
            </div>
          </div>
        </div>
        <VueDraggable
          v-else
          v-model="configs"
          handle=".drag-handle"
          ghost-class="opacity-30"
          :animation="200"
          class="space-y-3"
          @end="onConfigDragEnd"
        >
          <div
            v-for="cfg in configs"
            :key="cfg.id"
            class="flex items-center justify-between rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800/50 px-4 py-3"
          >
            <div class="flex items-center gap-3">
              <i class="pi pi-bars text-xs text-gray-400 cursor-grab drag-handle" />
              <div
                class="w-8 h-8 rounded-lg flex items-center justify-center"
                :class="cfg.color"
              >
                <i class="pi text-sm" :class="cfg.icon" />
              </div>
              <div>
                <p class="text-sm font-semibold text-gray-900 dark:text-white">{{ cfg.label }}</p>
                <p class="text-xs text-gray-500 dark:text-gray-400">{{ cfg.slug }}</p>
              </div>
            </div>
            <div class="flex items-center gap-2">
              <button
                class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium cursor-pointer transition-colors"
                :class="cfg.is_active
                  ? 'bg-success-100 text-success-700 dark:bg-success-500/20 dark:text-success-400 hover:bg-success-200 dark:hover:bg-success-500/30'
                  : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'"
                @click="toggleActive('config', cfg)"
              >
                {{ cfg.is_active ? 'Actif' : 'Inactif' }}
              </button>
              <button
                class="p-1.5 text-gray-500 hover:text-brand-500"
                @click="$router.push(`/install-guides-admin/configs/${cfg.id}/edit`)"
              >
                <i class="pi pi-pencil text-sm" />
              </button>
              <button
                class="p-1.5 text-gray-500 hover:text-error-500"
                @click="deleteItem('config', cfg.id, cfg.label)"
              >
                <i class="pi pi-trash text-sm" />
              </button>
            </div>
          </div>
        </VueDraggable>
      </div>

      <!-- Executors tab -->
      <div v-if="activeTab === 'executors'">
        <div v-if="!filteredExecutors.length" class="text-center py-12 text-gray-500">
          <i class="pi pi-box text-4xl mb-3 block" />
          <p>{{ activeFilterCount > 0 ? 'Aucun executeur ne correspond aux filtres' : 'Aucun executeur de paquets' }}</p>
        </div>
        <div v-else-if="activeFilterCount > 0" class="space-y-3">
          <div
            v-for="exec in filteredExecutors"
            :key="exec.id"
            class="flex items-center justify-between rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800/50 px-4 py-3"
          >
            <div class="flex items-center gap-3">
              <div
                class="w-8 h-8 rounded-lg flex items-center justify-center"
                :class="exec.color"
              >
                <i class="pi text-sm" :class="exec.icon" />
              </div>
              <div>
                <p class="text-sm font-semibold text-gray-900 dark:text-white">{{ exec.label }}</p>
                <p class="text-xs text-gray-500 dark:text-gray-400">{{ exec.slug }} — {{ exec.sub }}</p>
              </div>
            </div>
            <div class="flex items-center gap-2">
              <button
                class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium cursor-pointer transition-colors"
                :class="exec.is_active
                  ? 'bg-success-100 text-success-700 dark:bg-success-500/20 dark:text-success-400 hover:bg-success-200 dark:hover:bg-success-500/30'
                  : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'"
                @click="toggleActive('executor', exec)"
              >
                {{ exec.is_active ? 'Actif' : 'Inactif' }}
              </button>
              <button
                class="p-1.5 text-gray-500 hover:text-brand-500"
                @click="$router.push(`/install-guides-admin/executors/${exec.id}/edit`)"
              >
                <i class="pi pi-pencil text-sm" />
              </button>
              <button
                class="p-1.5 text-gray-500 hover:text-error-500"
                @click="deleteItem('executor', exec.id, exec.label)"
              >
                <i class="pi pi-trash text-sm" />
              </button>
            </div>
          </div>
        </div>
        <VueDraggable
          v-else
          v-model="executors"
          handle=".drag-handle"
          ghost-class="opacity-30"
          :animation="200"
          class="space-y-3"
          @end="onExecutorDragEnd"
        >
          <div
            v-for="exec in executors"
            :key="exec.id"
            class="flex items-center justify-between rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800/50 px-4 py-3"
          >
            <div class="flex items-center gap-3">
              <i class="pi pi-bars text-xs text-gray-400 cursor-grab drag-handle" />
              <div
                class="w-8 h-8 rounded-lg flex items-center justify-center"
                :class="exec.color"
              >
                <i class="pi text-sm" :class="exec.icon" />
              </div>
              <div>
                <p class="text-sm font-semibold text-gray-900 dark:text-white">{{ exec.label }}</p>
                <p class="text-xs text-gray-500 dark:text-gray-400">{{ exec.slug }} — {{ exec.sub }}</p>
              </div>
            </div>
            <div class="flex items-center gap-2">
              <button
                class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium cursor-pointer transition-colors"
                :class="exec.is_active
                  ? 'bg-success-100 text-success-700 dark:bg-success-500/20 dark:text-success-400 hover:bg-success-200 dark:hover:bg-success-500/30'
                  : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'"
                @click="toggleActive('executor', exec)"
              >
                {{ exec.is_active ? 'Actif' : 'Inactif' }}
              </button>
              <button
                class="p-1.5 text-gray-500 hover:text-brand-500"
                @click="$router.push(`/install-guides-admin/executors/${exec.id}/edit`)"
              >
                <i class="pi pi-pencil text-sm" />
              </button>
              <button
                class="p-1.5 text-gray-500 hover:text-error-500"
                @click="deleteItem('executor', exec.id, exec.label)"
              >
                <i class="pi pi-trash text-sm" />
              </button>
            </div>
          </div>
        </VueDraggable>
      </div>
    </PageHeaderTabs>

    <!-- Delete confirm -->
    <ConfirmDialog
      :open="deleteTarget !== undefined"
      title="Supprimer"
      :message="`Supprimer '${deleteTarget?.name}' ? Cette action est irreversible.`"
      confirm-label="Supprimer"
      @update:open="deleteTarget = undefined"
      @confirm="confirmDelete"
    />

    <!-- Hidden file input for import -->
    <input ref="fileInput" type="file" accept=".json" class="hidden" @change="onFileSelected" />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { installGuidesAdminApi } from '@/api/install-guides'
import { useToast } from '@/composables/useToast'
import PageBreadcrumb from '@/components/common/PageBreadcrumb.vue'
import PageHeaderTabs from '@/components/common/PageHeaderTabs.vue'
import ConfirmDialog from '@/components/shared/ConfirmDialog.vue'
import FilterPanel from '@/components/shared/FilterPanel.vue'
import { VueDraggable } from 'vue-draggable-plus'
import type { InstallExecutor, InstallConfig } from '@/types/install-guide'

const toast = useToast()

const loading = ref(false)
const activeTab = ref('configs')
const executors = ref<InstallExecutor[]>([])
const configs = ref<InstallConfig[]>([])
const successMsg = ref('')
const fileInput = ref<HTMLInputElement>()
const deleteTarget = ref<{ type: 'executor' | 'config'; id: number; name: string } | undefined>()

const filters = reactive({
  search: '',
  status: '' as '' | 'active' | 'inactive',
})

const tabs = computed(() => [
  { label: 'Configurations MCP', value: 'configs', count: configs.value.length },
  { label: 'Package executors', value: 'executors', count: executors.value.length },
])

function matchesFilters(item: InstallExecutor | InstallConfig, extraText?: string): boolean {
  const q = filters.search.trim().toLowerCase()
  if (q) {
    const haystack = [item.label, item.slug, extraText || ''].join(' ').toLowerCase()
    if (!haystack.includes(q)) return false
  }
  if (filters.status === 'active' && !item.is_active) return false
  if (filters.status === 'inactive' && item.is_active) return false
  return true
}

const filteredConfigs = computed(() =>
  configs.value.filter(c => matchesFilters(c))
)

const filteredExecutors = computed(() =>
  executors.value.filter(e => matchesFilters(e, e.sub))
)

const activeFilterCount = computed(() => {
  let n = 0
  if (filters.search.trim()) n++
  if (filters.status) n++
  return n
})

function resetFilters() {
  filters.search = ''
  filters.status = ''
}

onMounted(() => loadAll())

async function loadAll() {
  loading.value = true
  try {
    const [execRes, cfgRes] = await Promise.all([
      installGuidesAdminApi.listExecutors(),
      installGuidesAdminApi.listConfigs(),
    ])
    executors.value = execRes.executors || []
    configs.value = cfgRes.configs || []
  } catch {
    toast.error('Impossible de charger les guides')
  } finally {
    loading.value = false
  }
}

async function toggleActive(type: 'executor' | 'config', item: InstallExecutor | InstallConfig) {
  const newValue = !item.is_active
  try {
    if (type === 'executor') {
      await installGuidesAdminApi.updateExecutor(item.id, { is_active: newValue } as any)
    } else {
      await installGuidesAdminApi.updateConfig(item.id, { is_active: newValue } as any)
    }
    item.is_active = newValue
    toast.success(`${item.label} ${newValue ? 'active' : 'desactive'}`)
  } catch {
    toast.error('Erreur lors de la mise a jour')
  }
}

async function onExecutorDragEnd() {
  try {
    await Promise.all(
      executors.value.map((exec, i) =>
        installGuidesAdminApi.updateExecutor(exec.id, { display_order: i + 1 })
      )
    )
    executors.value.forEach((exec, i) => { exec.display_order = i + 1 })
  } catch {
    toast.error('Erreur lors du reordonnancement')
    await loadAll()
  }
}

async function onConfigDragEnd() {
  try {
    await Promise.all(
      configs.value.map((cfg, i) =>
        installGuidesAdminApi.updateConfig(cfg.id, { display_order: i + 1 })
      )
    )
    configs.value.forEach((cfg, i) => { cfg.display_order = i + 1 })
  } catch {
    toast.error('Erreur lors du reordonnancement')
    await loadAll()
  }
}

function deleteItem(type: 'executor' | 'config', id: number, name: string) {
  deleteTarget.value = { type, id, name }
}

async function confirmDelete() {
  if (!deleteTarget.value) return
  const { type, id } = deleteTarget.value
  try {
    if (type === 'executor') {
      await installGuidesAdminApi.deleteExecutor(id)
      executors.value = executors.value.filter(e => e.id !== id)
    } else {
      await installGuidesAdminApi.deleteConfig(id)
      configs.value = configs.value.filter(c => c.id !== id)
    }
    toast.success('Supprime')
  } catch {
    toast.error('Erreur lors de la suppression')
  } finally {
    deleteTarget.value = undefined
  }
}

function handleBatchImport() {
  fileInput.value?.click()
}

function handleExportAll() {
  // Strip server-managed fields so the export can be re-imported as-is via createExecutor/createConfig.
  const stripped = {
    executors: executors.value.map(({ id, created_at, updated_at, ...rest }: any) => rest),
    configs: configs.value.map(({ id, created_at, updated_at, ...rest }: any) => rest),
    exported_at: new Date().toISOString(),
  }
  const blob = new Blob([JSON.stringify(stripped, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `install-guides-${new Date().toISOString().slice(0, 10)}.json`
  a.click()
  URL.revokeObjectURL(url)
}

async function onFileSelected(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  try {
    const text = await file.text()
    const parsed = JSON.parse(text)
    let imported = 0

    // Global export format: { executors: [...], configs: [...] }
    if (parsed && !Array.isArray(parsed) && (Array.isArray(parsed.executors) || Array.isArray(parsed.configs))) {
      for (const item of parsed.executors || []) {
        await installGuidesAdminApi.createExecutor(item)
        imported++
      }
      for (const item of parsed.configs || []) {
        await installGuidesAdminApi.createConfig(item)
        imported++
      }
    } else if (Array.isArray(parsed)) {
      // Legacy flat array — import into the active tab
      if (activeTab.value === 'executors') {
        for (const item of parsed) {
          await installGuidesAdminApi.createExecutor(item)
          imported++
        }
      } else {
        for (const item of parsed) {
          await installGuidesAdminApi.createConfig(item)
          imported++
        }
      }
    } else {
      throw new Error('Format JSON non reconnu')
    }

    successMsg.value = `${imported} element(s) importe(s)`
    await loadAll()
    setTimeout(() => { successMsg.value = '' }, 5000)
  } catch (err: any) {
    toast.error(err?.body?.error || err?.message || 'Erreur lors de l\'import')
  }
  if (fileInput.value) fileInput.value.value = ''
}
</script>
