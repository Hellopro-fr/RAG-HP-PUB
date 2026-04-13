<template>
  <div>
    <PageBreadcrumb page-title="Clients OAuth2" />

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
          class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600"
          @click="router.push('/oauth2/new')"
        >
          Créer un client
        </button>
      </template>

      <!-- Client cards -->
      <div
        v-if="filteredClients.length"
        class="grid grid-cols-1 gap-4"
      >
        <ClientCard
          v-for="c in filteredClients"
          :key="c.id"
          :client="c"
          @edit="handleEdit"
          @revoke="handleRevoke"
          @delete="handleDelete"
        />
      </div>

      <!-- Empty state -->
      <div
        v-else
        class="text-center py-12 text-gray-500 dark:text-gray-400"
      >
        <i class="pi pi-shield text-4xl mb-3 block" />
        <p class="font-medium">Aucun client OAuth2</p>
        <p class="text-sm mt-1">
          Créez un client pour permettre l'authentification OAuth2 avec vos serveurs MCP.
        </p>
      </div>
    </PageHeaderTabs>

    <!-- Revoke confirm -->
    <ConfirmDialog
      :open="!!revokingClientId"
      title="Révoquer le client"
      message="Êtes-vous sûr de vouloir révoquer ce client ? Les tokens existants seront invalidés."
      confirm-label="Révoquer"
      @update:open="revokingClientId = undefined"
      @confirm="confirmRevoke"
    />

    <!-- Delete confirm -->
    <ConfirmDialog
      :open="!!deletingClientId"
      title="Supprimer le client"
      message="Êtes-vous sûr de vouloir supprimer ce client ? Cette action est irréversible."
      confirm-label="Supprimer"
      @update:open="deletingClientId = undefined"
      @confirm="confirmDelete"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { oauth2Api } from '@/api/oauth2'
import { useServersStore } from '@/stores/servers'
import { useToast } from '@/composables/useToast'
import PageBreadcrumb from '@/components/common/PageBreadcrumb.vue'
import PageHeaderTabs from '@/components/common/PageHeaderTabs.vue'
import ClientCard from '@/components/oauth2/ClientCard.vue'
import ConfirmDialog from '@/components/shared/ConfirmDialog.vue'
import type { OAuth2Client } from '@/types/oauth2'

const router = useRouter()
const serversStore = useServersStore()
const toast = useToast()

const clients = ref<OAuth2Client[]>([])
const loading = ref(false)
const activeTab = ref('all')
const revokingClientId = ref<string>()
const deletingClientId = ref<string>()

const activeCount = computed(() => clients.value.filter(c => c.is_active).length)
const revokedCount = computed(() => clients.value.filter(c => !c.is_active).length)
const dynamicCount = computed(() => clients.value.filter(c => c.dynamically_registered).length)

const tabs = computed(() => [
  { label: 'Tous', value: 'all', count: clients.value.length },
  { label: 'Actif', value: 'active', count: activeCount.value },
  { label: 'Révoqué', value: 'revoked', count: revokedCount.value },
  { label: 'Dynamic', value: 'dynamic', count: dynamicCount.value },
])

const filteredClients = computed(() => {
  if (activeTab.value === 'active') {
    return clients.value.filter(c => c.is_active)
  }
  if (activeTab.value === 'revoked') {
    return clients.value.filter(c => !c.is_active)
  }
  if (activeTab.value === 'dynamic') {
    return clients.value.filter(c => c.dynamically_registered)
  }
  return clients.value
})

onMounted(() => {
  loadClients()
  if (!serversStore.servers.length) {
    serversStore.fetchServers()
  }
})

async function loadClients() {
  loading.value = true
  try {
    const response = await oauth2Api.list()
    clients.value = response.clients
  } catch (err) {
    toast.error('Impossible de charger les clients OAuth2')
  } finally {
    loading.value = false
  }
}

function handleEdit(client: OAuth2Client) {
  router.push('/oauth2/' + client.id + '/edit')
}

function handleRevoke(id: string) {
  revokingClientId.value = id
}

function handleDelete(id: string) {
  deletingClientId.value = id
}

async function confirmRevoke() {
  if (revokingClientId.value) {
    try {
      await oauth2Api.revoke(revokingClientId.value)
      toast.success('Client révoqué')
      await loadClients()
    } catch {
      toast.error('Impossible de révoquer le client')
    } finally {
      revokingClientId.value = undefined
    }
  }
}

async function confirmDelete() {
  if (deletingClientId.value) {
    try {
      await oauth2Api.delete(deletingClientId.value)
      toast.success('Client supprimé')
      clients.value = clients.value.filter(c => c.id !== deletingClientId.value)
    } catch {
      toast.error('Impossible de supprimer le client')
    } finally {
      deletingClientId.value = undefined
    }
  }
}
</script>
