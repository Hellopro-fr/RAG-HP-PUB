<script setup lang="ts">
import { h, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { ColumnDef } from '@tanstack/vue-table'
import * as usersApi from '@/api/users'
import DataTable from '@/components/common/DataTable.vue'

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
          h(
            'button',
            { class: 'text-yellow-600', onClick: () => action(usersApi.demote, u.email, 'Rétrograder') },
            'Rétrograder',
          ),
        )
      } else {
        buttons.push(
          h(
            'button',
            { class: 'text-blue-600', onClick: () => action(usersApi.promote, u.email, 'Promouvoir') },
            'Promouvoir',
          ),
        )
      }
      if (u.is_allowed) {
        buttons.push(
          h(
            'button',
            { class: 'text-red-600', onClick: () => action(usersApi.block, u.email, 'Bloquer') },
            'Bloquer',
          ),
        )
      } else {
        buttons.push(
          h(
            'button',
            { class: 'text-green-600', onClick: () => action(usersApi.unblock, u.email, 'Débloquer') },
            'Débloquer',
          ),
        )
      }
      buttons.push(
        h(
          'button',
          {
            class: 'text-red-700',
            onClick: () => action(usersApi.revoke, u.email, 'Révoquer toutes les sessions de'),
          },
          'Révoquer',
        ),
      )
      buttons.push(
        h(
          'button',
          {
            class: 'text-gray-600',
            onClick: () =>
              router.push(`/admin/users/${encodeURIComponent(u.email)}/sessions`),
          },
          'Sessions',
        ),
      )
      return h('div', { class: 'flex gap-2 justify-end flex-wrap' }, buttons)
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
