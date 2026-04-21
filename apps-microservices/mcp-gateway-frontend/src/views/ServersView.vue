<template>
  <div>
    <PageBreadcrumb page-title="Serveurs MCP" />

    <!-- Loading -->
    <div v-if="serversStore.isLoading" class="text-center py-12">
      <i class="pi pi-spinner pi-spin text-2xl text-brand-500" />
    </div>

    <template v-else>
      <!-- Action bar -->
      <div class="mb-4 flex flex-wrap items-center justify-end gap-3">
        <button
          v-if="authStore.isAdmin"
          class="px-4 py-2 text-sm font-medium text-brand-500 border border-brand-300 rounded-md hover:bg-brand-50 dark:hover:bg-brand-500/10"
          @click="showImportModal = true"
        >
          Importer .mcp.json
        </button>
        <router-link
          v-if="authStore.isAdmin"
          to="/servers/import-google"
          class="px-4 py-2 text-sm font-medium text-green-600 border border-green-300 rounded-md hover:bg-green-50 dark:text-green-400 dark:border-green-600 dark:hover:bg-green-900/20"
        >
          <i class="pi pi-file-excel mr-1" />
          Google Sheets
        </router-link>
        <button
          v-if="authStore.isAdmin"
          class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600"
          @click="router.push('/servers/new')"
        >
          Ajouter un serveur
        </button>
        <button
          v-if="authStore.isAdmin"
          class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700"
          :disabled="discoveringAll"
          @click="handleDiscoverAll"
        >
          <i v-if="discoveringAll" class="pi pi-spinner pi-spin mr-1" />
          Découvrir tout
        </button>
      </div>

      <!-- Filters -->
      <FilterPanel
        :active-count="activeFilterCount"
        @reset="resetFilters"
      >
        <label class="flex flex-col gap-1 text-sm">
          <span class="text-gray-600 dark:text-gray-400">Nom</span>
          <input
            v-model="filters.search"
            type="text"
            placeholder="Rechercher..."
            class="px-3 py-2 text-sm border border-gray-300 rounded-md bg-white dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200 placeholder:text-gray-400"
          />
        </label>
        <label class="flex flex-col gap-1 text-sm">
          <span class="text-gray-600 dark:text-gray-400">Statut</span>
          <select v-model="filters.status" class="px-3 py-2 text-sm border border-gray-300 rounded-md bg-white dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200">
            <option value="">Tous</option>
            <option value="active">Actif</option>
            <option value="inactive">Inactif</option>
          </select>
        </label>
        <label class="flex flex-col gap-1 text-sm">
          <span class="text-gray-600 dark:text-gray-400">Sante</span>
          <select v-model="filters.health" class="px-3 py-2 text-sm border border-gray-300 rounded-md bg-white dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200">
            <option value="">Toutes</option>
            <option value="healthy">Healthy</option>
            <option value="unhealthy">Unhealthy</option>
            <option value="unknown">Unknown</option>
          </select>
        </label>
        <label class="flex flex-col gap-1 text-sm">
          <span class="text-gray-600 dark:text-gray-400">Transport</span>
          <select v-model="filters.transport" class="px-3 py-2 text-sm border border-gray-300 rounded-md bg-white dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200">
            <option value="">Tous</option>
            <option v-for="t in transportOptions" :key="t" :value="t">{{ t }}</option>
          </select>
        </label>
        <label class="flex flex-col gap-1 text-sm">
          <span class="text-gray-600 dark:text-gray-400">Tag</span>
          <select v-model="filters.tag" class="px-3 py-2 text-sm border border-gray-300 rounded-md bg-white dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200">
            <option value="">Tous</option>
            <option v-for="tag in serversStore.tags" :key="tag" :value="tag">{{ tag }}</option>
          </select>
        </label>
        <label class="flex flex-col gap-1 text-sm">
          <span class="text-gray-600 dark:text-gray-400">En-tetes auth</span>
          <select v-model="filters.auth" class="px-3 py-2 text-sm border border-gray-300 rounded-md bg-white dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200">
            <option value="">Tous</option>
            <option value="with">Avec</option>
            <option value="without">Sans</option>
          </select>
        </label>
        <label class="flex flex-col gap-1 text-sm">
          <span class="text-gray-600 dark:text-gray-400">Nombre d'outils</span>
          <select v-model="filters.toolsBucket" class="px-3 py-2 text-sm border border-gray-300 rounded-md bg-white dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200">
            <option value="">Tous</option>
            <option value="0">Aucun</option>
            <option value="1-5">1 a 5</option>
            <option value="6+">6 et plus</option>
          </select>
        </label>
        <label class="flex flex-col gap-1 text-sm">
          <span class="text-gray-600 dark:text-gray-400">Cree apres</span>
          <input v-model="filters.createdFrom" type="date" class="px-3 py-2 text-sm border border-gray-300 rounded-md bg-white dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200" />
        </label>
        <label class="flex flex-col gap-1 text-sm">
          <span class="text-gray-600 dark:text-gray-400">Cree avant</span>
          <input v-model="filters.createdTo" type="date" class="px-3 py-2 text-sm border border-gray-300 rounded-md bg-white dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200" />
        </label>
      </FilterPanel>

      <!-- Grid -->
      <div
        v-if="filteredServers.length"
        class="grid grid-cols-1 gap-4"
      >
        <ServerCard
          v-for="server in filteredServers"
          :key="server.id"
          :server="server"
          :is-admin="authStore.isAdmin"
          @toggle="handleToggle"
          @toggle-tool="handleToggleTool"
          @edit="handleEdit"
          @delete="handleDelete"
          @details="handleDetails"
          @discover="handleDiscover"
          @documentation="handleDocumentation"
        />
      </div>

      <!-- Empty state -->
      <div
        v-else
        class="text-center py-12 text-gray-500 dark:text-gray-400"
      >
        <i class="pi pi-server text-4xl mb-3 block" />
        <p>{{ activeFilterCount > 0 ? 'Aucun serveur ne correspond aux filtres' : 'Aucun serveur configuré' }}</p>
      </div>
    </template>

    <!-- Modals -->
    <ServerDetailsModal
      v-if="detailsServerId"
      :server-id="detailsServerId"
      @close="detailsServerId = undefined"
    />

    <ImportModal
      v-if="showImportModal"
      @close="showImportModal = false"
      @imported="loadServers"
    />


    <ConfirmDialog
      :open="!!deletingServerId"
      title="Supprimer le serveur"
      message="Êtes-vous sûr de vouloir supprimer ce serveur ? Cette action est irréversible."
      confirm-label="Supprimer"
      @update:open="deletingServerId = undefined"
      @confirm="confirmDelete"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useServersStore } from '@/stores/servers'
import { useAuthStore } from '@/stores/auth'
import { serversApi } from '@/api/servers'
import { useToast } from '@/composables/useToast'
import PageBreadcrumb from '@/components/common/PageBreadcrumb.vue'
import ServerCard from '@/components/servers/ServerCard.vue'
import ServerDetailsModal from '@/components/servers/ServerDetailsModal.vue'
import ImportModal from '@/components/servers/ImportModal.vue'
import ConfirmDialog from '@/components/shared/ConfirmDialog.vue'
import FilterPanel from '@/components/shared/FilterPanel.vue'
import type { Server } from '@/types/server'

const router = useRouter()
const serversStore = useServersStore()
const authStore = useAuthStore()
const toast = useToast()

const showImportModal = ref(false)
const detailsServerId = ref<string>()
const deletingServerId = ref<string>()
const discoveringAll = ref(false)

const filters = reactive({
  search: '',
  status: '' as '' | 'active' | 'inactive',
  health: '',
  transport: '',
  tag: '',
  auth: '' as '' | 'with' | 'without',
  toolsBucket: '' as '' | '0' | '1-5' | '6+',
  createdFrom: '',
  createdTo: '',
})

const transportOptions = computed(() => {
  const set = new Set<string>()
  for (const s of serversStore.servers) {
    if (s.transport_type) set.add(s.transport_type)
  }
  return Array.from(set).sort()
})

function matchesToolsBucket(count: number, bucket: string): boolean {
  if (bucket === '0') return count === 0
  if (bucket === '1-5') return count >= 1 && count <= 5
  if (bucket === '6+') return count >= 6
  return true
}

function matchesCreatedRange(iso: string): boolean {
  if (!filters.createdFrom && !filters.createdTo) return true
  const d = iso.slice(0, 10)
  if (filters.createdFrom && d < filters.createdFrom) return false
  if (filters.createdTo && d > filters.createdTo) return false
  return true
}

const filteredServers = computed(() => {
  const q = filters.search.trim().toLowerCase()
  return serversStore.servers.filter(s => {
    if (q && !s.name.toLowerCase().includes(q)) return false
    if (filters.status === 'active' && !s.is_active) return false
    if (filters.status === 'inactive' && s.is_active) return false
    if (filters.health && s.health_status !== filters.health) return false
    if (filters.transport && s.transport_type !== filters.transport) return false
    if (filters.tag && !s.tags.includes(filters.tag)) return false
    if (filters.auth === 'with' && !s.has_auth_headers) return false
    if (filters.auth === 'without' && s.has_auth_headers) return false
    if (filters.toolsBucket && !matchesToolsBucket(s.tools_count, filters.toolsBucket)) return false
    if (!matchesCreatedRange(s.created_at)) return false
    return true
  })
})

const activeFilterCount = computed(() => {
  let n = 0
  if (filters.search.trim()) n++
  if (filters.status) n++
  if (filters.health) n++
  if (filters.transport) n++
  if (filters.tag) n++
  if (filters.auth) n++
  if (filters.toolsBucket) n++
  if (filters.createdFrom) n++
  if (filters.createdTo) n++
  return n
})

function resetFilters() {
  filters.search = ''
  filters.status = ''
  filters.health = ''
  filters.transport = ''
  filters.tag = ''
  filters.auth = ''
  filters.toolsBucket = ''
  filters.createdFrom = ''
  filters.createdTo = ''
}

onMounted(() => {
  loadServers()
  serversStore.fetchTags()
})

function loadServers() {
  serversStore.fetchServers()
}

function handleToggle(id: string, enable: boolean) {
  serversStore.toggleServer(id, enable)
}

async function handleToggleTool(serverId: string, toolName: string, enable: boolean) {
  try {
    if (enable) {
      await serversApi.enableTool(serverId, toolName)
    } else {
      await serversApi.disableTool(serverId, toolName)
    }
    await serversStore.fetchServers()
  } catch (err) {
    console.error('Failed to toggle tool:', err)
  }
}

function handleEdit(server: Server) {
  router.push('/servers/' + server.id + '/edit')
}

function handleDocumentation(id: string) {
  router.push('/servers/' + id + '/documentation')
}

function handleDelete(id: string) {
  deletingServerId.value = id
}

async function confirmDelete() {
  if (deletingServerId.value) {
    await serversStore.deleteServer(deletingServerId.value)
    toast.success('Serveur supprimé')
    deletingServerId.value = undefined
  }
}

function handleDetails(id: string) {
  detailsServerId.value = id
}

async function handleDiscover(id: string) {
  await serversStore.discoverServer(id)
  toast.success('Découverte terminée')
}

async function handleDiscoverAll() {
  discoveringAll.value = true
  try {
    await serversStore.discoverAll()
    toast.success('Découverte de tous les serveurs terminée')
  } finally {
    discoveringAll.value = false
  }
}

</script>
