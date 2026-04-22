<template>
  <div>
    <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
      Icone du serveur
    </label>

    <!-- Selected icon preview -->
    <div v-if="modelValue" class="flex items-center gap-3 mb-3">
      <img
        :src="modelValue"
        alt="Icon"
        class="w-10 h-10 rounded border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 object-contain p-1"
      />
      <button
        type="button"
        class="text-xs text-gray-500 hover:text-red-500 dark:text-gray-400 dark:hover:text-red-400"
        @click="$emit('update:modelValue', '')"
      >
        <i class="pi pi-times mr-1" />
        Retirer
      </button>
    </div>

    <!-- Icon grid -->
    <div v-if="!collapsed || !modelValue" class="space-y-4">
      <!-- Built-in icons -->
      <div v-if="builtinIcons.length > 0">
        <p class="text-xs text-gray-500 dark:text-gray-400 mb-2">Icones predefinies</p>
        <div class="grid grid-cols-8 gap-2">
          <button
            v-for="icon in builtinIcons"
            :key="icon.path"
            type="button"
            class="w-10 h-10 rounded border p-1 flex items-center justify-center transition hover:shadow-sm"
            :class="modelValue === icon.path
              ? 'border-brand-500 bg-brand-50 dark:bg-brand-500/10 ring-2 ring-brand-500/30'
              : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 hover:border-brand-300 dark:hover:border-brand-600'"
            :title="icon.label"
            @click="$emit('update:modelValue', icon.path)"
          >
            <img :src="icon.path" :alt="icon.label" class="w-7 h-7 object-contain" />
          </button>
        </div>
      </div>

      <!-- Uploaded icons -->
      <div v-if="uploadedIcons.length > 0">
        <p class="text-xs text-gray-500 dark:text-gray-400 mb-2">Icones importees</p>
        <div class="grid grid-cols-8 gap-2">
          <button
            v-for="icon in uploadedIcons"
            :key="icon"
            type="button"
            class="w-10 h-10 rounded border p-1 flex items-center justify-center transition hover:shadow-sm"
            :class="modelValue === icon
              ? 'border-brand-500 bg-brand-50 dark:bg-brand-500/10 ring-2 ring-brand-500/30'
              : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 hover:border-brand-300 dark:hover:border-brand-600'"
            @click="$emit('update:modelValue', icon)"
          >
            <img :src="icon" :alt="icon" class="w-7 h-7 object-contain" />
          </button>
        </div>
      </div>

      <!-- Upload -->
      <div>
        <label
          class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-white/5 rounded-md hover:bg-gray-200 dark:hover:bg-gray-700 cursor-pointer transition"
        >
          <i class="pi pi-upload text-xs" />
          Importer une icone
          <input
            type="file"
            accept=".svg,.png,.jpg,.jpeg,.webp"
            class="hidden"
            @change="handleUpload"
          />
        </label>
        <span v-if="uploading" class="ml-2 text-xs text-gray-400">
          <i class="pi pi-spinner pi-spin mr-1" />
          Envoi...
        </span>
        <p v-if="uploadError" class="text-xs text-error-500 dark:text-error-400 mt-1">{{ uploadError }}</p>
      </div>
    </div>

    <!-- Toggle collapsed -->
    <button
      v-if="modelValue && (builtinIcons.length > 0 || uploadedIcons.length > 0)"
      type="button"
      class="mt-2 text-xs text-brand-500 hover:text-brand-600 dark:text-brand-400"
      @click="collapsed = !collapsed"
    >
      {{ collapsed ? 'Changer l\'icone' : 'Replier' }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { serversApi } from '@/api/servers'

defineProps<{
  modelValue: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

// Built-in icons from public/images/servers/
const builtinIcons = ref<{ path: string; label: string }[]>([])

// Uploaded icons from backend
const uploadedIcons = ref<string[]>([])

const collapsed = ref(true)
const uploading = ref(false)
const uploadError = ref('')

// Built-in SVGs bundled with the frontend
const BUILTIN_SVGS: { path: string; label: string }[] = [
  { path: '/images/servers/bdd.svg', label: 'Base de donnees' },
  { path: '/images/servers/google-analytics.svg', label: 'Google Analytics' },
  { path: '/images/servers/google-search-console.svg', label: 'Google Search Console' },
  { path: '/images/servers/leexi.svg', label: 'Leexi' },
  { path: '/images/servers/neo4j.svg', label: 'Neo4j' },
  { path: '/images/servers/rag.svg', label: 'RAG Pipeline' },
  { path: '/images/servers/ringover.svg', label: 'Ringover' },
  { path: '/images/servers/semrush.svg', label: 'SEMrush' },
  { path: '/images/servers/zoho.svg', label: 'Zoho CRM' },
]

onMounted(async () => {
  builtinIcons.value = BUILTIN_SVGS

  try {
    uploadedIcons.value = await serversApi.listIcons()
  } catch {
    // Silently fail — uploaded icons are optional
  }
})

async function handleUpload(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  uploading.value = true
  uploadError.value = ''

  try {
    const iconPath = await serversApi.uploadIcon(file)
    uploadedIcons.value.push(iconPath)
    emit('update:modelValue', iconPath)
    collapsed.value = true
  } catch (err) {
    uploadError.value = err instanceof Error ? err.message : 'Erreur lors de l\'envoi'
  } finally {
    uploading.value = false
    input.value = ''
  }
}
</script>
