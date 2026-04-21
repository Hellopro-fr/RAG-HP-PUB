<template>
  <div>
    <PageBreadcrumb page-title="Configuration MCP" />

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
            @click="router.push('/tokens/new')"
          >
            Créer un jeton
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
          <span class="text-gray-600 dark:text-gray-400">Serveur</span>
          <select v-model="filters.serverId" class="px-3 py-2 text-sm border border-gray-300 rounded-md bg-white dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200">
            <option value="">Tous</option>
            <option v-for="s in serversStore.servers" :key="s.id" :value="s.id">{{ s.name }}</option>
          </select>
        </label>
        <label class="flex flex-col gap-1 text-sm">
          <span class="text-gray-600 dark:text-gray-400">HTTP</span>
          <select v-model="filters.allowHttp" class="px-3 py-2 text-sm border border-gray-300 rounded-md bg-white dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200">
            <option value="">Tous</option>
            <option value="yes">Autorisé</option>
            <option value="no">Interdit</option>
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

      <!-- Token cards -->
      <div
        v-if="filteredTokens.length"
        class="grid grid-cols-1 gap-4"
      >
        <TokenCard
          v-for="t in filteredTokens"
          :key="t.id"
          :token="t"
          :executors="executors"
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
        <i class="pi pi-key text-4xl mb-3 block" />
        <p class="font-medium">{{ activeFilterCount > 0 ? 'Aucun jeton ne correspond aux filtres' : 'Aucun jeton d\'accès' }}</p>
        <p v-if="activeFilterCount === 0" class="text-sm mt-1">
          Créez un jeton pour permettre aux clients MCP de se connecter à vos serveurs.
        </p>
      </div>
    </template>

    <!-- Revoke confirm -->
    <ConfirmDialog
      :open="!!revokingTokenId"
      title="Révoquer le jeton"
      message="Êtes-vous sûr de vouloir révoquer ce jeton ? Il ne pourra plus être utilisé pour se connecter."
      confirm-label="Révoquer"
      @update:open="revokingTokenId = undefined"
      @confirm="confirmRevoke"
    />

    <!-- Delete confirm -->
    <ConfirmDialog
      :open="!!deletingTokenId"
      title="Supprimer le jeton"
      message="Êtes-vous sûr de vouloir supprimer ce jeton ? Cette action est irréversible."
      confirm-label="Supprimer"
      @update:open="deletingTokenId = undefined"
      @confirm="confirmDelete"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { tokensApi } from '@/api/tokens'
import { installGuidesPublicApi } from '@/api/install-guides'
import { useServersStore } from '@/stores/servers'
import { useToast } from '@/composables/useToast'
import PageBreadcrumb from '@/components/common/PageBreadcrumb.vue'
import TokenCard from '@/components/tokens/TokenCard.vue'
import ConfirmDialog from '@/components/shared/ConfirmDialog.vue'
import FilterPanel from '@/components/shared/FilterPanel.vue'
import type { ScopeToken } from '@/types/token'
import type { InstallExecutor } from '@/types/install-guide'

const router = useRouter()
const serversStore = useServersStore()
const toast = useToast()

const tokens = ref<ScopeToken[]>([])
const executors = ref<InstallExecutor[]>([])
const loading = ref(false)
const revokingTokenId = ref<string>()
const deletingTokenId = ref<string>()

const filters = reactive({
  search: '',
  status: '' as '' | 'active' | 'revoked',
  serverId: '',
  allowHttp: '' as '' | 'yes' | 'no',
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

const filteredTokens = computed(() => {
  const q = filters.search.trim().toLowerCase()
  return tokens.value.filter(t => {
    if (q && !t.name.toLowerCase().includes(q)) return false
    if (filters.status === 'active' && !t.is_active) return false
    if (filters.status === 'revoked' && t.is_active) return false
    if (filters.serverId && !t.server_ids.includes(filters.serverId)) return false
    if (filters.allowHttp === 'yes' && !t.allow_http) return false
    if (filters.allowHttp === 'no' && t.allow_http) return false
    if (!matchesExpires(t.expires_at)) return false
    if (!inCreatedRange(t.created_at)) return false
    return true
  })
})

const activeFilterCount = computed(() => {
  let n = 0
  if (filters.search.trim()) n++
  if (filters.status) n++
  if (filters.serverId) n++
  if (filters.allowHttp) n++
  if (filters.expiresBucket) n++
  if (filters.createdFrom) n++
  if (filters.createdTo) n++
  return n
})

function resetFilters() {
  filters.search = ''
  filters.status = ''
  filters.serverId = ''
  filters.allowHttp = ''
  filters.expiresBucket = ''
  filters.createdFrom = ''
  filters.createdTo = ''
}

onMounted(() => {
  loadTokens()
  if (!serversStore.servers.length) {
    serversStore.fetchServers()
  }
  installGuidesPublicApi.listExecutors()
    .then(list => { executors.value = list || [] })
    .catch(() => { executors.value = [] })
})

async function loadTokens() {
  loading.value = true
  try {
    const response = await tokensApi.list()
    tokens.value = response.tokens
  } catch (err) {
    toast.error('Impossible de charger les jetons')
  } finally {
    loading.value = false
  }
}

function handleEdit(token: ScopeToken) {
  router.push('/tokens/' + token.id + '/edit')
}

function handleRevoke(id: string) {
  revokingTokenId.value = id
}

function handleDelete(id: string) {
  deletingTokenId.value = id
}

async function confirmRevoke() {
  if (revokingTokenId.value) {
    try {
      await tokensApi.revoke(revokingTokenId.value)
      toast.success('Jeton révoqué')
      await loadTokens()
    } catch {
      toast.error('Impossible de révoquer le jeton')
    } finally {
      revokingTokenId.value = undefined
    }
  }
}

async function confirmDelete() {
  if (deletingTokenId.value) {
    try {
      await tokensApi.delete(deletingTokenId.value)
      toast.success('Jeton supprimé')
      tokens.value = tokens.value.filter(t => t.id !== deletingTokenId.value)
    } catch {
      toast.error('Impossible de supprimer le jeton')
    } finally {
      deletingTokenId.value = undefined
    }
  }
}
</script>
