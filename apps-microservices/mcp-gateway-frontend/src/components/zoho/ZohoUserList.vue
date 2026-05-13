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

    <table v-else class="w-full text-sm">
      <thead>
        <tr class="text-left text-xs uppercase text-gray-500 dark:text-gray-400">
          <th class="py-2">Créateur</th>
          <th>Nom</th>
          <th>URL</th>
          <th>Actif</th>
          <th>Headers</th>
          <th class="text-right">Actions</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-gray-100 dark:divide-gray-800">
        <tr v-for="r in rows" :key="r.id" class="text-sm">
          <td class="py-2 font-mono text-xs">{{ r.created_by }}</td>
          <td>{{ r.name }}</td>
          <td class="font-mono text-xs truncate max-w-[280px]" :title="r.url">{{ r.url }}</td>
          <td>{{ r.is_active ? 'oui' : 'non' }}</td>
          <td class="text-xs">{{ r.auth_header_keys.join(', ') }}</td>
          <td class="text-right">
            <div class="flex justify-end items-center gap-2">
              <ZohoTestResultBadge :result="testResults[r.id] ?? null" />
              <button
                class="text-xs px-2 py-1 rounded-md border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300"
                @click="$emit('test', r)"
              >
                Tester
              </button>
              <button
                class="text-xs px-2 py-1 rounded-md border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300"
                @click="$emit('toggle', r)"
              >
                {{ r.is_active ? 'Désactiver' : 'Activer' }}
              </button>
              <button
                class="text-xs px-2 py-1 rounded-md border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300"
                @click="$emit('edit', r)"
              >
                Modifier
              </button>
              <button
                class="text-xs px-2 py-1 rounded-md border border-error-300 dark:border-error-700 text-error-600"
                @click="$emit('delete', r)"
              >
                Supprimer
              </button>
            </div>
          </td>
        </tr>
      </tbody>
    </table>

    <div v-if="totalPages > 1" class="flex justify-center items-center gap-2 mt-4 text-sm">
      <button
        class="px-2 py-1 rounded-md border border-gray-300 dark:border-gray-600 disabled:opacity-40"
        :disabled="page <= 1"
        @click="$emit('page', page - 1)"
      >
        Précédent
      </button>
      <span>{{ page }} / {{ totalPages }}</span>
      <button
        class="px-2 py-1 rounded-md border border-gray-300 dark:border-gray-600 disabled:opacity-40"
        :disabled="page >= totalPages"
        @click="$emit('page', page + 1)"
      >
        Suivant
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import ZohoTestResultBadge from './ZohoTestResultBadge.vue'
import type { ZohoImportRow, ZohoImportTestResponse } from '@/types/zoho'

const props = defineProps<{
  rows: ZohoImportRow[]
  total: number
  page: number
  limit: number
  search: string
  testResults: Record<string, ZohoImportTestResponse>
}>()

const emit = defineEmits<{
  search: [v: string]
  page: [n: number]
  edit: [r: ZohoImportRow]
  delete: [r: ZohoImportRow]
  toggle: [r: ZohoImportRow]
  test: [r: ZohoImportRow]
}>()

const searchLocal = ref(props.search)

watch(
  () => props.search,
  (v) => {
    searchLocal.value = v
  }
)

const totalPages = computed(() => Math.max(1, Math.ceil(props.total / props.limit)))

let searchTimer: ReturnType<typeof setTimeout> | null = null

function onSearch() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => emit('search', searchLocal.value), 250)
}
</script>
