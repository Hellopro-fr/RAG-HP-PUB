<script setup lang="ts">
import { computed, h, ref } from 'vue'
import type { ColumnDef } from '@tanstack/vue-table'
import DataTable from '@/components/common/DataTable.vue'
import type { ApiCatalogEndpoint } from '@/types/apiCatalog'

const props = defineProps<{ endpoints: ApiCatalogEndpoint[] }>()
const search = ref('')

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return props.endpoints
  return props.endpoints.filter(
    (e) =>
      e.path.toLowerCase().includes(q) ||
      (e.summary || '').toLowerCase().includes(q),
  )
})

const columns: ColumnDef<ApiCatalogEndpoint, any>[] = [
  {
    accessorKey: 'method',
    header: 'Méthode',
    cell: (i) => h('code', { class: 'font-mono text-xs' }, (i.getValue() as string) || '-'),
  },
  {
    accessorKey: 'path',
    header: 'Chemin',
    cell: (i) => h('code', { class: 'font-mono text-xs' }, i.getValue() as string),
  },
  { accessorKey: 'summary', header: 'Résumé' },
  {
    id: 'tags',
    header: 'Tags',
    accessorFn: (row) => (row.tags || []).join(', '),
    cell: (i) => i.getValue() as string,
  },
]
</script>
<template>
  <div>
    <input
      v-model="search"
      type="text"
      placeholder="Filtrer par chemin ou résumé…"
      class="mb-3 w-full max-w-sm rounded border px-3 py-2 text-sm dark:bg-gray-800 dark:border-gray-700"
    />
    <DataTable :rows="filtered" :columns="columns" />
  </div>
</template>
