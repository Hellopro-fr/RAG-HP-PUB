<template>
  <div class="fixed inset-0 bg-black/50 z-50 flex items-center justify-center" @click.self="emit('close')">
    <div class="bg-white dark:bg-gray-900 rounded-lg shadow-theme-xl p-6 max-w-lg w-full max-h-[90vh] overflow-y-auto">
      <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-4">Importer .mcp.json</h2>

      <!-- JSON textarea -->
      <div class="mb-4">
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Configuration JSON</label>
        <textarea
          v-model="jsonInput"
          rows="12"
          class="w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 font-mono shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
          :placeholder="samplePlaceholder"
        />
        <p v-if="parseError" class="text-xs text-error-500 dark:text-error-400 mt-1">{{ parseError }}</p>
      </div>

      <!-- File upload / drag-drop zone -->
      <div
        class="mb-4 border-2 border-dashed rounded-lg p-6 text-center transition-colors cursor-pointer"
        :class="isDragging ? 'border-brand-400 bg-brand-50 dark:bg-brand-500/10' : 'border-gray-300 dark:border-gray-700 hover:border-gray-400 dark:hover:border-gray-600'"
        @dragover.prevent="isDragging = true"
        @dragleave.prevent="isDragging = false"
        @drop.prevent="handleDrop"
        @click="fileInput?.click()"
      >
        <input
          ref="fileInput"
          type="file"
          accept=".json,.mcp.json"
          class="hidden"
          @change="handleFileSelect"
        />
        <i class="pi pi-upload text-2xl text-gray-400 dark:text-gray-500 mb-2" />
        <p class="text-sm text-gray-500 dark:text-gray-400">
          <template v-if="fileName">
            <i class="pi pi-file mr-1" />
            {{ fileName }}
          </template>
          <template v-else>
            Glissez-déposez un fichier .mcp.json ou cliquez pour parcourir
          </template>
        </p>
      </div>

      <!-- Auto-discover -->
      <div class="flex items-center gap-2 mb-4">
        <input
          id="import-discover"
          v-model="autoDiscover"
          type="checkbox"
          class="rounded border-gray-300 text-brand-500 dark:border-gray-700"
        />
        <label for="import-discover" class="text-sm text-gray-700 dark:text-gray-300">
          Découvrir automatiquement après import
        </label>
      </div>

      <!-- Results -->
      <div v-if="results" class="mb-4 p-4 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-800 rounded-md">
        <p class="text-sm font-medium text-gray-800 dark:text-gray-200 mb-2">
          {{ results.imported }} importé{{ results.imported > 1 ? 's' : '' }},
          {{ results.skipped }} ignoré{{ results.skipped > 1 ? 's' : '' }},
          {{ results.errors }} erreur{{ results.errors > 1 ? 's' : '' }}
        </p>
        <ul class="space-y-1">
          <li
            v-for="item in results.details"
            :key="item.name"
            class="flex items-center gap-2 text-sm"
          >
            <i
              :class="{
                'pi pi-check-circle text-success-600 dark:text-success-400': item.status === 'imported',
                'pi pi-question-circle text-warning-500 dark:text-warning-400': item.status === 'skipped',
                'pi pi-times-circle text-error-500 dark:text-error-400': item.status === 'error'
              }"
              class="text-sm"
            />
            <span class="font-medium text-gray-800 dark:text-gray-200">{{ item.name }}</span>
            <span v-if="item.message" class="text-gray-500 dark:text-gray-400">— {{ item.message }}</span>
          </li>
        </ul>
      </div>

      <!-- Actions -->
      <div class="flex justify-end gap-3 pt-4 border-t border-gray-100 dark:border-gray-800">
        <button
          type="button"
          class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-white/5 rounded-md hover:bg-gray-200 dark:hover:bg-gray-700"
          @click="emit('close')"
        >
          {{ results ? 'Fermer' : 'Annuler' }}
        </button>
        <button
          v-if="!results"
          class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600 disabled:opacity-50"
          :disabled="!jsonInput.trim() || submitting"
          @click="handleImport"
        >
          <i v-if="submitting" class="pi pi-spinner pi-spin mr-1" />
          Importer
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useServersStore } from '@/stores/servers'
import { useToast } from '@/composables/useToast'
import type { ImportResult } from '@/types/server'

const emit = defineEmits<{ close: []; imported: [] }>()

const serversStore = useServersStore()
const toast = useToast()

const jsonInput = ref('')
const autoDiscover = ref(true)
const submitting = ref(false)
const parseError = ref('')
const results = ref<ImportResult>()
const isDragging = ref(false)
const fileName = ref('')
const fileInput = ref<HTMLInputElement>()

const samplePlaceholder = `{
  "mcpServers": {
    "my-server": {
      "url": "https://mcp.example.com"
    },
    "local-server": {
      "command": "npx",
      "args": ["-y", "@mcp/server"]
    }
  }
}`

function handleFileSelect(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) readFile(file)
}

function handleDrop(event: DragEvent) {
  isDragging.value = false
  const file = event.dataTransfer?.files?.[0]
  if (file) readFile(file)
}

function readFile(file: File) {
  fileName.value = file.name
  const reader = new FileReader()
  reader.onload = (e) => {
    jsonInput.value = e.target?.result as string
    parseError.value = ''
  }
  reader.readAsText(file)
}

async function handleImport() {
  parseError.value = ''
  let parsed: unknown
  try {
    parsed = JSON.parse(jsonInput.value)
  } catch {
    parseError.value = 'JSON invalide'
    return
  }

  submitting.value = true
  try {
    results.value = await serversStore.importServers(parsed, autoDiscover.value)
    emit('imported')
  } catch (err) {
    toast.error(err instanceof Error ? err.message : 'Erreur lors de l\'import')
  } finally {
    submitting.value = false
  }
}
</script>
