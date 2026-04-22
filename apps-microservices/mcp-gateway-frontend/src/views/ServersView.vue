<template>
  <div>
    <PageBreadcrumb page-title="Serveurs MCP" />

    <!-- Loading -->
    <div v-if="serversStore.isLoading" class="text-center py-12">
      <i class="pi pi-spinner pi-spin text-2xl text-brand-500" />
    </div>

    <PageHeaderTabs
      v-else
      v-model="activeTab"
      :tabs="tabs"
    >
      <template #actions>
        <select
          v-model="tagFilter"
          class="text-sm border border-gray-300 dark:border-gray-600 rounded-md px-3 py-2 bg-white dark:bg-gray-800 dark:text-gray-200"
          @change="loadServers"
        >
          <option value="">Tous les tags</option>
          <option v-for="tag in serversStore.tags" :key="tag" :value="tag">
            {{ tag }}
          </option>
        </select>
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
      </template>

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
        <p>Aucun serveur configuré</p>
      </div>
    </PageHeaderTabs>

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
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useServersStore } from '@/stores/servers'
import { useAuthStore } from '@/stores/auth'
import { serversApi } from '@/api/servers'
import { useToast } from '@/composables/useToast'
import PageBreadcrumb from '@/components/common/PageBreadcrumb.vue'
import PageHeaderTabs from '@/components/common/PageHeaderTabs.vue'
import ServerCard from '@/components/servers/ServerCard.vue'
import ServerDetailsModal from '@/components/servers/ServerDetailsModal.vue'
import ImportModal from '@/components/servers/ImportModal.vue'
import ConfirmDialog from '@/components/shared/ConfirmDialog.vue'
import type { Server } from '@/types/server'

const router = useRouter()
const serversStore = useServersStore()
const authStore = useAuthStore()
const toast = useToast()

const activeTab = ref('all')
const tagFilter = ref('')
const showImportModal = ref(false)
const detailsServerId = ref<string>()
const deletingServerId = ref<string>()
const discoveringAll = ref(false)

const filteredServers = computed(() => {
  if (activeTab.value === 'active') {
    return serversStore.servers.filter(s => s.is_active)
  }
  if (activeTab.value === 'inactive') {
    return serversStore.servers.filter(s => !s.is_active)
  }
  return serversStore.servers
})

const activeCount = computed(() => serversStore.servers.filter(s => s.is_active).length)
const inactiveCount = computed(() => serversStore.servers.filter(s => !s.is_active).length)

const tabs = computed(() => [
  { label: 'Tous', value: 'all', count: serversStore.servers.length },
  { label: 'Actif', value: 'active', count: activeCount.value },
  { label: 'Inactif', value: 'inactive', count: inactiveCount.value },
])

onMounted(() => {
  loadServers()
  serversStore.fetchTags()
})

function loadServers() {
  const filters: Record<string, string> = {}
  if (tagFilter.value) filters.tag = tagFilter.value
  serversStore.fetchServers(filters)
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
