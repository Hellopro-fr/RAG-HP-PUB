<script setup lang="ts">
import { h, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { ColumnDef } from '@tanstack/vue-table'
import * as servicesApi from '@/api/services'
import type { OAuth2Client } from '@/types/oauth2'
import DataTable from '@/components/common/DataTable.vue'

const router = useRouter()
const items = ref<OAuth2Client[]>([])
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const r = await servicesApi.list(100, 0)
    items.value = r.items
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Erreur de chargement'
  } finally {
    loading.value = false
  }
}

onMounted(load)

const columns: ColumnDef<OAuth2Client, any>[] = [
  {
    accessorKey: 'name',
    header: 'Nom',
    cell: (info) => h('span', { class: 'font-medium' }, info.getValue() as string),
  },
  {
    accessorKey: 'client_id',
    header: 'client_id',
    cell: (info) => {
      const v = (info.getValue() as string) || ''
      return h('code', { class: 'font-mono text-xs text-gray-600 dark:text-gray-300' }, v.slice(0, 12) + '…')
    },
  },
  {
    id: 'redirect_uris',
    header: 'Redirect URIs',
    accessorFn: (row) => row.redirect_uris?.length ?? 0,
    cell: (info) => `${info.getValue()} URI`,
  },
  {
    accessorKey: 'token_ttl_s',
    header: 'TTL token',
    cell: (info) => `${info.getValue()}s`,
  },
  {
    accessorKey: 'is_active',
    header: 'Actif',
    cell: (info) =>
      h(
        'span',
        { class: info.getValue() ? 'text-green-600' : 'text-red-600' },
        info.getValue() ? 'oui' : 'non',
      ),
  },
  {
    id: 'actions',
    header: '',
    enableSorting: false,
    cell: (info) =>
      h(
        'button',
        {
          class: 'text-blue-600 hover:underline',
          onClick: () => router.push(`/admin/services/${info.row.original.id}/edit`),
        },
        'Modifier',
      ),
  },
]
</script>

<template>
  <div class="p-6">
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-2xl font-semibold">Services OAuth2</h1>
      <button
        class="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
        @click="router.push('/admin/services/new')"
      >
        + Nouveau service
      </button>
    </div>

    <div v-if="error" class="mb-4 p-3 bg-red-50 text-red-700 rounded-md">{{ error }}</div>
    <p v-if="loading" class="text-sm text-gray-500">Chargement...</p>
    <DataTable
      v-else
      :rows="items"
      :columns="columns"
      search-placeholder="Rechercher par nom, client_id..."
      empty-text="Aucun service enregistré"
    />
  </div>
</template>
