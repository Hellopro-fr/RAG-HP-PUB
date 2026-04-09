<template>
  <div>
    <PageBreadcrumb page-title="Utilisateurs" />

    <!-- Loading -->
    <div v-if="loading" class="text-center py-12">
      <i class="pi pi-spinner pi-spin text-2xl text-brand-500" />
    </div>

    <PageHeaderTabs
      v-else
      v-model="activeTab"
      :tabs="tabs"
    >
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

            <!-- Role badge + stats -->
            <div class="flex flex-wrap items-center gap-3">
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
        <p class="font-medium">Aucun utilisateur</p>
      </div>
    </PageHeaderTabs>

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
import { ref, computed, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { usersApi } from '@/api/users'
import { useToast } from '@/composables/useToast'
import PageBreadcrumb from '@/components/common/PageBreadcrumb.vue'
import PageHeaderTabs from '@/components/common/PageHeaderTabs.vue'
import ConfirmDialog from '@/components/shared/ConfirmDialog.vue'
import type { User } from '@/types/user'

const authStore = useAuthStore()
const toast = useToast()

const users = ref<User[]>([])
const loading = ref(false)
const activeTab = ref('all')
const deletingUserId = ref<number | undefined>()
const updatingId = ref<number | undefined>()

const adminCount = computed(() => users.value.filter(u => u.role === 'admin').length)
const readOnlyCount = computed(() => users.value.filter(u => u.role === 'read-only').length)
const configOnlyCount = computed(() => users.value.filter(u => u.role === 'config-only').length)

const tabs = computed(() => [
  { label: 'Tous', value: 'all', count: users.value.length },
  { label: 'Admin', value: 'admin', count: adminCount.value },
  { label: 'Lecture seule', value: 'read-only', count: readOnlyCount.value },
  { label: 'Config seule', value: 'config-only', count: configOnlyCount.value },
])

const filteredUsers = computed(() => {
  if (activeTab.value === 'all') return users.value
  return users.value.filter(u => u.role === activeTab.value)
})

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
  const parts = email.split('@')[0].split(/[._-]/)
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase()
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
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length]
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
