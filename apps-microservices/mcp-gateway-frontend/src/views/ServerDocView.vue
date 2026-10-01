<template>
  <div>
    <!-- Page header -->
    <div class="mb-6 flex items-center gap-4">
      <button
        type="button"
        class="inline-flex items-center gap-1.5 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
        @click="router.push('/docs-admin')"
      >
        <i class="pi pi-arrow-left text-xs" />
        Retour
      </button>
      <h1 class="text-2xl font-bold text-gray-900 dark:text-white">Documentation</h1>
      <span v-if="serverName" class="text-sm text-gray-500 dark:text-gray-400">— {{ serverName }}</span>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex items-center justify-center py-20">
      <i class="pi pi-spinner pi-spin text-2xl text-gray-400 dark:text-gray-500" />
    </div>

    <template v-else>
      <!-- Slug + Description -->
      <div class="bg-white dark:bg-gray-900 rounded-lg shadow-theme-xs border border-gray-200 dark:border-gray-800 p-5 mb-6">
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <!-- Doc slug -->
          <div>
            <label for="doc-slug" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Slug (URL)
            </label>
            <div class="flex items-center gap-2">
              <span class="text-sm text-gray-400 dark:text-gray-500 shrink-0">/docs/</span>
              <input
                id="doc-slug"
                v-model="form.doc_slug"
                type="text"
                class="h-10 min-w-0 flex-1 rounded-lg border border-gray-300 bg-transparent px-3 py-2 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
                placeholder="mon-serveur"
              />
            </div>
            <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">Laisser vide pour ne pas publier</p>
          </div>

          <!-- Auth type -->
          <div>
            <label for="auth-type" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Type d'authentification
            </label>
            <input
              id="auth-type"
              v-model="form.authType"
              type="text"
              class="h-10 w-full rounded-lg border border-gray-300 bg-transparent px-3 py-2 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
              placeholder="OAuth2, Cle API, Service Account..."
            />
          </div>
        </div>

        <!-- Description (full width) -->
        <div class="mt-4">
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Description
          </label>
          <WysiwygEditor
            v-model="form.doc_description"
            placeholder="Description affichee sur la page documentation..."
          />
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
              @click="($refs.fileInput as HTMLInputElement).click()"
            >
              <i class="pi pi-upload text-xs" />
              <span class="text-xs font-medium">Glisser un fichier JSON ici ou cliquer pour importer</span>
              <input ref="fileInput" type="file" accept=".json" class="hidden" @change="handleImport" />
            </div>
          </div>
          <p v-if="importError" class="text-xs text-error-500 dark:text-error-400 mt-2">{{ importError }}</p>
        </div>
      </div>

      <!-- Doc Builder -->
      <div class="mb-6 overflow-x-auto">
        <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">Guide de configuration</h2>
        <DocBuilder v-model="builderElements" />
      </div>

      <!-- Spacer for sticky bar -->
      <div class="h-20" />
    </template>

    <!-- Sticky bottom bar -->
    <div
      v-if="!loading"
      class="fixed bottom-0 right-0 z-40 border-t border-gray-200 dark:border-gray-800 bg-white/95 dark:bg-gray-900/95 backdrop-blur-sm shadow-lg transition-all duration-300 ease-in-out"
      :class="[sidebarExpanded || sidebarHovered ? 'lg:left-[290px]' : 'lg:left-[90px]', 'left-0']"
    >
      <div class="max-w-screen-2xl mx-auto px-4 md:px-6 py-3 flex items-center justify-between">
        <div class="flex items-center gap-3">
          <button
            v-if="hasDoc"
            type="button"
            class="px-4 py-2 text-sm font-medium text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-500/10 rounded-md hover:bg-red-100 dark:hover:bg-red-500/20"
            @click="handleDelete"
          >
            Retirer de /docs
          </button>
          <router-link
            v-if="form.doc_slug"
            :to="`/docs/${form.doc_slug}`"
            target="_blank"
            class="text-xs text-brand-500 hover:text-brand-600 dark:text-brand-400 inline-flex items-center gap-1"
          >
            Apercu : /docs/{{ form.doc_slug }}
            <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" /></svg>
          </router-link>
        </div>
        <div class="flex gap-3">
          <button
            type="button"
            class="px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-white/5 rounded-md hover:bg-gray-200 dark:hover:bg-gray-700 inline-flex items-center gap-1.5"
            title="Convertir tous les accents en entites HTML (description + tous les elements)"
            @click="encodeAllEntities"
          >
            <span class="font-mono font-semibold">&amp;</span>
            Encoder accents
          </button>
          <button
            type="button"
            class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-white/5 rounded-md hover:bg-gray-200 dark:hover:bg-gray-700"
            @click="router.push('/docs-admin')"
          >
            Annuler
          </button>
          <button
            type="button"
            class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600 disabled:opacity-50"
            :disabled="submitting"
            @click="handleSave"
          >
            <i v-if="submitting" class="pi pi-spinner pi-spin mr-1" />
            Enregistrer
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useServersStore } from '@/stores/servers'
import { useToast } from '@/composables/useToast'
import { toErrorMessage } from '@/utils/error'
import { serversApi } from '@/api/servers'
import DocBuilder from '@/components/docs/DocBuilder.vue'
import WysiwygEditor from '@/components/shared/WysiwygEditor.vue'
import { useSidebar } from '@/composables/useSidebar'
import type { DocElement } from '@/components/docs/DocBuilder.vue'
import type { DocConfigGuide, DocConfigGuideStep } from '@/types/server'
import { encodeHtmlEntities, encodeTextEntities } from '@/utils/htmlEntities'

const route = useRoute()
const router = useRouter()
const serversStore = useServersStore()
const toast = useToast()

const { isExpanded: sidebarExpanded, isHovered: sidebarHovered } = useSidebar()

const serverId = route.params.id as string
const serverName = ref('')
const loading = ref(true)
const submitting = ref(false)
const hasDoc = ref(false)

const importError = ref('')
const dragOverImport = ref(false)

const form = reactive({
  doc_slug: '',
  doc_description: '',
  authType: ''
})

const builderElements = ref<DocElement[]>([])

// Fields whose values must NOT be entity-encoded (URLs, slugs, image paths, CSS classes, etc.)
const skipEncodingProps = new Set(['link', 'image', 'src', 'url', 'cssClass', 'class'])

function encodeAllEntities() {
  // 1) Encode the rich-text description (HTML aware).
  if (form.doc_description) {
    form.doc_description = encodeHtmlEntities(form.doc_description)
  }
  // 2) Walk each builder element and encode its props.
  builderElements.value = builderElements.value.map(el => {
    const newProps: Record<string, string> = {}
    for (const [k, v] of Object.entries(el.props)) {
      if (skipEncodingProps.has(k) || typeof v !== 'string') {
        newProps[k] = v as string
        continue
      }
      // Step descriptions / text content are HTML-ish; titles/labels are plain text.
      const isHtmlish = /<[a-zA-Z\/!]/.test(v)
      newProps[k] = isHtmlish ? encodeHtmlEntities(v) : encodeTextEntities(v)
    }
    return { ...el, props: newProps }
  })
  toast.success('Accents convertis en entites HTML')
}

// Convert builder elements → backend config guide
function elementsToConfigGuide(): DocConfigGuide {
  const allEntries: DocConfigGuideStep[] = builderElements.value
    .filter(el => {
      if (el.type === 'step') return el.props.title || el.props.description
      if (el.type === 'text') return !!el.props.content
      if (el.type === 'image') return !!el.props.src
      if (el.type === 'link') return !!el.props.url
      if (el.type === 'divider') return true
      return false
    })
    .map(el => {
      if (el.type === 'step') {
        return {
          type: 'step',
          title: el.props.title || '',
          description: el.props.description || '',
          ...(el.props.link ? { link: el.props.link } : {}),
          ...(el.props.image ? { image: el.props.image } : {})
        }
      }
      if (el.type === 'text') {
        return { type: 'text', title: '', description: el.props.content || '' }
      }
      if (el.type === 'image') {
        return { type: 'image', title: el.props.alt || '', description: '', image: el.props.src || '' }
      }
      if (el.type === 'link') {
        return { type: 'link', title: el.props.label || el.props.url || '', description: '', link: el.props.url || '' }
      }
      if (el.type === 'divider') {
        return { type: 'divider', title: '', description: '' }
      }
      return { type: el.type, title: '', description: '' }
    })

  return { authType: form.authType, steps: allEntries }
}

// Convert backend steps back to builder elements (supports mixed types)
function stepsToElements(steps: DocConfigGuideStep[]): DocElement[] {
  return steps.map((step, i): DocElement => {
    const id = Date.now().toString(36) + i + Math.random().toString(36).slice(2, 5)
    const type = (step.type || 'step') as DocElement['type']

    switch (type) {
      case 'text':
        return { id, type, props: { content: step.description || '' } }
      case 'image':
        return { id, type, props: { src: step.image || '', alt: step.title || '' } }
      case 'link':
        return { id, type, props: { url: step.link || '', label: step.title || '' } }
      case 'divider':
        return { id, type, props: {} }
      default:
        return { id, type: 'step', props: { title: step.title || '', description: step.description || '', link: step.link || '', image: step.image || '' } }
    }
  })
}

function handleExport() {
  const data = {
    doc_slug: form.doc_slug,
    doc_description: form.doc_description,
    doc_config_guide: elementsToConfigGuide()
  }
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `doc-${form.doc_slug || 'server'}.json`
  a.click()
  URL.revokeObjectURL(url)
}

function handleDropImport(event: DragEvent) {
  dragOverImport.value = false
  const file = event.dataTransfer?.files?.[0]
  if (!file || !file.name.endsWith('.json')) {
    importError.value = 'Fichier JSON attendu'
    return
  }
  processImportFile(file)
}

function handleImport(event: Event) {
  importError.value = ''
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  processImportFile(file)
  input.value = ''
}

function processImportFile(file: File) {
  importError.value = ''
  const reader = new FileReader()
  reader.onload = () => {
    try {
      const data = JSON.parse(reader.result as string)
      if (data.doc_slug !== undefined) form.doc_slug = data.doc_slug || ''
      if (data.doc_description !== undefined) form.doc_description = data.doc_description || ''
      if (data.doc_config_guide) {
        form.authType = data.doc_config_guide.authType || ''
        builderElements.value = stepsToElements(data.doc_config_guide.steps || [])
      }
      toast.success('Documentation importee')
    } catch {
      importError.value = 'Fichier JSON invalide'
    }
  }
  reader.readAsText(file)
}

onMounted(async () => {
  try {
    const server = await serversApi.get(serverId)
    serverName.value = server.name
    form.doc_slug = server.doc_slug || ''
    form.doc_description = server.doc_description || ''
    hasDoc.value = !!server.doc_slug

    if (server.doc_config_guide) {
      form.authType = server.doc_config_guide.authType || ''
      builderElements.value = stepsToElements(server.doc_config_guide.steps || [])
    }
  } catch (err) {
    toast.error(err instanceof Error ? err.message : 'Erreur lors du chargement')
    router.push('/docs-admin')
  } finally {
    loading.value = false
  }
})

async function handleSave() {
  submitting.value = true
  try {
    await serversStore.updateServer(serverId, {
      doc_slug: form.doc_slug || '',
      doc_description: form.doc_description || '',
      doc_config_guide: elementsToConfigGuide()
    })
    toast.success('Documentation enregistree')
    router.push('/docs-admin')
  } catch (err: unknown) {
    toast.error(toErrorMessage(err, 'Erreur lors de l\'enregistrement'))
  } finally {
    submitting.value = false
  }
}

async function handleDelete() {
  submitting.value = true
  try {
    await serversStore.updateServer(serverId, {
      doc_slug: '',
      doc_description: '',
      doc_config_guide: { authType: '', steps: [] }
    })
    toast.success('Documentation retiree')
    router.push('/docs-admin')
  } catch (err) {
    toast.error(err instanceof Error ? err.message : 'Erreur')
  } finally {
    submitting.value = false
  }
}
</script>
