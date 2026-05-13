<template>
  <div class="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-5">
    <div v-if="admin" class="flex items-start justify-between gap-4">
      <div class="min-w-0">
        <h3 class="text-sm font-semibold text-gray-900 dark:text-white">
          {{ admin.name || 'Compte admin Zoho' }}
        </h3>
        <p class="text-xs text-gray-500 dark:text-gray-400 mt-1 truncate" :title="admin.url">
          {{ admin.url }}
        </p>
        <div class="text-xs text-gray-500 dark:text-gray-400 mt-2 flex gap-3">
          <span>Actif : <strong>{{ admin.is_active ? 'oui' : 'non' }}</strong></span>
          <span>Headers : {{ admin.auth_header_keys.join(', ') || 'aucun' }}</span>
        </div>
      </div>
      <div class="flex gap-2 shrink-0">
        <button
          class="text-xs px-2 py-1 rounded-md border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300"
          @click="$emit('test')"
        >
          Tester
        </button>
        <button
          class="text-xs px-2 py-1 rounded-md border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300"
          @click="$emit('edit')"
        >
          Modifier
        </button>
        <button
          class="text-xs px-2 py-1 rounded-md border border-error-300 dark:border-error-700 text-error-600"
          @click="$emit('delete')"
        >
          Supprimer
        </button>
      </div>
    </div>

    <div v-if="testResult" class="mt-3">
      <ZohoTestResultBadge :result="testResult" />
    </div>

    <div v-if="!admin" class="text-center py-6 text-gray-500 dark:text-gray-400">
      <p class="text-sm mb-3">Aucun compte admin configuré.</p>
      <button
        class="px-3 py-1.5 text-sm rounded-md text-white bg-brand-500 hover:bg-brand-600"
        @click="$emit('create')"
      >
        Configurer le compte admin
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import ZohoTestResultBadge from './ZohoTestResultBadge.vue'
import type { ZohoImportRow, ZohoImportTestResponse } from '@/types/zoho'

defineProps<{
  admin: ZohoImportRow | null
  testResult: ZohoImportTestResponse | null
}>()

defineEmits<{
  edit: []
  test: []
  delete: []
  create: []
}>()
</script>
