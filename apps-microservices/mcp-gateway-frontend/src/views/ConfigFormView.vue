<template>
  <div>
    <PageBreadcrumb :page-title="isEdit ? 'Modifier configuration' : 'Nouvelle configuration'" />

    <div v-if="loading" class="text-center py-12">
      <i class="pi pi-spinner pi-spin text-2xl text-brand-500" />
    </div>

    <template v-else>
      <!-- Info card -->
      <div class="bg-white dark:bg-gray-900 rounded-lg shadow-theme-xs border border-gray-200 dark:border-gray-800 p-5 mb-6">
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Slug *</label>
            <div class="flex items-center gap-2">
              <span class="text-sm text-gray-400 dark:text-gray-500 shrink-0">/install-guide/config/</span>
              <input v-model="form.slug" type="text" class="h-10 min-w-0 flex-1 rounded-lg border border-gray-300 bg-transparent px-3 py-2 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30" placeholder="claude-code" />
            </div>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Label *</label>
            <input v-model="form.label" type="text" class="h-10 w-full rounded-lg border border-gray-300 bg-transparent px-3 py-2 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30" placeholder="Claude Code" />
          </div>
        </div>

        <div class="mt-4">
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Description</label>
          <WysiwygEditor v-model="form.description" placeholder="Description affichee sur la carte..." />
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Icone</label>
            <PrimeIconPicker v-model="form.icon" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Couleur</label>
            <ColorClassPicker v-model="form.color" />
          </div>
        </div>

        <!-- Import / Export -->
        <div class="mt-4 pt-4">
          <div class="flex items-center gap-3 mb-4">
            <div class="flex-1 border-t border-gray-200 dark:border-gray-700" />
            <span class="text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">ou</span>
            <div class="flex-1 border-t border-gray-200 dark:border-gray-700" />
          </div>
          <div class="flex items-center gap-3">
            <button
              type="button"
              class="h-10 inline-flex items-center gap-1.5 px-4 text-xs font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-white/5 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700 transition shrink-0"
              @click="handleExport"
            >
              <i class="pi pi-download text-xs" />
              Exporter JSON
            </button>
            <div
              class="h-10 flex-1 min-w-0 flex items-center justify-center gap-2 px-4 rounded-lg border-2 border-dashed transition-colors cursor-pointer"
              :class="dragOverImport
                ? 'border-brand-400 bg-brand-50/50 dark:bg-brand-500/5 text-brand-600 dark:text-brand-400'
                : 'border-gray-300 dark:border-gray-700 text-gray-500 dark:text-gray-400 hover:border-gray-400 dark:hover:border-gray-600'"
              @dragover.prevent="dragOverImport = true"
              @dragleave="dragOverImport = false"
              @drop.prevent="handleDropImport"
              @click="(fileInput as HTMLInputElement)?.click()"
            >
              <i class="pi pi-upload text-xs" />
              <span class="text-xs font-medium">Glisser un fichier JSON ici ou cliquer pour importer</span>
              <input ref="fileInput" type="file" accept=".json" class="hidden" @change="handleImport" />
            </div>
          </div>
        </div>
      </div>

      <!-- Steps builder -->
      <div class="mb-6">
        <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">Etapes</h2>
        <StepBuilder v-model="steps" />
      </div>

      <!-- Actions -->
      <div class="flex gap-3 pt-4 border-t border-gray-200 dark:border-gray-700 mb-6">
        <button
          class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600 disabled:opacity-50"
          :disabled="submitting"
          @click="handleSave"
        >
          {{ submitting ? 'Enregistrement...' : (isEdit ? 'Mettre a jour' : 'Creer') }}
        </button>
        <button
          class="px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-white/5 rounded-md hover:bg-gray-200 dark:hover:bg-gray-700 inline-flex items-center gap-1.5"
          title="Convertir tous les accents en entites HTML"
          @click="encodeAllEntities"
        >
          <span class="font-mono font-semibold">&amp;</span>
          Encoder accents
        </button>
        <button
          class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700"
          @click="$router.push('/install-guides-admin')"
        >
          Annuler
        </button>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { installGuidesAdminApi } from '@/api/install-guides'
import { useToast } from '@/composables/useToast'
import { toErrorMessage } from '@/utils/error'
import PageBreadcrumb from '@/components/common/PageBreadcrumb.vue'
import WysiwygEditor from '@/components/shared/WysiwygEditor.vue'
import StepBuilder from '@/components/install-guides/StepBuilder.vue'
import PrimeIconPicker from '@/components/shared/PrimeIconPicker.vue'
import ColorClassPicker from '@/components/shared/ColorClassPicker.vue'
import type { ConfigStep, ConfigStepTable, InstallConfig } from '@/types/install-guide'
import { encodeHtmlEntities, encodeTextEntities } from '@/utils/htmlEntities'

const route = useRoute()
const router = useRouter()
const toast = useToast()

const loading = ref(false)
const submitting = ref(false)
const isEdit = computed(() => !!route.params.id)
const dragOverImport = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

const form = ref({
  slug: '',
  label: '',
  description: '',
  icon: '',
  color: '',
  display_order: 0,
  is_active: true,
})

const steps = ref<(ConfigStep & { table?: ConfigStepTable[] })[]>([])

onMounted(async () => {
  if (isEdit.value) {
    loading.value = true
    try {
      const c = await installGuidesAdminApi.getConfig(Number(route.params.id))
      form.value = {
        slug: c.slug,
        label: c.label,
        description: c.description,
        icon: c.icon,
        color: c.color,
        display_order: c.display_order,
        is_active: c.is_active,
      }
      steps.value = (c.content || []).map(s => ({ ...s }))
    } catch {
      toast.error('Configuration introuvable')
      router.push('/install-guides-admin')
    } finally {
      loading.value = false
    }
  }
})

// Fields that must NOT be entity-encoded.
const skipEncodingKeys = new Set(['slug', 'icon', 'color', 'display_order', 'is_active', 'codeField', 'code', 'image', 'link', 'src', 'url'])

function encodeAllEntities() {
  if (form.value.label) form.value.label = encodeTextEntities(form.value.label)
  if (form.value.description) form.value.description = encodeHtmlEntities(form.value.description)

  steps.value = steps.value.map(step => {
    const newStep: ConfigStep = { ...step }
    for (const [k, v] of Object.entries(step)) {
      if (skipEncodingKeys.has(k) || typeof v !== 'string') continue
      const isHtmlish = /<[a-zA-Z\/!]/.test(v)
      ;(newStep as unknown as Record<string, unknown>)[k] = isHtmlish ? encodeHtmlEntities(v) : encodeTextEntities(v)
    }
    // Encode table cells (field/value)
    if (Array.isArray(step.table)) {
      newStep.table = step.table.map((row: ConfigStepTable) => ({
        field: row.field ? encodeTextEntities(row.field) : row.field,
        value: row.value, // values often contain URLs/templates → leave as-is
      }))
    }
    return newStep
  })
  toast.success('Accents convertis en entites HTML')
}

async function handleSave() {
  if (!form.value.slug || !form.value.label) {
    toast.error('Slug et label sont obligatoires')
    return
  }

  submitting.value = true
  try {
    const payload = { ...form.value, content: steps.value }
    if (isEdit.value) {
      await installGuidesAdminApi.updateConfig(Number(route.params.id), payload)
      toast.success('Configuration mise a jour')
    } else {
      await installGuidesAdminApi.createConfig(payload)
      toast.success('Configuration creee')
    }
    router.push('/install-guides-admin')
  } catch (err: unknown) {
    toast.error(toErrorMessage(err, 'Erreur lors de l\'enregistrement'))
  } finally {
    submitting.value = false
  }
}

function handleExport() {
  const data = { ...form.value, content: steps.value }
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `config-${form.value.slug || 'new'}.json`
  a.click()
  URL.revokeObjectURL(url)
}

type ImportedConfig = Partial<Omit<InstallConfig, 'content'>> & { content?: ConfigStep[] }

function applyImportData(data: ImportedConfig) {
  if (data.slug) form.value.slug = data.slug
  if (data.label) form.value.label = data.label
  if (data.description !== undefined) form.value.description = data.description
  if (data.icon) form.value.icon = data.icon
  if (data.color) form.value.color = data.color
  if (data.content) {
    steps.value = data.content.map((s) => ({ ...s }))
  }
  toast.success('Donnees importees')
}

function handleImport(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  file.text().then(text => {
    try { applyImportData(JSON.parse(text)) } catch { toast.error('JSON invalide') }
  })
  if (fileInput.value) fileInput.value.value = ''
}

function handleDropImport(e: DragEvent) {
  dragOverImport.value = false
  const file = e.dataTransfer?.files?.[0]
  if (!file) return
  file.text().then(text => {
    try { applyImportData(JSON.parse(text)) } catch { toast.error('JSON invalide') }
  })
}
</script>
