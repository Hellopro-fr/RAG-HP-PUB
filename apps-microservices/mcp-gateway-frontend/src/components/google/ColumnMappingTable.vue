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

        <!-- Dual-mode fields (tags, tool_prefix): sheet column OR manual -->
        <template v-if="field.dualMode">
          <div class="flex-1 flex items-center gap-2">
            <!-- Toggle -->
            <div class="flex rounded-md border border-gray-300 dark:border-gray-600 overflow-hidden shrink-0">
              <button
                type="button"
                :class="[
                  'px-2 py-1.5 text-xs',
                  dualModes[field.key] === 'sheet'
                    ? 'bg-brand-500 text-white'
                    : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700'
                ]"
                @click="setDualMode(field.key, 'sheet')"
              >
                Feuille
              </button>
              <button
                type="button"
                :class="[
                  'px-2 py-1.5 text-xs',
                  dualModes[field.key] === 'manual'
                    ? 'bg-brand-500 text-white'
                    : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700'
                ]"
                @click="setDualMode(field.key, 'manual')"
              >
                Manuel
              </button>
            </div>

            <!-- Sheet column dropdown -->
            <select
              v-if="dualModes[field.key] === 'sheet'"
              :value="(modelValue as Record<string, string>)[field.key] || ''"
              class="flex-1 text-sm border border-gray-300 dark:border-gray-600 rounded-md px-3 py-2 bg-white dark:bg-gray-800 dark:text-gray-200"
              @change="updateField(field.key, ($event.target as HTMLSelectElement).value)"
            >
              <option value="">— Aucune —</option>
              <option v-for="h in headers" :key="h" :value="h">{{ h }}</option>
            </select>

            <!-- Manual input -->
            <input
              v-else
              :value="manualValues[field.key] || ''"
              type="text"
              :placeholder="field.manualPlaceholder"
              class="flex-1 text-sm border border-gray-300 dark:border-gray-600 rounded-md px-3 py-2 bg-white dark:bg-gray-800 dark:text-gray-200 placeholder:text-gray-400 dark:placeholder:text-white/30"
              @input="updateManual(field.key, ($event.target as HTMLInputElement).value)"
            />
          </div>
        </template>

        <!-- Standard fields: sheet column only -->
        <select
          v-else
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
import { reactive } from 'vue'
import type { ColumnMapping } from '@/types/google'

const props = defineProps<{
  headers: string[]
  modelValue: ColumnMapping
  fixedTags: string
  fixedToolPrefix: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: ColumnMapping]
  'update:fixedTags': [value: string]
  'update:fixedToolPrefix': [value: string]
}>()

interface FieldDef {
  key: string
  label: string
  required: boolean
  dualMode?: boolean
  manualPlaceholder?: string
}

const fields: FieldDef[] = [
  { key: 'name', label: 'Nom du serveur', required: true },
  { key: 'url', label: 'URL du serveur', required: true },
  { key: 'auth_headers', label: 'En-têtes auth (JSON)', required: false },
  { key: 'tags', label: 'Tags', required: false, dualMode: true, manualPlaceholder: 'tag1, tag2, tag3' },
  { key: 'transport_preference', label: 'Préférence transport', required: false },
  { key: 'connect_timeout_ms', label: 'Timeout (ms)', required: false },
  { key: 'tool_prefix', label: 'Préfixe outil', required: false, dualMode: true, manualPlaceholder: 'myprefix' },
  { key: 'icon', label: 'Icône (URL)', required: false },
  { key: 'mcp_transport', label: 'Transport MCP', required: false },
  { key: 'mcp_command', label: 'Commande MCP', required: false },
  { key: 'mcp_args', label: 'Arguments MCP (JSON)', required: false },
  { key: 'mcp_env', label: 'Env MCP (JSON)', required: false },
  { key: 'doc_slug', label: 'Slug documentation', required: false },
  { key: 'doc_description', label: 'Description documentation', required: false },
]

// Track which mode each dual-mode field is in
const dualModes = reactive<Record<string, 'sheet' | 'manual'>>({
  tags: props.fixedTags ? 'manual' : 'sheet',
  tool_prefix: props.fixedToolPrefix ? 'manual' : 'sheet',
})

// Track manual values
const manualValues = reactive<Record<string, string>>({
  tags: props.fixedTags || '',
  tool_prefix: props.fixedToolPrefix || '',
})

function updateField(key: string, value: string) {
  emit('update:modelValue', { ...props.modelValue, [key]: value })
}

function setDualMode(key: string, mode: 'sheet' | 'manual') {
  dualModes[key] = mode
  if (mode === 'manual') {
    // Clear sheet column mapping
    updateField(key, '')
  } else {
    // Clear manual value
    manualValues[key] = ''
    if (key === 'tags') emit('update:fixedTags', '')
    if (key === 'tool_prefix') emit('update:fixedToolPrefix', '')
  }
}

function updateManual(key: string, value: string) {
  manualValues[key] = value
  if (key === 'tags') emit('update:fixedTags', value)
  if (key === 'tool_prefix') emit('update:fixedToolPrefix', value)
}
</script>
