<template>
  <div>
    <PageBreadcrumb page-title="Configuration MCP" />

    <!-- Loading -->
    <div v-if="loading" class="text-center py-12">
      <i class="pi pi-spinner pi-spin text-2xl text-blue-500" />
    </div>

    <PageHeaderTabs
      v-else
      v-model="activeTab"
      :tabs="tabs"
    >
      <template #actions>
        <button
          class="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700"
          @click="router.push('/tokens/new')"
        >
          Créer un jeton
        </button>
      </template>

      <!-- Token cards -->
      <div
        v-if="filteredTokens.length"
        class="grid grid-cols-1 gap-4"
      >
        <TokenCard
          v-for="t in filteredTokens"
          :key="t.id"
          :token="t"
          @edit="handleEdit"
          @revoke="handleRevoke"
          @delete="handleDelete"
        />
      </div>

      <!-- Empty state -->
      <div
        v-else
        class="text-center py-12 text-gray-500"
      >
        <i class="pi pi-key text-4xl mb-3 block" />
        <p class="font-medium">Aucun jeton d'accès</p>
        <p class="text-sm mt-1">
          Créez un jeton pour permettre aux clients MCP de se connecter à vos serveurs.
        </p>
      </div>
    </PageHeaderTabs>

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
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { tokensApi } from '@/api/tokens'
import { useServersStore } from '@/stores/servers'
import { useToast } from '@/composables/useToast'
import PageBreadcrumb from '@/components/common/PageBreadcrumb.vue'
import PageHeaderTabs from '@/components/common/PageHeaderTabs.vue'
import TokenCard from '@/components/tokens/TokenCard.vue'
import ConfirmDialog from '@/components/shared/ConfirmDialog.vue'
import type { ScopeToken } from '@/types/token'

const router = useRouter()
const serversStore = useServersStore()
const toast = useToast()

const tokens = ref<ScopeToken[]>([])
const loading = ref(false)
const activeTab = ref('all')
const revokingTokenId = ref<string>()
const deletingTokenId = ref<string>()

const activeCount = computed(() => tokens.value.filter(t => t.is_active).length)
const revokedCount = computed(() => tokens.value.filter(t => !t.is_active).length)

const tabs = computed(() => [
  { label: 'Tous', value: 'all', count: tokens.value.length },
  { label: 'Actif', value: 'active', count: activeCount.value },
  { label: 'Révoqué', value: 'revoked', count: revokedCount.value },
])

const filteredTokens = computed(() => {
  if (activeTab.value === 'active') {
    return tokens.value.filter(t => t.is_active)
  }
  if (activeTab.value === 'revoked') {
    return tokens.value.filter(t => !t.is_active)
  }
  return tokens.value
})

onMounted(() => {
  loadTokens()
  if (!serversStore.servers.length) {
    serversStore.fetchServers()
  }
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
