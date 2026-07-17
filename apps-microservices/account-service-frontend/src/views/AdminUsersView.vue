<script setup lang="ts">
import { h, onMounted, ref, type Component } from 'vue'
import { useRouter } from 'vue-router'
import type { ColumnDef } from '@tanstack/vue-table'
import { ChevronUp, ChevronDown, Lock, Unlock, KeyRound, Users } from 'lucide-vue-next'
import * as usersApi from '@/api/users'
import DataTable from '@/components/common/DataTable.vue'

function iconButton(icon: Component, title: string, color: string, onClick: () => void) {
  return h(
    'button',
    {
      type: 'button',
      title,
      'aria-label': title,
      class:
        'inline-flex items-center justify-center w-8 h-8 rounded-md text-gray-500 hover:bg-gray-100 dark:hover:bg-white/5 ' +
        color,
      onClick,
    },
    h(icon, { size: 16 }),
  )
}

const router = useRouter()
const items = ref<usersApi.AdminUser[]>([])
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const r = await usersApi.list(200, 0)
    items.value = r.items
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Erreur'
  } finally {
    loading.value = false
  }
}

async function action(fn: (e: string) => Promise<unknown>, email: string, label: string) {
  if (!confirm(`${label} ${email} ?`)) return
  try {
    await fn(email)
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Erreur'
  }
}

onMounted(load)

const columns: ColumnDef<usersApi.AdminUser, any>[] = [
  {
    accessorKey: 'email',
    header: 'Email',
    cell: (info) => h('span', { class: 'font-mono text-sm' }, info.getValue() as string),
  },
  { accessorKey: 'display_name', header: 'Nom' },
  {
    accessorKey: 'is_admin',
    header: 'Admin',
    cell: (info) => (info.getValue() ? '✔' : ''),
  },
  {
    accessorKey: 'is_allowed',
    header: 'Autorisé',
    cell: (info) =>
      h(
        'span',
        { class: info.getValue() ? 'text-green-600' : 'text-red-600' },
        info.getValue() ? '✔' : '✗',
      ),
  },
  {
    accessorKey: 'last_login_at',
    header: 'Dernière connexion',
    cell: (info) => (info.getValue() as string) ?? '—',
  },
  {
    id: 'actions',
    header: '',
    enableSorting: false,
    cell: (info) => {
      const u = info.row.original
      const buttons: ReturnType<typeof h>[] = []
      if (u.is_admin) {
        buttons.push(
          iconButton(ChevronDown, 'Rétrograder', 'hover:text-yellow-600', () =>
            action(usersApi.demote, u.email, 'Rétrograder'),
          ),
        )
      } else {
        buttons.push(
          iconButton(ChevronUp, 'Promouvoir admin', 'hover:text-brand-500', () =>
            action(usersApi.promote, u.email, 'Promouvoir'),
          ),
        )
      }
      if (u.is_allowed) {
        buttons.push(
          iconButton(Lock, 'Bloquer', 'hover:text-red-600', () =>
            action(usersApi.block, u.email, 'Bloquer'),
          ),
        )
      } else {
        buttons.push(
          iconButton(Unlock, 'Débloquer', 'hover:text-green-600', () =>
            action(usersApi.unblock, u.email, 'Débloquer'),
          ),
        )
      }
      buttons.push(
        iconButton(KeyRound, 'Révoquer toutes les sessions', 'hover:text-red-700', () =>
          action(usersApi.revoke, u.email, 'Révoquer toutes les sessions de'),
        ),
      )
      buttons.push(
        iconButton(Users, 'Voir les sessions', 'hover:text-gray-700', () =>
          router.push(`/admin/users/${encodeURIComponent(u.email)}/sessions`),
        ),
      )
      return h('div', { class: 'flex gap-1 justify-end' }, buttons)
    },
  },
]
</script>

<template>
  <div class="p-6">
    <h1 class="text-2xl font-semibold mb-4">Utilisateurs</h1>
    <div v-if="error" class="mb-4 p-3 bg-red-50 text-red-700 rounded">{{ error }}</div>
    <p v-if="loading" class="text-sm text-gray-500">Chargement...</p>
    <DataTable
      v-else
      :rows="items"
      :columns="columns"
      search-placeholder="Rechercher par email, nom..."
      empty-text="Aucun utilisateur"
    />
  </div>
</template>
