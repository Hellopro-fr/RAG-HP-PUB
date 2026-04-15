<template>
  <div>
    <div
      class="flex items-center gap-2 px-3 py-2 border rounded-lg cursor-pointer transition-colors"
      :class="open
        ? 'border-brand-500 ring-2 ring-brand-500/20'
        : 'border-gray-300 dark:border-gray-600 hover:border-gray-400'"
      @click="open = !open"
    >
      <!-- Preview -->
      <span
        class="inline-flex items-center justify-center w-6 h-6 rounded text-xs"
        :class="modelValue || 'bg-gray-100 text-gray-400'"
      >
        <i class="pi pi-palette" />
      </span>
      <span class="text-sm text-gray-700 dark:text-gray-300 flex-1 truncate">
        {{ modelValue || 'Choisir un style...' }}
      </span>
      <i class="pi pi-chevron-down text-xs text-gray-400 transition-transform" :class="{ 'rotate-180': open }" />
    </div>

    <div v-if="open" class="mt-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-lg max-h-72 overflow-hidden">
      <!-- Presets -->
      <div class="p-2 grid grid-cols-2 gap-1.5 overflow-y-auto max-h-52">
        <button
          v-for="preset in presets"
          :key="preset.value"
          type="button"
          class="flex items-center gap-2 px-2.5 py-2 rounded-md border transition-colors text-left"
          :class="modelValue === preset.value
            ? 'border-brand-500 ring-1 ring-brand-500/20'
            : 'border-gray-200 dark:border-gray-700 hover:border-gray-300'"
          @click="select(preset.value)"
        >
          <span
            class="inline-flex items-center justify-center w-7 h-7 rounded text-xs shrink-0"
            :class="preset.value"
          >
            <i class="pi pi-star" />
          </span>
          <span class="text-xs text-gray-600 dark:text-gray-400 truncate">{{ preset.label }}</span>
        </button>
      </div>
      <!-- Custom input -->
      <div class="p-2 border-t border-gray-100 dark:border-gray-800">
        <label class="block text-[10px] text-gray-500 dark:text-gray-400 mb-1">CSS personnalise</label>
        <input
          :value="modelValue"
          type="text"
          class="w-full text-xs border border-gray-300 dark:border-gray-600 rounded px-2 py-1.5 bg-white dark:bg-gray-800 dark:text-gray-200 font-mono"
          placeholder="text-green-600 bg-green-50 ..."
          @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)"
          @click.stop
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

defineProps<{
  modelValue: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const open = ref(false)

const presets = [
  { label: 'Vert', value: 'text-green-600 bg-green-50 dark:bg-green-900/20 dark:text-green-400' },
  { label: 'Bleu', value: 'text-blue-600 bg-blue-50 dark:bg-blue-900/20 dark:text-blue-400' },
  { label: 'Violet', value: 'text-purple-600 bg-purple-50 dark:bg-purple-900/20 dark:text-purple-400' },
  { label: 'Orange', value: 'text-orange-600 bg-orange-50 dark:bg-orange-900/20 dark:text-orange-400' },
  { label: 'Cyan', value: 'text-cyan-600 bg-cyan-50 dark:bg-cyan-900/20 dark:text-cyan-400' },
  { label: 'Rose', value: 'text-pink-600 bg-pink-50 dark:bg-pink-900/20 dark:text-pink-400' },
  { label: 'Rouge', value: 'text-red-600 bg-red-50 dark:bg-red-900/20 dark:text-red-400' },
  { label: 'Jaune', value: 'text-yellow-600 bg-yellow-50 dark:bg-yellow-900/20 dark:text-yellow-400' },
  { label: 'Indigo', value: 'text-indigo-600 bg-indigo-50 dark:bg-indigo-900/20 dark:text-indigo-400' },
  { label: 'Emeraude', value: 'text-emerald-600 bg-emerald-50 dark:bg-emerald-900/20 dark:text-emerald-400' },
  { label: 'Gris', value: 'text-gray-600 bg-gray-100 dark:bg-gray-700 dark:text-gray-300' },
  { label: 'Sombre', value: 'text-gray-900 bg-gray-100 dark:bg-gray-700 dark:text-white' },
  { label: 'Brand', value: 'text-brand-600 bg-brand-50 dark:bg-brand-900/20 dark:text-brand-400' },
  { label: 'Ambre', value: 'text-amber-600 bg-amber-50 dark:bg-amber-900/20 dark:text-amber-400' },
]

function select(value: string) {
  emit('update:modelValue', value)
  open.value = false
}
</script>
