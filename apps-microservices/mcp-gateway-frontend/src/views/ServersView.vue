<template>
  <div>
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">Serveurs MCP</h1>
        <p class="text-sm text-gray-500 mt-1">Gérez vos serveurs MCP et leurs outils</p>
      </div>
      <div class="flex items-center gap-3">
        <select
          v-model="statusFilter"
          class="text-sm border border-gray-300 rounded-md px-3 py-2"
          @change="loadServers"
        >
          <option value="">Tous</option>
          <option value="true">Actif</option>
          <option value="false">Inactif</option>
        </select>
        <select
          v-model="tagFilter"
          class="text-sm border border-gray-300 rounded-md px-3 py-2"
          @change="loadServers"
        >
          <option value="">Tous les tags</option>
          <option v-for="tag in serversStore.tags" :key="tag" :value="tag">
            {{ tag }}
          </option>
        </select>
        <button
          class="px-4 py-2 text-sm font-medium text-blue-600 border border-blue-300 rounded-md hover:bg-blue-50"
          @click="showImportModal = true"
        >
          Importer .mcp.json
        </button>
        <button
          class="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700"
          @click="router.push('/servers/new')"
        >
          Ajouter un serveur
        </button>
        <button
          class="px-4 py-2 text-sm font-medium text-gray-700 border border-gray-300 rounded-md hover:bg-gray-50"
          :disabled="discoveringAll"
          @click="handleDiscoverAll"
        >
          <i v-if="discoveringAll" class="pi pi-spinner pi-spin mr-1" />
          Découvrir tout
        </button>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="serversStore.isLoading" class="text-center py-12">
      <i class="pi pi-spinner pi-spin text-2xl text-blue-500" />
    </div>

    <!-- Grid -->
    <div
      v-else
      class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"
    >
      <ServerCard
        v-for="server in serversStore.servers"
        :key="server.id"
        :server="server"
        @toggle="handleToggle"
        @edit="handleEdit"
        @delete="handleDelete"
        @details="handleDetails"
        @discover="handleDiscover"
      />
    </div>

    <!-- Empty state -->
    <div
      v-if="!serversStore.isLoading && serversStore.servers.length === 0"
      class="text-center py-12 text-gray-500"
    >
      <i class="pi pi-server text-4xl mb-3 block" />
      <p>Aucun serveur configuré</p>
    </div>

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
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useServersStore } from '@/stores/servers'
import { useToast } from '@/composables/useToast'
import ServerCard from '@/components/servers/ServerCard.vue'
import ServerDetailsModal from '@/components/servers/ServerDetailsModal.vue'
import ImportModal from '@/components/servers/ImportModal.vue'
import ConfirmDialog from '@/components/shared/ConfirmDialog.vue'
import type { Server } from '@/types/server'

const router = useRouter()
const serversStore = useServersStore()
const toast = useToast()

const statusFilter = ref('')
const tagFilter = ref('')
const showImportModal = ref(false)
const detailsServerId = ref<string>()
const deletingServerId = ref<string>()
const discoveringAll = ref(false)

onMounted(() => {
  loadServers()
  serversStore.fetchTags()
})

function loadServers() {
  const filters: Record<string, string> = {}
  if (statusFilter.value) filters.is_active = statusFilter.value
  if (tagFilter.value) filters.tag = tagFilter.value
  serversStore.fetchServers(filters)
}

function handleToggle(id: string, enable: boolean) {
  serversStore.toggleServer(id, enable)
}

function handleEdit(server: Server) {
  router.push('/servers/' + server.id + '/edit')
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
