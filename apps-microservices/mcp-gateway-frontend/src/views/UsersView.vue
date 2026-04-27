<template>
  <div>
    <PageBreadcrumb page-title="Utilisateurs" />

    <!-- Loading -->
    <div v-if="loading" class="text-center py-12">
      <i class="pi pi-spinner pi-spin text-2xl text-brand-500" />
    </div>

    <template v-else>
      <!-- Filters -->
      <FilterPanel
        :active-count="activeFilterCount"
        @reset="resetFilters"
      >
        <label class="flex flex-col gap-1 text-sm">
          <span class="text-gray-600 dark:text-gray-400">Email ou nom</span>
          <input v-model="filters.search" type="text" placeholder="Rechercher..." class="px-3 py-2 text-sm border border-gray-300 rounded-md bg-white dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200 placeholder:text-gray-400" />
        </label>
        <label class="flex flex-col gap-1 text-sm">
          <span class="text-gray-600 dark:text-gray-400">Rôle</span>
          <select v-model="filters.role" class="px-3 py-2 text-sm border border-gray-300 rounded-md bg-white dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200">
            <option value="">Tous</option>
            <option value="admin">Admin</option>
            <option value="read-only">Lecture seule</option>
            <option value="config-only">Config seule</option>
          </select>
        </label>
        <label class="flex flex-col gap-1 text-sm">
          <span class="text-gray-600 dark:text-gray-400">Accès</span>
          <select v-model="filters.allowed" class="px-3 py-2 text-sm border border-gray-300 rounded-md bg-white dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200">
            <option value="">Tous</option>
            <option value="allowed">Autorisé</option>
            <option value="blocked">Bloqué</option>
          </select>
        </label>
        <label class="flex flex-col gap-1 text-sm">
          <span class="text-gray-600 dark:text-gray-400">Dernière connexion après</span>
          <input v-model="filters.lastLoginFrom" type="date" class="px-3 py-2 text-sm border border-gray-300 rounded-md bg-white dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200" />
        </label>
        <label class="flex flex-col gap-1 text-sm">
          <span class="text-gray-600 dark:text-gray-400">Dernière connexion avant</span>
          <input v-model="filters.lastLoginTo" type="date" class="px-3 py-2 text-sm border border-gray-300 rounded-md bg-white dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200" />
        </label>
      </FilterPanel>

      <!-- User cards -->
      <div
        v-if="filteredUsers.length"
        class="grid grid-cols-1 gap-4"
      >
        <div
          v-for="user in filteredUsers"
          :key="user.id"
          class="rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800 p-4 sm:p-5"
        >
          <!-- Row 1: identity + role + stats -->
          <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <!-- Avatar + identity -->
            <div class="flex items-center gap-3">
              <div
                class="h-10 w-10 rounded-full flex items-center justify-center text-sm font-semibold text-white shrink-0"
                :class="avatarColor(user.email)"
              >
                {{ initials(user.email) }}
              </div>
              <div>
                <p class="text-sm font-semibold text-gray-900 dark:text-white">
                  {{ user.display_name || user.email }}
                </p>
                <p class="text-xs text-gray-500 dark:text-gray-400">{{ user.email }}</p>
              </div>
            </div>

            <!-- Status + Role badge + stats -->
            <div class="flex flex-wrap items-center gap-3">
              <span
                class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium"
                :class="user.is_allowed
                  ? 'bg-success-100 text-success-700 dark:bg-success-500/20 dark:text-success-400'
                  : 'bg-error-100 text-error-700 dark:bg-error-500/20 dark:text-error-400'"
              >
                {{ user.is_allowed ? 'Autorisé' : 'Bloqué' }}
              </span>
              <span
                class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium"
                :class="roleBadgeClass(user.role)"
              >
                {{ roleLabel(user.role) }}
              </span>
              <span class="text-xs text-gray-500 dark:text-gray-400">
                <i class="pi pi-sign-in mr-1" />
                {{ user.login_count }} connexion{{ user.login_count !== 1 ? 's' : '' }}
              </span>
              <span v-if="user.last_login_at" class="text-xs text-gray-500 dark:text-gray-400">
                <i class="pi pi-clock mr-1" />
                Dernière connexion : {{ formatDate(user.last_login_at) }}
              </span>
              <span v-else class="text-xs text-gray-400 dark:text-gray-500 italic">
                Jamais connecté
              </span>
            </div>
          </div>

          <!-- Row 2: actions -->
          <div class="mt-4 flex flex-wrap items-center gap-3 border-t border-gray-100 dark:border-gray-700 pt-4">
            <!-- Access toggle -->
            <button
              v-if="user.email !== authStore.user?.email"
              class="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md border"
              :class="user.is_allowed
                ? 'text-error-600 border-error-300 hover:bg-error-50 dark:hover:bg-error-500/10'
                : 'text-success-600 border-success-300 hover:bg-success-50 dark:hover:bg-success-500/10'"
              :disabled="togglingId === user.id"
              @click="handleToggleAllowed(user)"
            >
              <i class="pi text-xs" :class="user.is_allowed ? 'pi-lock' : 'pi-lock-open'" />
              {{ user.is_allowed ? 'Bloquer' : 'Autoriser' }}
              <i v-if="togglingId === user.id" class="pi pi-spinner pi-spin text-xs" />
            </button>

            <!-- Role selector -->
            <div class="flex items-center gap-2">
              <label class="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">Rôle :</label>
              <select
                :value="user.role"
                :disabled="user.email === authStore.user?.email || updatingId === user.id"
                class="text-sm border border-gray-300 dark:border-gray-600 rounded-md px-2 py-1.5 bg-white dark:bg-gray-800 dark:text-gray-200 disabled:opacity-50 disabled:cursor-not-allowed"
                @change="handleRoleChange(user, ($event.target as HTMLSelectElement).value)"
              >
                <option value="admin">Admin</option>
                <option value="read-only">Lecture seule</option>
                <option value="config-only">Config seule</option>
              </select>
              <i v-if="updatingId === user.id" class="pi pi-spinner pi-spin text-brand-500 text-sm" />
            </div>

            <!-- Audit logs link -->
            <router-link
              :to="{ path: '/audit-logs', query: { user_email: user.email } }"
              class="inline-flex items-center gap-1 px-3 py-1.5 text-sm font-medium text-brand-500 border border-brand-300 rounded-md hover:bg-brand-50 dark:hover:bg-brand-500/10"
            >
              <i class="pi pi-list text-xs" />
              Voir les logs
            </router-link>

            <!-- Delete button -->
            <button
              v-if="user.email !== authStore.user?.email"
              class="inline-flex items-center gap-1 px-3 py-1.5 text-sm font-medium text-error-600 border border-error-300 rounded-md hover:bg-error-50 dark:hover:bg-error-500/10 ml-auto"
              @click="deletingUserId = user.id"
            >
              <i class="pi pi-trash text-xs" />
              Supprimer
            </button>
            <span
              v-else
              class="ml-auto text-xs text-gray-400 dark:text-gray-500 italic"
            >
              Votre compte
            </span>
          </div>
        </div>
      </div>

      <!-- Empty state -->
      <div
        v-else
        class="text-center py-12 text-gray-500 dark:text-gray-400"
      >
        <i class="pi pi-users text-4xl mb-3 block" />
        <p class="font-medium">{{ activeFilterCount > 0 ? 'Aucun utilisateur ne correspond aux filtres' : 'Aucun utilisateur' }}</p>
      </div>
    </template>

    <!-- Delete confirm -->
    <ConfirmDialog
      :open="deletingUserId !== undefined"
      title="Supprimer l'utilisateur"
      message="Êtes-vous sûr de vouloir supprimer cet utilisateur ? Cette action est irréversible."
      confirm-label="Supprimer"
      @update:open="deletingUserId = undefined"
      @confirm="confirmDelete"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { usersApi } from '@/api/users'
import { useToast } from '@/composables/useToast'
import PageBreadcrumb from '@/components/common/PageBreadcrumb.vue'
import ConfirmDialog from '@/components/shared/ConfirmDialog.vue'
import FilterPanel from '@/components/shared/FilterPanel.vue'
import type { User } from '@/types/user'

const authStore = useAuthStore()
const toast = useToast()

const users = ref<User[]>([])
const loading = ref(false)
const deletingUserId = ref<number | undefined>()
const updatingId = ref<number | undefined>()
const togglingId = ref<number | undefined>()

const filters = reactive({
  search: '',
  role: '' as '' | 'admin' | 'read-only' | 'config-only',
  allowed: '' as '' | 'allowed' | 'blocked',
  lastLoginFrom: '',
  lastLoginTo: '',
})

function matchesLastLogin(iso: string | undefined): boolean {
  if (!filters.lastLoginFrom && !filters.lastLoginTo) return true
  if (!iso) return false
  const d = iso.slice(0, 10)
  if (filters.lastLoginFrom && d < filters.lastLoginFrom) return false
  if (filters.lastLoginTo && d > filters.lastLoginTo) return false
  return true
}

const filteredUsers = computed(() => {
  const q = filters.search.trim().toLowerCase()
  return users.value.filter(u => {
    if (q) {
      const hay = (u.email + ' ' + (u.display_name || '')).toLowerCase()
      if (!hay.includes(q)) return false
    }
    if (filters.role && u.role !== filters.role) return false
    if (filters.allowed === 'allowed' && !u.is_allowed) return false
    if (filters.allowed === 'blocked' && u.is_allowed) return false
    if (!matchesLastLogin(u.last_login_at)) return false
    return true
  })
})

const activeFilterCount = computed(() => {
  let n = 0
  if (filters.search.trim()) n++
  if (filters.role) n++
  if (filters.allowed) n++
  if (filters.lastLoginFrom) n++
  if (filters.lastLoginTo) n++
  return n
})

function resetFilters() {
  filters.search = ''
  filters.role = ''
  filters.allowed = ''
  filters.lastLoginFrom = ''
  filters.lastLoginTo = ''
}

onMounted(() => {
  loadUsers()
})

async function loadUsers() {
  loading.value = true
  try {
    const response = await usersApi.list()
    users.value = response.users
  } catch {
    toast.error('Impossible de charger les utilisateurs')
  } finally {
    loading.value = false
  }
}

async function handleToggleAllowed(user: User) {
  togglingId.value = user.id
  try {
    await usersApi.toggleAllowed(user.id, !user.is_allowed)
    user.is_allowed = !user.is_allowed
    toast.success(`${user.email} ${user.is_allowed ? 'autorisé' : 'bloqué'}`)
  } catch (err: any) {
    const msg = err?.body?.error || 'Impossible de modifier l\'accès'
    toast.error(msg)
  } finally {
    togglingId.value = undefined
  }
}

async function handleRoleChange(user: User, newRole: string) {
  updatingId.value = user.id
  try {
    await usersApi.update(user.id, newRole)
    user.role = newRole as User['role']
    toast.success(`Rôle de ${user.email} mis à jour`)
  } catch {
    toast.error('Impossible de mettre à jour le rôle')
  } finally {
    updatingId.value = undefined
  }
}

async function confirmDelete() {
  if (deletingUserId.value === undefined) return
  const id = deletingUserId.value
  try {
    await usersApi.delete(id)
    users.value = users.value.filter(u => u.id !== id)
    toast.success('Utilisateur supprimé')
  } catch {
    toast.error('Impossible de supprimer l\'utilisateur')
  } finally {
    deletingUserId.value = undefined
  }
}

function initials(email: string): string {
  const parts = email.split('@')[0]?.split(/[._-]/) ?? []
  if (parts.length >= 2 && parts[0] && parts[1]) {
    return (parts[0][0]! + parts[1][0]!).toUpperCase()
  }
  return email.slice(0, 2).toUpperCase()
}

const AVATAR_COLORS = [
  'bg-blue-500',
  'bg-green-500',
  'bg-purple-500',
  'bg-orange-500',
  'bg-pink-500',
  'bg-teal-500',
  'bg-indigo-500',
  'bg-red-500',
]

function avatarColor(email: string): string {
  let hash = 0
  for (let i = 0; i < email.length; i++) {
    hash = (hash * 31 + email.charCodeAt(i)) & 0xffffffff
  }
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length]!
}

function roleBadgeClass(role: User['role']): string {
  switch (role) {
    case 'admin':
      return 'bg-error-100 text-error-700 dark:bg-error-500/20 dark:text-error-400'
    case 'read-only':
      return 'bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-400'
    case 'config-only':
      return 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300'
  }
}

function roleLabel(role: User['role']): string {
  switch (role) {
    case 'admin':
      return 'Admin'
    case 'read-only':
      return 'Lecture seule'
    case 'config-only':
      return 'Config seule'
  }
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('fr-FR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}
</script>
