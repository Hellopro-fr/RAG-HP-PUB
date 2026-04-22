<template>
  <div>
    <!-- OS Tabs -->
    <div class="flex gap-1.5 mb-3">
      <button
        v-for="os in osList"
        :key="os.id"
        type="button"
        class="px-2.5 py-1 text-xs font-medium rounded-md border transition-colors"
        :class="activeOS === os.id
          ? 'border-brand-500 text-brand-600 bg-brand-50 dark:bg-brand-500/10 dark:text-brand-400 dark:border-brand-400'
          : 'border-gray-200 dark:border-gray-700 text-gray-500 dark:text-gray-400 hover:border-gray-400'"
        @click="activeOS = os.id; editingIndex = null"
      >
        {{ os.label }}
        <span class="ml-0.5 text-gray-400">({{ (install[os.id] || []).length }})</span>
      </button>
    </div>

    <!-- Options list -->
    <div class="space-y-1.5 mb-2">
      <div
        v-for="(opt, i) in currentOptions"
        :key="i"
        class="rounded-md border transition-all cursor-pointer text-xs"
        :class="editingIndex === i
          ? 'border-brand-500 bg-brand-50/50 dark:bg-brand-500/5 ring-1 ring-brand-500/20'
          : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 hover:border-gray-300'"
        @click="editingIndex = i"
      >
        <!-- Collapsed: preview -->
        <div class="flex items-center justify-between px-2.5 py-1.5">
          <div class="flex items-center gap-1.5 min-w-0">
            <span class="inline-flex items-center justify-center w-4 h-4 rounded-full bg-brand-500 text-white text-[10px] font-semibold shrink-0">{{ i + 1 }}</span>
            <span class="truncate text-gray-700 dark:text-gray-300">{{ opt.label || 'Sans titre' }}</span>
          </div>
          <button
            type="button"
            class="p-0.5 text-gray-400 hover:text-red-500 shrink-0"
            @click.stop="removeOption(i)"
          >
            <i class="pi pi-times text-[10px]" />
          </button>
        </div>

        <!-- Expanded: inline edit -->
        <div v-if="editingIndex === i" class="px-2.5 pb-2.5 space-y-2 border-t border-gray-100 dark:border-gray-800 pt-2" @click.stop>
          <div>
            <label class="block text-[10px] font-medium text-gray-500 dark:text-gray-400 mb-0.5">Label</label>
            <input
              v-model="opt.label"
              type="text"
              placeholder="Via Homebrew (recommande)"
              class="w-full rounded border border-gray-300 bg-white px-2 py-1 text-xs dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
            />
          </div>
          <div>
            <label class="block text-[10px] font-medium text-gray-500 dark:text-gray-400 mb-0.5">Description (HTML)</label>
            <textarea
              v-model="opt.note"
              rows="2"
              placeholder="Explication..."
              class="w-full rounded border border-gray-300 bg-white px-2 py-1 text-xs dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
            />
          </div>
          <div>
            <label class="block text-[10px] font-medium text-gray-500 dark:text-gray-400 mb-0.5">Commande</label>
            <textarea
              v-model="opt.code"
              rows="2"
              placeholder="brew install node"
              class="w-full rounded border border-gray-300 bg-white px-2 py-1 text-xs font-mono dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
            />
          </div>
        </div>
      </div>
    </div>

    <!-- Empty state -->
    <div v-if="!currentOptions.length" class="text-center py-4 text-gray-400 dark:text-gray-500 text-xs">
      Aucune option pour {{ activeOSLabel }}
    </div>

    <!-- Add button -->
    <button
      type="button"
      class="w-full flex items-center justify-center gap-1.5 px-2.5 py-1.5 text-xs font-medium text-brand-500 border border-dashed border-brand-300 dark:border-brand-600 rounded-md hover:bg-brand-50 dark:hover:bg-brand-500/10 transition"
      @click="addOption"
    >
      <i class="pi pi-plus text-[10px]" />
      Ajouter une option
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { InstallOption } from '@/types/install-guide'

const props = defineProps<{
  modelValue: Record<string, InstallOption[]>
}>()

const emit = defineEmits<{
  'update:modelValue': [value: Record<string, InstallOption[]>]
}>()

const install = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const osList = [
  { id: 'windows', label: 'Win' },
  { id: 'linux', label: 'Linux' },
  { id: 'macos', label: 'macOS' },
]

const activeOS = ref('windows')
const editingIndex = ref<number | null>(null)

const activeOSLabel = computed(() => osList.find(o => o.id === activeOS.value)?.label || activeOS.value)

const currentOptions = computed({
  get: () => install.value[activeOS.value] || [],
  set: (val) => {
    install.value = { ...install.value, [activeOS.value]: val }
  }
})

function addOption() {
  currentOptions.value = [...currentOptions.value, { label: '', note: '', code: '' }]
  editingIndex.value = currentOptions.value.length - 1
}

function removeOption(index: number) {
  if (editingIndex.value === index) editingIndex.value = null
  else if (editingIndex.value !== null && editingIndex.value > index) editingIndex.value--
  const copy = [...currentOptions.value]
  copy.splice(index, 1)
  currentOptions.value = copy
}
</script>
