<template>
  <div>
    <PageBreadcrumb page-title="Serveur Autorisation" />

    <p class="mb-6 text-sm text-gray-600 dark:text-gray-400">
      Octroie un accès complet (sans filtre Leexi / Ringover / BDD) à un utilisateur
      sur un serveur MCP spécifique.
    </p>

    <!-- Server picker + add form -->
    <div
      class="mb-6 rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900"
    >
      <div class="grid gap-4 md:grid-cols-2">
        <label class="flex flex-col gap-1 text-sm">
          <span class="text-gray-600 dark:text-gray-400">Serveur</span>
          <select
            v-model="selectedServer"
            class="px-3 py-2 text-sm border border-gray-300 rounded-md bg-white dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200"
          >
            <option value="">— Tous les serveurs —</option>
            <option v-for="s in servers" :key="s.id" :value="s.id">
              {{ s.name }}
            </option>
          </select>
        </label>
      </div>

      <form
        v-if="selectedServer"
        class="mt-4 flex flex-col gap-3 md:flex-row md:items-end"
        @submit.prevent="addGrant"
      >
        <label class="flex flex-1 flex-col gap-1 text-sm">
          <span class="text-gray-600 dark:text-gray-400">Utilisateur à autoriser</span>
          <select
            v-model="selectedEmail"
            class="px-3 py-2 text-sm border border-gray-300 rounded-md bg-white dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200"
          >
            <option value="">— Sélectionnez un utilisateur —</option>
            <option v-for="u in users" :key="u.id" :value="u.email">
              {{ u.display_name ? `${u.display_name} (${u.email})` : u.email }}
            </option>
          </select>
        </label>
        <button
          type="submit"
          :disabled="!selectedEmail || creating"
          class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {{ creating ? 'Octroi…' : 'Octroyer' }}
        </button>
      </form>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="text-center py-12">
      <i class="pi pi-spinner pi-spin text-2xl text-brand-500" />
    </div>

    <!-- Grants table -->
    <template v-else>
      <h2 class="mb-3 text-base font-semibold text-gray-900 dark:text-white">
        Autorisations
        <span
          v-if="selectedServerName"
          class="ml-2 text-sm font-normal text-gray-500 dark:text-gray-400"
        >
          — {{ selectedServerName }}
        </span>
      </h2>

      <div
        v-if="grants.length === 0"
        class="rounded-lg border border-dashed border-gray-300 bg-white py-12 text-center text-gray-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-400"
      >
        <i class="pi pi-shield text-4xl mb-3 block" />
        <p class="font-medium">Aucune autorisation enregistrée.</p>
        <p v-if="!selectedServer" class="text-sm mt-1">
          Sélectionnez un serveur pour octroyer un nouvel accès.
        </p>
      </div>

      <div
        v-else
        class="overflow-hidden rounded-lg border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900"
      >
        <table class="w-full text-sm">
          <thead class="bg-gray-50 dark:bg-gray-800">
            <tr class="text-left text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400">
              <th class="px-4 py-3 font-medium">Email</th>
              <th v-if="!selectedServer" class="px-4 py-3 font-medium">Serveur</th>
              <th class="px-4 py-3 font-medium">Octroyé par</th>
              <th class="px-4 py-3 font-medium">Date</th>
              <th class="px-4 py-3 text-right font-medium">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-200 dark:divide-gray-700">
            <tr
              v-for="g in grants"
              :key="`${g.server_id}-${g.email}`"
              class="text-gray-700 dark:text-gray-200"
            >
              <td class="px-4 py-3">{{ g.email }}</td>
              <td v-if="!selectedServer" class="px-4 py-3">
                <span class="font-mono text-xs">
                  {{ serverNameById(g.server_id) || g.server_id }}
                </span>
              </td>
              <td class="px-4 py-3 text-gray-600 dark:text-gray-400">
                {{ g.created_by || '—' }}
              </td>
              <td class="px-4 py-3 text-gray-600 dark:text-gray-400">
                {{ formatDate(g.created_at) }}
              </td>
              <td class="px-4 py-3 text-right">
                <button
                  class="px-3 py-1 text-sm font-medium text-error-600 rounded-md hover:bg-error-50 dark:hover:bg-error-500/10"
                  @click="askRemoveGrant(g)"
                >
                  Révoquer
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <!-- Revoke confirm -->
    <ConfirmDialog
      :open="!!pendingRemoval"
      title="Révoquer l'autorisation"
      :message="confirmMessage"
      confirm-label="Révoquer"
      @update:open="pendingRemoval = undefined"
      @confirm="confirmRemove"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { serverAuthorizationsApi } from '@/api/server-authorizations'
import { serversApi } from '@/api/servers'
import { usersApi } from '@/api/users'
import { useToast } from '@/composables/useToast'
import PageBreadcrumb from '@/components/common/PageBreadcrumb.vue'
import ConfirmDialog from '@/components/shared/ConfirmDialog.vue'
import type { ServerAuthorization } from '@/types/server-authorization'
import type { User } from '@/types/user'

interface ServerOption {
  id: string
  name: string
}

const toast = useToast()

const servers = ref<ServerOption[]>([])
const users = ref<User[]>([])
const selectedServer = ref<string>('')
const grants = ref<ServerAuthorization[]>([])
const selectedEmail = ref('')
const loading = ref(false)
const creating = ref(false)
const pendingRemoval = ref<ServerAuthorization | undefined>(undefined)

const selectedServerName = computed(
  () => servers.value.find((s) => s.id === selectedServer.value)?.name ?? '',
)

const confirmMessage = computed(() => {
  const g = pendingRemoval.value
  if (!g) return ''
  const serverName = serverNameById(g.server_id) || g.server_id
  return `Révoquer l'accès complet de ${g.email} sur le serveur "${serverName}" ?`
})

function serverNameById(id: string): string | undefined {
  return servers.value.find((s) => s.id === id)?.name
}

function formatDate(iso: string): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('fr-FR')
  } catch {
    return iso
  }
}

async function loadServers(): Promise<void> {
  try {
    const response = await serversApi.list()
    servers.value = response.servers.map((s) => ({ id: s.id, name: s.name }))
  } catch {
    toast.error('Impossible de charger la liste des serveurs')
  }
}

async function loadUsers(): Promise<void> {
  try {
    const response = await usersApi.list()
    users.value = response.users
  } catch {
    toast.error("Impossible de charger la liste des utilisateurs")
  }
}

async function loadGrants(): Promise<void> {
  loading.value = true
  try {
    grants.value = await serverAuthorizationsApi.list(
      selectedServer.value || undefined,
    )
  } catch {
    toast.error('Impossible de charger les autorisations')
    grants.value = []
  } finally {
    loading.value = false
  }
}

async function addGrant(): Promise<void> {
  const email = selectedEmail.value
  if (!selectedServer.value || !email) return
  creating.value = true
  try {
    await serverAuthorizationsApi.create({
      server_id: selectedServer.value,
      email,
    })
    selectedEmail.value = ''
    toast.success('Autorisation octroyée')
    await loadGrants()
  } catch {
    toast.error("Impossible d'octroyer l'autorisation")
  } finally {
    creating.value = false
  }
}

function askRemoveGrant(g: ServerAuthorization): void {
  pendingRemoval.value = g
}

async function confirmRemove(): Promise<void> {
  const g = pendingRemoval.value
  if (!g) return
  try {
    await serverAuthorizationsApi.delete(g.server_id, g.email)
    toast.success('Autorisation révoquée')
    grants.value = grants.value.filter(
      (x) => !(x.server_id === g.server_id && x.email === g.email),
    )
  } catch {
    toast.error("Impossible de révoquer l'autorisation")
  } finally {
    pendingRemoval.value = undefined
  }
}

onMounted(async () => {
  await Promise.all([loadServers(), loadUsers()])
  await loadGrants()
})

watch(selectedServer, () => {
  loadGrants()
})
</script>
