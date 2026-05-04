<script setup lang="ts" generic="TData">
import { computed, ref, watch } from 'vue'
import {
  FlexRender,
  type ColumnDef,
  type SortingState,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useVueTable,
} from '@tanstack/vue-table'

const props = defineProps<{
  rows: TData[]
  columns: ColumnDef<TData, any>[]
  pageSize?: number
  searchPlaceholder?: string
  emptyText?: string
}>()

const sorting = ref<SortingState>([])
const globalFilter = ref('')
const pagination = ref({
  pageIndex: 0,
  pageSize: props.pageSize ?? 10,
})

watch(globalFilter, () => {
  pagination.value.pageIndex = 0
})

const table = useVueTable({
  get data() {
    return props.rows
  },
  get columns() {
    return props.columns
  },
  state: {
    get sorting() { return sorting.value },
    get globalFilter() { return globalFilter.value },
    get pagination() { return pagination.value },
  },
  onSortingChange: (updater) => {
    sorting.value = typeof updater === 'function' ? updater(sorting.value) : updater
  },
  onGlobalFilterChange: (updater) => {
    globalFilter.value = typeof updater === 'function' ? updater(globalFilter.value) : updater
  },
  onPaginationChange: (updater) => {
    pagination.value = typeof updater === 'function' ? updater(pagination.value) : updater
  },
  getCoreRowModel: getCoreRowModel(),
  getSortedRowModel: getSortedRowModel(),
  getFilteredRowModel: getFilteredRowModel(),
  getPaginationRowModel: getPaginationRowModel(),
})

const totalRows = computed(() => table.getFilteredRowModel().rows.length)
const startRow = computed(() =>
  totalRows.value === 0 ? 0 : pagination.value.pageIndex * pagination.value.pageSize + 1,
)
const endRow = computed(() =>
  Math.min((pagination.value.pageIndex + 1) * pagination.value.pageSize, totalRows.value),
)
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
      <div class="relative w-full sm:max-w-xs">
        <span class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">🔍</span>
        <input
          v-model="globalFilter"
          type="text"
          :placeholder="searchPlaceholder ?? 'Rechercher...'"
          class="w-full h-10 pl-9 pr-3 border border-gray-300 rounded-lg dark:bg-gray-900 dark:border-gray-700 dark:text-white"
        />
      </div>
      <div class="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
        <label class="flex items-center gap-2">
          <span>Lignes :</span>
          <select
            :value="pagination.pageSize"
            @change="(e) => table.setPageSize(Number((e.target as HTMLSelectElement).value))"
            class="h-9 px-2 border border-gray-300 rounded-md dark:bg-gray-900 dark:border-gray-700 dark:text-white"
          >
            <option v-for="n in [10, 20, 50, 100]" :key="n" :value="n">{{ n }}</option>
          </select>
        </label>
      </div>
    </div>

    <div class="overflow-hidden rounded-xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-white/[0.03]">
      <div class="max-w-full overflow-x-auto">
        <table class="min-w-full text-sm">
          <thead class="bg-gray-50 dark:bg-gray-800/40">
            <tr v-for="hg in table.getHeaderGroups()" :key="hg.id">
              <th
                v-for="header in hg.headers"
                :key="header.id"
                :colspan="header.colSpan"
                class="px-5 py-3 text-left font-medium text-gray-500 text-xs uppercase tracking-wider dark:text-gray-400"
              >
                <button
                  v-if="!header.isPlaceholder"
                  type="button"
                  class="flex items-center gap-1 select-none"
                  :class="header.column.getCanSort() ? 'cursor-pointer hover:text-gray-700 dark:hover:text-gray-200' : 'cursor-default'"
                  @click="header.column.getToggleSortingHandler()?.($event)"
                >
                  <FlexRender :render="header.column.columnDef.header" :props="header.getContext()" />
                  <span v-if="header.column.getIsSorted() === 'asc'">▲</span>
                  <span v-else-if="header.column.getIsSorted() === 'desc'">▼</span>
                </button>
              </th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-200 dark:divide-gray-700">
            <tr
              v-for="row in table.getRowModel().rows"
              :key="row.id"
              class="hover:bg-gray-50 dark:hover:bg-white/[0.02]"
            >
              <td
                v-for="cell in row.getVisibleCells()"
                :key="cell.id"
                class="px-5 py-3 text-gray-700 dark:text-gray-200"
              >
                <FlexRender :render="cell.column.columnDef.cell" :props="cell.getContext()" />
              </td>
            </tr>
            <tr v-if="totalRows === 0">
              <td :colspan="columns.length" class="px-5 py-12 text-center text-gray-500">
                {{ emptyText ?? 'Aucune donnée' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 text-sm">
      <span class="text-gray-500 dark:text-gray-400">
        {{ startRow }}–{{ endRow }} sur {{ totalRows }}
      </span>
      <div class="flex items-center gap-2">
        <button
          type="button"
          class="px-3 py-1 border rounded-md disabled:opacity-40 dark:border-gray-700"
          :disabled="!table.getCanPreviousPage()"
          @click="table.setPageIndex(0)"
        >«</button>
        <button
          type="button"
          class="px-3 py-1 border rounded-md disabled:opacity-40 dark:border-gray-700"
          :disabled="!table.getCanPreviousPage()"
          @click="table.previousPage()"
        >‹ Précédent</button>
        <span class="px-2">
          {{ pagination.pageIndex + 1 }} / {{ Math.max(1, table.getPageCount()) }}
        </span>
        <button
          type="button"
          class="px-3 py-1 border rounded-md disabled:opacity-40 dark:border-gray-700"
          :disabled="!table.getCanNextPage()"
          @click="table.nextPage()"
        >Suivant ›</button>
        <button
          type="button"
          class="px-3 py-1 border rounded-md disabled:opacity-40 dark:border-gray-700"
          :disabled="!table.getCanNextPage()"
          @click="table.setPageIndex(table.getPageCount() - 1)"
        >»</button>
      </div>
    </div>
  </div>
</template>
