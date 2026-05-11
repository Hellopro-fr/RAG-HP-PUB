<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { ColumnDef } from '@tanstack/vue-table'
import { RefreshIcon } from '@/icons'
import * as apiCatalog from '@/api/apiCatalog'
import type { ApiCatalogService, Protocol, Source, Status } from '@/types/apiCatalog'
import { useAuthStore } from '@/stores/auth'
import DataTable from '@/components/common/DataTable.vue'
import ProtocolBadge from '@/components/api-catalog/ProtocolBadge.vue'
import ScanStatusBadge from '@/components/api-catalog/ScanStatusBadge.vue'

const router = useRouter()
const auth = useAuthStore()

const items = ref<ApiCatalogService[]>([])
const loading = ref(true)
const error = ref('')
const rescanning = ref(false)
const rescanMsg = ref('')

// Filters
const searchText = ref('')
const filterProtocol = ref<Protocol | ''>('')
const filterStatus = ref<Status | ''>('')
const filterSource = ref<Source | ''>('')

const filtered = computed(() => {
  return items.value.filter((s) => {
    if (filterProtocol.value && !s.protocols.includes(filterProtocol.value as Protocol)) return false
    if (filterStatus.value && s.status !== filterStatus.value) return false
    if (filterSource.value && s.source !== filterSource.value) return false
    if (searchText.value) {
      const q = searchText.value.toLowerCase()
      if (!s.name.toLowerCase().includes(q) && !(s.description || '').toLowerCase().includes(q)) return false
    }
    return true
  })
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    const r = await apiCatalog.list(200, 0)
    items.value = r.items
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Erreur de chargement'
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function rescanAll() {
  rescanning.value = true
  rescanMsg.value = ''
  try {
    const r = await apiCatalog.rescanAll()
    rescanMsg.value = `Rescan terminé : ${r.servicesOk}/${r.servicesScanned} OK`
    await load()
  } catch (e) {
    rescanMsg.value = e instanceof Error ? e.message : 'Erreur rescan'
  } finally {
    rescanning.value = false
  }
}

const statusLabel: Record<Status, string> = {
  active: 'Actif',
  deprecated: 'Déprécié',
  down: 'Hors ligne',
}

const statusCls: Record<Status, string> = {
  active: 'text-green-600',
  deprecated: 'text-yellow-600',
  down: 'text-red-600',
}

const columns: ColumnDef<ApiCatalogService, any>[] = [
  {
    accessorKey: 'name',
    header: 'Nom',
    cell: (info) =>
      h(
        'button',
        {
          type: 'button',
          class: 'font-medium text-blue-600 hover:underline',
          onClick: () => router.push(`/admin/api/${info.row.original.id}`),
        },
        info.getValue() as string,
      ),
  },
  {
    id: 'protocols',
    header: 'Protocoles',
    accessorFn: (row) => row.protocols.join(','),
    cell: (info) => {
      const svc = info.row.original
      return h(
        'div',
        { class: 'flex gap-1 flex-wrap' },
        svc.protocols.map((p) => h(ProtocolBadge, { protocol: p, key: p })),
      )
    },
  },
  {
    accessorKey: 'status',
    header: 'Statut',
    cell: (info) => {
      const s = info.getValue() as Status
      return h('span', { class: statusCls[s] }, statusLabel[s])
    },
  },
  {
    accessorKey: 'source',
    header: 'Source',
    cell: (info) => h('code', { class: 'text-xs font-mono' }, info.getValue() as string),
  },
  {
    id: 'lastScan',
    header: 'Dernier scan',
    accessorFn: (row) => row.lastScannedAt || '',
    cell: (info) => {
      const svc = info.row.original
      return h(ScanStatusBadge, { ok: svc.lastScanOk, at: svc.lastScannedAt })
    },
  },
  {
    id: 'endpoints',
    header: 'Endpoints',
    accessorFn: () => '—',
    enableSorting: false,
    cell: () => h('span', { class: 'text-gray-400 text-xs' }, '—'),
  },
]
</script>

<template>
  <div class="p-6">
    <div class="flex items-center justify-between mb-4 flex-wrap gap-3">
      <h1 class="text-2xl font-semibold">Catalogue API</h1>
      <div class="flex gap-2">
        <button
          v-if="auth.isAdmin"
          class="inline-flex items-center gap-1.5 px-3 py-2 text-sm rounded-md border border-gray-300 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-50"
          :disabled="rescanning"
          @click="rescanAll"
        >
          <RefreshIcon class="w-4 h-4" />
          {{ rescanning ? 'Scan en cours…' : 'Rescan all' }}
        </button>
        <button
          v-if="auth.isAdmin"
          class="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 text-sm"
          @click="router.push('/admin/api/new')"
        >
          + Créer
        </button>
      </div>
    </div>

    <div v-if="rescanMsg" class="mb-3 p-3 bg-blue-50 text-blue-700 rounded-md text-sm">
      {{ rescanMsg }}
    </div>

    <!-- Filters -->
    <div class="mb-4 flex flex-wrap gap-3">
      <input
        v-model="searchText"
        type="text"
        placeholder="Rechercher par nom ou description…"
        class="h-9 rounded-lg border border-gray-200 px-3 text-sm dark:bg-gray-900 dark:border-gray-700 dark:text-white"
      />
      <select
        v-model="filterProtocol"
        class="h-9 rounded-lg border border-gray-200 px-2 text-sm dark:bg-gray-900 dark:border-gray-700 dark:text-white"
      >
        <option value="">Tous protocoles</option>
        <option value="rest">REST</option>
        <option value="ws">WebSocket</option>
        <option value="grpc">gRPC</option>
      </select>
      <select
        v-model="filterStatus"
        class="h-9 rounded-lg border border-gray-200 px-2 text-sm dark:bg-gray-900 dark:border-gray-700 dark:text-white"
      >
        <option value="">Tous statuts</option>
        <option value="active">Actif</option>
        <option value="deprecated">Déprécié</option>
        <option value="down">Hors ligne</option>
      </select>
      <select
        v-model="filterSource"
        class="h-9 rounded-lg border border-gray-200 px-2 text-sm dark:bg-gray-900 dark:border-gray-700 dark:text-white"
      >
        <option value="">Toutes sources</option>
        <option value="env">env</option>
        <option value="manual">manual</option>
        <option value="scan">scan</option>
      </select>
    </div>

    <div v-if="error" class="mb-4 p-3 bg-red-50 text-red-700 rounded-md">{{ error }}</div>
    <p v-if="loading" class="text-sm text-gray-500">Chargement...</p>
    <DataTable
      v-else
      :rows="filtered"
      :columns="columns"
      search-placeholder="Filtrer…"
      empty-text="Aucun service dans le catalogue"
    />
  </div>
</template>
