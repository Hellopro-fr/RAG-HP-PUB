<template>
  <div>
    <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">
      Correspondance des colonnes
    </h3>
    <div class="space-y-3">
      <div
        v-for="field in fields"
        :key="field.key"
        class="flex items-center gap-3"
      >
        <label
          class="w-48 text-sm text-gray-700 dark:text-gray-300 shrink-0"
          :class="{ 'font-semibold': field.required }"
        >
          {{ field.label }}
          <span v-if="field.required" class="text-error-500">*</span>
        </label>
        <select
          :value="(modelValue as Record<string, string>)[field.key] || ''"
          class="flex-1 text-sm border border-gray-300 dark:border-gray-600 rounded-md px-3 py-2 bg-white dark:bg-gray-800 dark:text-gray-200"
          @change="updateField(field.key, ($event.target as HTMLSelectElement).value)"
        >
          <option value="">— Aucune —</option>
          <option v-for="h in headers" :key="h" :value="h">{{ h }}</option>
        </select>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { ColumnMapping } from '@/types/google'

const props = defineProps<{
  headers: string[]
  modelValue: ColumnMapping
}>()

const emit = defineEmits<{
  'update:modelValue': [value: ColumnMapping]
}>()

interface FieldDef {
  key: string
  label: string
  required: boolean
}

const fields: FieldDef[] = [
  { key: 'name', label: 'Nom du serveur', required: true },
  { key: 'url', label: 'URL du serveur', required: true },
  { key: 'auth_headers', label: 'En-têtes auth (JSON)', required: false },
  { key: 'tags', label: 'Tags (séparés par virgule)', required: false },
  { key: 'transport_preference', label: 'Préférence transport', required: false },
  { key: 'connect_timeout_ms', label: 'Timeout (ms)', required: false },
  { key: 'tool_prefix', label: 'Préfixe outil', required: false },
  { key: 'icon', label: 'Icône (URL)', required: false },
  { key: 'mcp_transport', label: 'Transport MCP', required: false },
  { key: 'mcp_command', label: 'Commande MCP', required: false },
  { key: 'mcp_args', label: 'Arguments MCP (JSON)', required: false },
  { key: 'mcp_env', label: 'Env MCP (JSON)', required: false },
  { key: 'doc_slug', label: 'Slug documentation', required: false },
  { key: 'doc_description', label: 'Description documentation', required: false },
]

function updateField(key: string, value: string) {
  emit('update:modelValue', { ...props.modelValue, [key]: value })
}
</script>
