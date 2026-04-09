<template>
  <div>
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">Configuration MCP</h1>
        <p class="text-sm text-gray-500 mt-1">
          Gérez vos jetons d'accès MCP et leurs permissions sur les serveurs
        </p>
      </div>
      <button
        class="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700"
        @click="router.push('/tokens/new')"
      >
        Créer un jeton d'accès
      </button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="text-center py-12">
      <i class="pi pi-spinner pi-spin text-2xl text-blue-500" />
    </div>

    <!-- Token cards -->
    <div
      v-else-if="tokens.length"
      class="grid grid-cols-1 gap-4"
    >
      <TokenCard
        v-for="t in tokens"
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
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { tokensApi } from '@/api/tokens'
import { useServersStore } from '@/stores/servers'
import { useToast } from '@/composables/useToast'
import TokenCard from '@/components/tokens/TokenCard.vue'
import ConfirmDialog from '@/components/shared/ConfirmDialog.vue'
import type { ScopeToken } from '@/types/token'

const router = useRouter()
const serversStore = useServersStore()
const toast = useToast()

const tokens = ref<ScopeToken[]>([])
const loading = ref(false)
const revokingTokenId = ref<string>()
const deletingTokenId = ref<string>()

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
