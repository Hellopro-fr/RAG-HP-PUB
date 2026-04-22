<template>
  <div>
    <PageBreadcrumb page-title="Clients OAuth2" />

    <!-- Loading -->
    <div v-if="loading" class="text-center py-12">
      <i class="pi pi-spinner pi-spin text-2xl text-brand-500" />
    </div>

    <template v-else>
      <!-- Filters + actions -->
      <FilterPanel
        :active-count="activeFilterCount"
        @reset="resetFilters"
      >
        <template #actions>
          <button
            class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600"
            @click="router.push('/oauth2/new')"
          >
            Créer un client
          </button>
        </template>
        <label class="flex flex-col gap-1 text-sm">
          <span class="text-gray-600 dark:text-gray-400">Nom</span>
          <input v-model="filters.search" type="text" placeholder="Rechercher..." class="px-3 py-2 text-sm border border-gray-300 rounded-md bg-white dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200 placeholder:text-gray-400" />
        </label>
        <label class="flex flex-col gap-1 text-sm">
          <span class="text-gray-600 dark:text-gray-400">Statut</span>
          <select v-model="filters.status" class="px-3 py-2 text-sm border border-gray-300 rounded-md bg-white dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200">
            <option value="">Tous</option>
            <option value="active">Actif</option>
            <option value="revoked">Révoqué</option>
          </select>
        </label>
        <label class="flex flex-col gap-1 text-sm">
          <span class="text-gray-600 dark:text-gray-400">Enregistrement</span>
          <select v-model="filters.dynamic" class="px-3 py-2 text-sm border border-gray-300 rounded-md bg-white dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200">
            <option value="">Tous</option>
            <option value="dynamic">Dynamique</option>
            <option value="manual">Manuel</option>
          </select>
        </label>
        <label class="flex flex-col gap-1 text-sm">
          <span class="text-gray-600 dark:text-gray-400">Serveur</span>
          <select v-model="filters.serverId" class="px-3 py-2 text-sm border border-gray-300 rounded-md bg-white dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200">
            <option value="">Tous</option>
            <option v-for="s in serversStore.servers" :key="s.id" :value="s.id">{{ s.name }}</option>
          </select>
        </label>
        <label class="flex flex-col gap-1 text-sm">
          <span class="text-gray-600 dark:text-gray-400">Expiration</span>
          <select v-model="filters.expiresBucket" class="px-3 py-2 text-sm border border-gray-300 rounded-md bg-white dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200">
            <option value="">Toutes</option>
            <option value="never">Jamais</option>
            <option value="expired">Expiré</option>
            <option value="soon">Expire sous 30j</option>
          </select>
        </label>
        <label class="flex flex-col gap-1 text-sm">
          <span class="text-gray-600 dark:text-gray-400">Créé après</span>
          <input v-model="filters.createdFrom" type="date" class="px-3 py-2 text-sm border border-gray-300 rounded-md bg-white dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200" />
        </label>
        <label class="flex flex-col gap-1 text-sm">
          <span class="text-gray-600 dark:text-gray-400">Créé avant</span>
          <input v-model="filters.createdTo" type="date" class="px-3 py-2 text-sm border border-gray-300 rounded-md bg-white dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200" />
        </label>
      </FilterPanel>

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
        <p class="font-medium">{{ activeFilterCount > 0 ? 'Aucun client ne correspond aux filtres' : 'Aucun client OAuth2' }}</p>
        <p v-if="activeFilterCount === 0" class="text-sm mt-1">
          Créez un client pour permettre l'authentification OAuth2 avec vos serveurs MCP.
        </p>
      </div>
    </template>

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
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { oauth2Api } from '@/api/oauth2'
import { useServersStore } from '@/stores/servers'
import { useToast } from '@/composables/useToast'
import PageBreadcrumb from '@/components/common/PageBreadcrumb.vue'
import ClientCard from '@/components/oauth2/ClientCard.vue'
import ConfirmDialog from '@/components/shared/ConfirmDialog.vue'
import FilterPanel from '@/components/shared/FilterPanel.vue'
import type { OAuth2Client } from '@/types/oauth2'

const router = useRouter()
const serversStore = useServersStore()
const toast = useToast()

const clients = ref<OAuth2Client[]>([])
const loading = ref(false)
const revokingClientId = ref<string>()
const deletingClientId = ref<string>()

const filters = reactive({
  search: '',
  status: '' as '' | 'active' | 'revoked',
  dynamic: '' as '' | 'dynamic' | 'manual',
  serverId: '',
  expiresBucket: '' as '' | 'never' | 'expired' | 'soon',
  createdFrom: '',
  createdTo: '',
})

function inCreatedRange(iso: string): boolean {
  if (!filters.createdFrom && !filters.createdTo) return true
  const d = iso.slice(0, 10)
  if (filters.createdFrom && d < filters.createdFrom) return false
  if (filters.createdTo && d > filters.createdTo) return false
  return true
}

function matchesExpires(expiresAt: string | undefined): boolean {
  if (!filters.expiresBucket) return true
  if (filters.expiresBucket === 'never') return !expiresAt
  if (!expiresAt) return false
  const now = Date.now()
  const exp = new Date(expiresAt).getTime()
  if (filters.expiresBucket === 'expired') return exp < now
  if (filters.expiresBucket === 'soon') return exp >= now && exp - now <= 30 * 24 * 60 * 60 * 1000
  return true
}

const filteredClients = computed(() => {
  const q = filters.search.trim().toLowerCase()
  return clients.value.filter(c => {
    if (q && !c.name.toLowerCase().includes(q)) return false
    if (filters.status === 'active' && !c.is_active) return false
    if (filters.status === 'revoked' && c.is_active) return false
    if (filters.dynamic === 'dynamic' && !c.dynamically_registered) return false
    if (filters.dynamic === 'manual' && c.dynamically_registered) return false
    if (filters.serverId && !c.server_ids.includes(filters.serverId)) return false
    if (!matchesExpires(c.expires_at)) return false
    if (!inCreatedRange(c.created_at)) return false
    return true
  })
})

const activeFilterCount = computed(() => {
  let n = 0
  if (filters.search.trim()) n++
  if (filters.status) n++
  if (filters.dynamic) n++
  if (filters.serverId) n++
  if (filters.expiresBucket) n++
  if (filters.createdFrom) n++
  if (filters.createdTo) n++
  return n
})

function resetFilters() {
  filters.search = ''
  filters.status = ''
  filters.dynamic = ''
  filters.serverId = ''
  filters.expiresBucket = ''
  filters.createdFrom = ''
  filters.createdTo = ''
}

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
