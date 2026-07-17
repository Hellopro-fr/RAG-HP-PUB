<script setup lang="ts">
import { computed, defineComponent, h, ref } from 'vue'
import type { ColumnDef } from '@tanstack/vue-table'
import DataTable from '@/components/common/DataTable.vue'
import type { ApiCatalogEndpoint, AuthPolicy } from '@/types/apiCatalog'
import { updateEndpoint } from '@/api/apiCatalog'

const props = defineProps<{ serviceId: string; endpoints: ApiCatalogEndpoint[] }>()
const emit = defineEmits<{ (e: 'updated', endpoint: ApiCatalogEndpoint): void }>()

const search = ref('')
const saving = ref<Record<string, boolean>>({})

async function onPolicyChange(ep: ApiCatalogEndpoint, value: string) {
  saving.value[ep.id] = true
  const prev = ep.authPolicy
  const payload = { authPolicy: value === '' ? null : (value as AuthPolicy) }
  try {
    const next = await updateEndpoint(props.serviceId, ep.id, payload)
    emit('updated', next)
  } catch (err) {
    ep.authPolicy = prev
    console.error('updateEndpoint failed:', err)
    alert('Failed to update endpoint policy: ' + (err as Error).message)
  } finally {
    saving.value[ep.id] = false
  }
}

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return props.endpoints
  return props.endpoints.filter(
    (e) =>
      e.path.toLowerCase().includes(q) ||
      (e.summary || '').toLowerCase().includes(q),
  )
})

// Inline sub-component so the select can access reactive `saving` from closure
const PolicySelect = defineComponent({
  props: { ep: { type: Object as () => ApiCatalogEndpoint, required: true } },
  setup(p) {
    return () =>
      h(
        'select',
        {
          value: p.ep.authPolicy ?? '',
          disabled: saving.value[p.ep.id] ?? false,
          class:
            'rounded border border-gray-300 bg-transparent px-2 py-1 text-xs text-gray-800 focus:border-brand-300 focus:outline-hidden focus:ring-2 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 disabled:opacity-50',
          onChange: (e: Event) =>
            onPolicyChange(p.ep, (e.target as HTMLSelectElement).value),
        },
        [
          h('option', { value: '' }, '(inherit)'),
          h('option', { value: 'public' }, 'public'),
          h('option', { value: 'bearer' }, 'bearer'),
          h('option', { value: 'admin-key' }, 'admin-key'),
        ],
      )
  },
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
  {
    id: 'authPolicy',
    header: 'Politique',
    cell: (i) => h(PolicySelect, { ep: i.row.original }),
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
