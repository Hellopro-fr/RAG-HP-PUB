<template>
  <div>
    <PageBreadcrumb page-title="Serveur Autorisation" />

    <p class="mb-6 text-sm text-gray-600 dark:text-gray-400">
      Octroie un accès complet (sans filtre Leexi / Ringover / BDD) à un ou plusieurs
      utilisateurs sur un ou plusieurs serveurs MCP.
    </p>

    <div
      class="mb-6 rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900"
    >
      <div class="grid gap-4 md:grid-cols-2">
        <!-- Server checkbox list -->
        <div class="space-y-2">
          <div class="flex items-center justify-between">
            <span class="text-sm text-gray-600 dark:text-gray-400">
              Serveurs ({{ selectedServerIds.length }} sélectionné(s))
            </span>
            <div class="flex gap-3 text-xs">
              <button
                type="button"
                class="text-brand-500 hover:text-brand-600 font-medium"
                @click="selectAllServers"
              >
                Tout
              </button>
              <button
                type="button"
                class="text-brand-500 hover:text-brand-600 font-medium"
                @click="selectedServerIds = []"
              >
                Aucun
              </button>
            </div>
          </div>
          <input
            v-model="serverSearch"
            type="text"
            placeholder="Rechercher un serveur…"
            class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
          />
          <div
            class="border border-gray-200 dark:border-gray-800 rounded-lg divide-y divide-gray-100 dark:divide-gray-800 max-h-[320px] overflow-y-auto"
          >
            <label
              v-for="s in filteredServers"
              :key="s.id"
              class="flex items-center gap-3 px-4 py-2.5 cursor-pointer bg-white dark:bg-gray-900 hover:bg-gray-50 dark:hover:bg-white/5"
            >
              <input
                type="checkbox"
                :value="s.id"
                v-model="selectedServerIds"
                class="rounded border-gray-300 text-brand-500 dark:border-gray-700 shrink-0"
              />
              <i class="pi pi-server text-sm text-gray-400 dark:text-gray-500" />
              <span class="text-sm text-gray-800 dark:text-gray-200 truncate">{{ s.name }}</span>
            </label>
            <div
              v-if="filteredServers.length === 0"
              class="px-4 py-6 text-center text-sm text-gray-400 dark:text-gray-500"
            >
              Aucun serveur trouvé
            </div>
          </div>
        </div>

        <!-- User checkbox list -->
        <div class="space-y-2">
          <div class="flex items-center justify-between">
            <span class="text-sm text-gray-600 dark:text-gray-400">
              Utilisateurs ({{ selectedEmails.length }} sélectionné(s))
            </span>
            <div class="flex gap-3 text-xs">
              <button
                type="button"
                class="text-brand-500 hover:text-brand-600 font-medium"
                @click="selectAllUsers"
              >
                Tout
              </button>
              <button
                type="button"
                class="text-brand-500 hover:text-brand-600 font-medium"
                @click="selectedEmails = []"
              >
                Aucun
              </button>
            </div>
          </div>
          <input
            v-model="userSearch"
            type="text"
            placeholder="Rechercher un utilisateur…"
            class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
          />
          <div
            class="border border-gray-200 dark:border-gray-800 rounded-lg divide-y divide-gray-100 dark:divide-gray-800 max-h-[320px] overflow-y-auto"
          >
            <label
              v-for="u in filteredUsers"
              :key="u.id"
              class="flex items-center gap-3 px-4 py-2.5 cursor-pointer bg-white dark:bg-gray-900 hover:bg-gray-50 dark:hover:bg-white/5"
            >
              <input
                type="checkbox"
                :value="u.email"
                v-model="selectedEmails"
                class="rounded border-gray-300 text-brand-500 dark:border-gray-700 shrink-0"
              />
              <i class="pi pi-user text-sm text-gray-400 dark:text-gray-500" />
              <div class="min-w-0 flex-1">
                <p class="text-sm text-gray-800 dark:text-gray-200 truncate">
                  {{ u.display_name || u.email }}
                </p>
                <p
                  v-if="u.display_name"
                  class="text-[11px] text-gray-400 dark:text-gray-500 truncate"
                >
                  {{ u.email }}
                </p>
              </div>
            </label>
            <div
              v-if="filteredUsers.length === 0"
              class="px-4 py-6 text-center text-sm text-gray-400 dark:text-gray-500"
            >
              Aucun utilisateur trouvé
            </div>
          </div>
        </div>
      </div>

      <div class="mt-4 flex items-center justify-between">
        <p class="text-xs text-gray-500 dark:text-gray-400">
          {{ pairCount }} autorisation(s) seront créées.
        </p>
        <button
          type="button"
          :disabled="pairCount === 0 || creating"
          class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-50"
          @click="addGrants"
        >
          {{ creating ? 'Octroi…' : 'Octroyer' }}
        </button>
      </div>
    </div>

    <div v-if="loading" class="text-center py-12">
      <i class="pi pi-spinner pi-spin text-2xl text-brand-500" />
    </div>

    <template v-else>
      <h2 class="mb-3 text-base font-semibold text-gray-900 dark:text-white">
        Autorisations
        <span class="ml-2 text-sm font-normal text-gray-500 dark:text-gray-400">
          ({{ filteredGrants.length }})
        </span>
      </h2>

      <div
        v-if="filteredGrants.length === 0"
        class="rounded-lg border border-dashed border-gray-300 bg-white py-12 text-center text-gray-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-400"
      >
        <i class="pi pi-shield text-4xl mb-3 block" />
        <p class="font-medium">Aucune autorisation enregistrée.</p>
        <p class="text-sm mt-1">
          Sélectionnez serveurs et utilisateurs pour octroyer des accès.
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
              <th class="px-4 py-3 font-medium">Serveur</th>
              <th class="px-4 py-3 font-medium">Octroyé par</th>
              <th class="px-4 py-3 font-medium">Date</th>
              <th class="px-4 py-3 text-right font-medium">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-200 dark:divide-gray-700">
            <tr
              v-for="g in filteredGrants"
              :key="`${g.server_id}-${g.email}`"
              class="text-gray-700 dark:text-gray-200"
            >
              <td class="px-4 py-3">{{ g.email }}</td>
              <td class="px-4 py-3">
                <span class="text-sm">
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
import { computed, onMounted, ref } from 'vue'
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
const grants = ref<ServerAuthorization[]>([])

const selectedServerIds = ref<string[]>([])
const selectedEmails = ref<string[]>([])
const serverSearch = ref('')
const userSearch = ref('')

const loading = ref(false)
const creating = ref(false)
const pendingRemoval = ref<ServerAuthorization | undefined>(undefined)

const filteredServers = computed(() => {
  const q = serverSearch.value.trim().toLowerCase()
  if (!q) return servers.value
  return servers.value.filter((s) => s.name.toLowerCase().includes(q))
})

const filteredUsers = computed(() => {
  const q = userSearch.value.trim().toLowerCase()
  if (!q) return users.value
  return users.value.filter(
    (u) =>
      u.email.toLowerCase().includes(q) ||
      (u.display_name ?? '').toLowerCase().includes(q),
  )
})

const pairCount = computed(
  () => selectedServerIds.value.length * selectedEmails.value.length,
)

const filteredGrants = computed(() => {
  if (selectedServerIds.value.length === 0) return grants.value
  const set = new Set(selectedServerIds.value)
  return grants.value.filter((g) => set.has(g.server_id))
})

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

function selectAllServers(): void {
  selectedServerIds.value = filteredServers.value.map((s) => s.id)
}

function selectAllUsers(): void {
  selectedEmails.value = filteredUsers.value.map((u) => u.email)
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
    grants.value = await serverAuthorizationsApi.list()
  } catch {
    toast.error('Impossible de charger les autorisations')
    grants.value = []
  } finally {
    loading.value = false
  }
}

async function addGrants(): Promise<void> {
  if (pairCount.value === 0) return
  creating.value = true
  let ok = 0
  let fail = 0
  try {
    for (const serverID of selectedServerIds.value) {
      for (const email of selectedEmails.value) {
        try {
          await serverAuthorizationsApi.create({
            server_id: serverID,
            email,
          })
          ok++
        } catch {
          fail++
        }
      }
    }
    if (fail === 0) {
      toast.success(`${ok} autorisation(s) octroyée(s)`)
    } else {
      toast.error(`${ok} octroyée(s), ${fail} échec(s)`)
    }
    selectedEmails.value = []
    await loadGrants()
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
</script>
