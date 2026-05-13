<template>
  <div>
    <div class="flex items-center gap-3 mb-3">
      <input
        v-model="searchLocal"
        type="text"
        placeholder="Filtrer par email ou nom…"
        class="h-9 flex-1 max-w-sm text-sm rounded-md border border-gray-300 dark:border-gray-600 px-3 bg-white dark:bg-gray-800 dark:text-gray-200"
        @input="onSearch"
      />
      <span class="text-xs text-gray-500 dark:text-gray-400">{{ total }} ligne(s)</span>
    </div>

    <div
      v-if="rows.length === 0"
      class="text-center py-12 text-gray-500 dark:text-gray-400 bg-white dark:bg-gray-900 rounded-lg border border-dashed border-gray-200 dark:border-gray-800"
    >
      <p class="text-sm">Aucun import utilisateur.</p>
    </div>

    <DataTable
      v-else
      :value="rows"
      data-key="id"
      :lazy="true"
      :paginator="true"
      :rows="limit"
      :total-records="total"
      :first="(page - 1) * limit"
      :rows-per-page-options="[10, 20, 50]"
      responsive-layout="scroll"
      striped-rows
      class="text-sm"
      @page="onDtPage"
    >
      <Column field="created_by" header="Créateur">
        <template #body="{ data }">
          <span class="font-mono text-xs text-gray-900 dark:text-white">{{ data.created_by }}</span>
        </template>
      </Column>
      <Column field="name" header="Nom" />
      <Column header="URL">
        <template #body="{ data }">
          <span class="font-mono text-xs truncate block max-w-[280px]" :title="data.url">{{ data.url }}</span>
        </template>
      </Column>
      <Column header="Actif" header-style="width: 4rem">
        <template #body="{ data }">
          <span
            class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium"
            :class="data.is_active
              ? 'bg-success-100 text-success-700 dark:bg-success-500/20 dark:text-success-400'
              : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300'"
          >
            {{ data.is_active ? 'oui' : 'non' }}
          </span>
        </template>
      </Column>
      <Column header="Headers">
        <template #body="{ data }">
          <span class="text-xs text-gray-600 dark:text-gray-300">{{ data.auth_header_keys.join(', ') }}</span>
        </template>
      </Column>
      <Column header="Actions" header-style="width: 22rem; text-align: right">
        <template #body="{ data }">
          <div class="inline-flex items-center gap-2 justify-end w-full">
            <ZohoTestResultBadge :result="testResults[data.id] ?? null" />
            <span
              v-if="discoverResults?.[data.id]"
              class="text-xs px-2 py-0.5 rounded-full font-medium"
              :class="discoverResults[data.id]!.ok
                ? 'bg-success-100 text-success-700 dark:bg-success-500/20 dark:text-success-400'
                : 'bg-error-100 text-error-700 dark:bg-error-500/20 dark:text-error-400'"
              :title="`${discoverResults[data.id]!.tools} outils`"
            >
              {{ discoverResults[data.id]!.tools }} outils
            </span>
            <button
              class="text-xs px-2 py-1 rounded-md border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300"
              @click="$emit('test', data)"
            >
              Tester
            </button>
            <button
              class="text-xs px-2 py-1 rounded-md border border-brand-300 dark:border-brand-700 text-brand-600 dark:text-brand-400"
              @click="$emit('discover', data)"
            >
              Découvrir
            </button>
            <button
              class="text-xs px-2 py-1 rounded-md border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300"
              @click="$emit('toggle', data)"
            >
              {{ data.is_active ? 'Désactiver' : 'Activer' }}
            </button>
            <button
              class="text-xs px-2 py-1 rounded-md border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300"
              @click="$emit('edit', data)"
            >
              Modifier
            </button>
            <button
              class="text-xs px-2 py-1 rounded-md border border-error-300 dark:border-error-700 text-error-600"
              @click="$emit('delete', data)"
            >
              Supprimer
            </button>
          </div>
        </template>
      </Column>
    </DataTable>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import DataTable, { type DataTablePageEvent } from 'primevue/datatable'
import Column from 'primevue/column'
import ZohoTestResultBadge from './ZohoTestResultBadge.vue'
import type { ZohoImportRow, ZohoImportTestResponse } from '@/types/zoho'

const props = defineProps<{
  rows: ZohoImportRow[]
  total: number
  page: number
  limit: number
  search: string
  testResults: Record<string, ZohoImportTestResponse>
  discoverResults?: Record<string, { ok: boolean; tools: number }>
}>()

const emit = defineEmits<{
  search: [v: string]
  page: [n: number]
  edit: [r: ZohoImportRow]
  delete: [r: ZohoImportRow]
  toggle: [r: ZohoImportRow]
  test: [r: ZohoImportRow]
  discover: [r: ZohoImportRow]
}>()

const searchLocal = ref(props.search)

watch(
  () => props.search,
  (v) => {
    searchLocal.value = v
  }
)

let searchTimer: ReturnType<typeof setTimeout> | null = null

function onSearch() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => emit('search', searchLocal.value), 250)
}

function onDtPage(e: DataTablePageEvent) {
  emit('page', e.page + 1)
}
</script>
