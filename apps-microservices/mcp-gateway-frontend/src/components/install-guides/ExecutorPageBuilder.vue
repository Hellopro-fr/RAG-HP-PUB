<template>
  <div class="flex gap-4 min-h-[500px] w-full min-w-0">
    <!-- Left: Element palette -->
    <div class="w-44 shrink-0">
      <p class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-3">Elements</p>
      <div class="space-y-2">
        <button
          v-for="el in paletteElements"
          :key="el.type"
          type="button"
          class="w-full flex items-center gap-2.5 px-3 py-2.5 text-sm text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg hover:border-brand-300 dark:hover:border-brand-600 hover:shadow-sm transition cursor-grab active:cursor-grabbing"
          draggable="true"
          @dragstart="onPaletteDragStart($event, el.type)"
        >
          <i :class="el.icon" class="text-sm text-brand-500" />
          <span>{{ el.label }}</span>
        </button>
      </div>
    </div>

    <!-- Center: Canvas -->
    <div class="flex-1 min-w-0">
      <p class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-3">Contenu de la page</p>
      <div
        ref="canvasRef"
        class="min-h-[450px] rounded-lg border-2 border-dashed transition-colors"
        :class="dragOverCanvas
          ? 'border-brand-400 bg-brand-50/50 dark:bg-brand-500/5'
          : 'border-gray-300 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-800/30'"
        @dragover.prevent="dragOverCanvas = true"
        @dragleave="dragOverCanvas = false"
        @drop.prevent="onCanvasDrop"
      >
        <div v-if="elements.length === 0" class="flex flex-col items-center justify-center h-full py-16 text-gray-400 dark:text-gray-500">
          <i class="pi pi-inbox text-3xl mb-3" />
          <p class="text-sm">Glissez des elements ici</p>
        </div>

        <div v-else class="p-3 space-y-2">
          <div
            v-for="(el, index) in elements"
            :key="el.id"
            class="group relative rounded-lg border transition-all cursor-pointer"
            :class="[
              selectedIndex === index
                ? 'border-brand-500 bg-white dark:bg-gray-900 shadow-sm ring-2 ring-brand-500/20'
                : 'border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 hover:border-gray-300 dark:hover:border-gray-700',
              dragElementIndex === index ? 'opacity-40' : ''
            ]"
            draggable="true"
            @dragstart="onElementDragStart($event, index)"
            @dragover.prevent="onElementDragOver($event, index)"
            @dragleave="onElementDragLeave($event, index)"
            @drop.stop.prevent="onElementDrop($event, index)"
            @click="selectedIndex = index"
          >
            <!-- Drop indicator: line above -->
            <div
              v-if="dropTargetIndex === index && dropPosition === 'before' && dragElementIndex !== index"
              class="absolute -top-1 left-0 right-0 h-1 rounded-full bg-brand-500 pointer-events-none z-10"
            />
            <!-- Drop indicator: line below -->
            <div
              v-if="dropTargetIndex === index && dropPosition === 'after' && dragElementIndex !== index"
              class="absolute -bottom-1 left-0 right-0 h-1 rounded-full bg-brand-500 pointer-events-none z-10"
            />
            <!-- Header bar -->
            <div class="flex items-center justify-between px-3 py-2 border-b border-gray-100 dark:border-gray-800">
              <div class="flex items-center gap-2">
                <i class="pi pi-bars text-xs text-gray-400 cursor-grab" />
                <i :class="getMeta(el.type).icon" class="text-xs text-brand-400" />
                <span class="text-xs font-medium text-gray-500 dark:text-gray-400">{{ getMeta(el.type).label }}</span>
              </div>
              <button
                type="button"
                class="p-1 rounded opacity-0 group-hover:opacity-100 text-red-400 hover:text-red-500 transition-opacity"
                @click.stop="removeElement(index)"
              >
                <i class="pi pi-times text-xs" />
              </button>
            </div>

            <!-- Preview -->
            <div class="px-3 py-2">
              <!-- OS Install -->
              <template v-if="el.type === 'os-install'">
                <div class="flex items-center gap-2">
                  <span class="text-xs text-gray-500">{{ countOsOptions(el.props.install) }} options</span>
                  <span v-for="os in ['windows', 'linux', 'macos']" :key="os" class="text-xs px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-500">
                    {{ os }} ({{ (el.props.install?.[os] || []).length }})
                  </span>
                </div>
              </template>
              <!-- Verify -->
              <template v-else-if="el.type === 'verify'">
                <p class="text-xs text-gray-500 font-mono truncate">{{ el.props.code || 'Aucune commande' }}</p>
              </template>
              <!-- MCP Config — content from the top-level "Configuration MCP (JSON)" field -->
              <template v-else-if="el.type === 'mcp-config'">
                <p class="text-xs text-blue-600 dark:text-blue-400 italic truncate">
                  <i class="pi pi-link text-[10px] mr-1" />
                  Li&eacute; au champ Configuration MCP (JSON) du formulaire
                </p>
              </template>
              <!-- CLI Command -->
              <template v-else-if="el.type === 'cli-command'">
                <p class="text-xs text-gray-500 font-mono truncate">{{ el.props.code || 'Aucune commande' }}</p>
              </template>
              <!-- Note -->
              <template v-else-if="el.type === 'note'">
                <div class="flex items-center gap-2">
                  <span class="text-xs font-semibold text-gray-600 dark:text-gray-400">{{ el.props.label || 'Note' }}</span>
                  <span class="text-xs text-gray-400 truncate">{{ stripHtml(el.props.text || '') }}</span>
                </div>
              </template>
              <!-- Text -->
              <template v-else-if="el.type === 'text'">
                <p class="text-xs text-gray-500 truncate">{{ stripHtml(el.props.content || 'Texte vide') }}</p>
              </template>
              <!-- Divider -->
              <template v-else-if="el.type === 'divider'">
                <hr class="border-gray-200 dark:border-gray-700" />
              </template>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Right: Properties panel -->
    <div class="w-64 shrink-0">
      <p class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-3">Proprietes</p>
      <div v-if="selectedIndex === null || !selectedElement" class="text-sm text-gray-400 dark:text-gray-500 italic py-8 text-center">
        Selectionnez un element
      </div>
      <div v-else class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-4 space-y-3 max-h-[600px] overflow-y-auto">
        <div class="flex items-center justify-between mb-1">
          <span class="text-xs font-semibold text-gray-600 dark:text-gray-300">{{ getMeta(selectedElement.type).label }}</span>
          <button type="button" class="text-xs text-gray-400 hover:text-gray-600" @click="selectedIndex = null">
            <i class="pi pi-times" />
          </button>
        </div>

        <!-- OS Install properties -->
        <template v-if="selectedElement.type === 'os-install'">
          <p class="text-xs text-gray-500 dark:text-gray-400 mb-2">Editez les options dans le panneau ci-dessous.</p>
          <InstallOptionsBuilder v-model="selectedElement.props.install" />
        </template>

        <!-- Verify properties -->
        <template v-else-if="selectedElement.type === 'verify'">
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Titre</label>
            <input v-model="selectedElement.props.title" type="text" placeholder="Verification" class="w-full rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm dark:border-gray-700 dark:bg-gray-900 dark:text-white/90" />
          </div>
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Commande</label>
            <textarea v-model="selectedElement.props.code" rows="3" class="w-full rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-mono dark:border-gray-700 dark:bg-gray-900 dark:text-white/90" />
          </div>
        </template>

        <!-- MCP Config properties — content is sourced from the top-level "Configuration MCP (JSON)" field on the executor form -->
        <template v-else-if="selectedElement.type === 'mcp-config'">
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Titre</label>
            <input v-model="selectedElement.props.title" type="text" placeholder="Configuration MCP" class="w-full rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm dark:border-gray-700 dark:bg-gray-900 dark:text-white/90" />
          </div>
          <div class="rounded-md border border-blue-200 bg-blue-50 dark:border-blue-500/30 dark:bg-blue-500/10 p-2 text-[11px] leading-snug text-blue-800 dark:text-blue-300 break-words">
            <div class="flex items-start gap-1.5 font-medium">
              <i class="pi pi-info-circle shrink-0 mt-0.5" />
              <span class="min-w-0">Li&eacute; au champ &laquo;&nbsp;Configuration MCP (JSON)&nbsp;&raquo; du formulaire.</span>
            </div>
            <p class="mt-1 text-blue-700 dark:text-blue-300/80">
              &Eacute;ditez le template depuis le formulaire, pas ici.
            </p>
          </div>
        </template>

        <!-- CLI Command properties -->
        <template v-else-if="selectedElement.type === 'cli-command'">
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Titre</label>
            <input v-model="selectedElement.props.title" type="text" placeholder="Commande Claude Code" class="w-full rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm dark:border-gray-700 dark:bg-gray-900 dark:text-white/90" />
          </div>
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Commande</label>
            <textarea v-model="selectedElement.props.code" rows="3" class="w-full rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-mono dark:border-gray-700 dark:bg-gray-900 dark:text-white/90" />
          </div>
        </template>

        <!-- Note properties -->
        <template v-else-if="selectedElement.type === 'note'">
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Label</label>
            <input v-model="selectedElement.props.label" type="text" placeholder="Note :" class="w-full rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm dark:border-gray-700 dark:bg-gray-900 dark:text-white/90" />
          </div>
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Texte (HTML)</label>
            <textarea v-model="selectedElement.props.text" rows="3" class="w-full rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm dark:border-gray-700 dark:bg-gray-900 dark:text-white/90" />
          </div>
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">CSS class</label>
            <input v-model="selectedElement.props.cssClass" type="text" placeholder="bg-amber-50 ..." class="w-full rounded-md border border-gray-300 bg-white px-3 py-1.5 text-xs font-mono dark:border-gray-700 dark:bg-gray-900 dark:text-white/90" />
          </div>
        </template>

        <!-- Text properties -->
        <template v-else-if="selectedElement.type === 'text'">
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Contenu (HTML)</label>
            <textarea v-model="selectedElement.props.content" rows="5" class="w-full rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm dark:border-gray-700 dark:bg-gray-900 dark:text-white/90" />
          </div>
        </template>

        <!-- Divider -->
        <template v-else-if="selectedElement.type === 'divider'">
          <p class="text-xs text-gray-400 dark:text-gray-500 italic">Aucune propriete</p>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import InstallOptionsBuilder from './InstallOptionsBuilder.vue'
import type { ExecutorElement, ExecutorElementType, InstallOption } from '@/types/install-guide'

const props = defineProps<{
  modelValue: ExecutorElement[]
}>()

const emit = defineEmits<{
  'update:modelValue': [value: ExecutorElement[]]
}>()

const elements = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const selectedIndex = ref<number | null>(null)
const dragOverCanvas = ref(false)
const dragElementIndex = ref<number | null>(null)
const dropTargetIndex = ref<number | null>(null)
const dropPosition = ref<'before' | 'after'>('before')

const selectedElement = computed(() =>
  selectedIndex.value !== null ? elements.value[selectedIndex.value] || null : null
)

const paletteElements: { type: ExecutorElementType; label: string; icon: string }[] = [
  { type: 'os-install', label: 'Installation OS', icon: 'pi pi-desktop' },
  { type: 'verify', label: 'Verification', icon: 'pi pi-check-circle' },
  { type: 'mcp-config', label: 'Config MCP', icon: 'pi pi-file' },
  { type: 'cli-command', label: 'Commande CLI', icon: 'pi pi-code' },
  { type: 'note', label: 'Note', icon: 'pi pi-info-circle' },
  { type: 'text', label: 'Texte', icon: 'pi pi-align-left' },
  { type: 'divider', label: 'Separateur', icon: 'pi pi-minus' },
]

function getMeta(type: string) {
  return paletteElements.find(e => e.type === type) || { label: type, icon: 'pi pi-question' }
}

function generateId() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 7)
}

function createDefault(type: ExecutorElementType): ExecutorElement {
  const el: ExecutorElement = { id: generateId(), type, props: {} }
  switch (type) {
    case 'os-install':
      el.props = { install: { windows: [], linux: [], macos: [] } }
      break
    case 'verify':
      el.props = { title: 'Verification', code: '' }
      break
    case 'mcp-config':
      el.props = { title: 'Configuration MCP', code: '' }
      break
    case 'cli-command':
      el.props = { title: 'Commande Claude Code', code: '' }
      break
    case 'note':
      el.props = { label: 'Note :', text: '', cssClass: 'bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/30 text-amber-800 dark:text-amber-300' }
      break
    case 'text':
      el.props = { content: '' }
      break
    case 'divider':
      el.props = {}
      break
  }
  return el
}

function countOsOptions(install: Record<string, InstallOption[]> | undefined): number {
  if (!install) return 0
  return Object.values(install).reduce((sum, arr) => sum + (arr?.length || 0), 0)
}

function stripHtml(html: string): string {
  return html.replace(/<[^>]*>/g, '').substring(0, 60)
}

// ── Drag & Drop ────────────────────────────────────────────────────

function onPaletteDragStart(event: DragEvent, type: string) {
  event.dataTransfer!.setData('palette-type', type)
  event.dataTransfer!.effectAllowed = 'copy'
  dragElementIndex.value = null
}

function onElementDragStart(event: DragEvent, index: number) {
  event.dataTransfer!.setData('move-index', String(index))
  event.dataTransfer!.effectAllowed = 'move'
  dragElementIndex.value = index
}

function onElementDragOver(event: DragEvent, index: number) {
  if (dragElementIndex.value === null) return
  event.dataTransfer!.dropEffect = 'move'
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  const isBelow = event.clientY - rect.top > rect.height / 2
  dropTargetIndex.value = index
  dropPosition.value = isBelow ? 'after' : 'before'
}

function onElementDragLeave(event: DragEvent, index: number) {
  const related = event.relatedTarget as Node | null
  const current = event.currentTarget as HTMLElement
  if (related && current.contains(related)) return
  if (dropTargetIndex.value === index) {
    dropTargetIndex.value = null
  }
}

function onElementDrop(event: DragEvent, targetIndex: number) {
  const moveIndex = event.dataTransfer!.getData('move-index')
  if (moveIndex !== '') {
    const from = parseInt(moveIndex)
    let to = dropPosition.value === 'after' ? targetIndex + 1 : targetIndex
    if (from < to) to--
    if (from !== to) {
      const copy = [...elements.value]
      const [moved] = copy.splice(from, 1)
      copy.splice(to, 0, moved!)
      elements.value = copy
      if (selectedIndex.value === from) selectedIndex.value = to
    }
  }
  dragElementIndex.value = null
  dropTargetIndex.value = null
}

function onCanvasDrop(event: DragEvent) {
  dragOverCanvas.value = false
  const paletteType = event.dataTransfer!.getData('palette-type') as ExecutorElementType
  if (paletteType) {
    const newEl = createDefault(paletteType)
    elements.value = [...elements.value, newEl]
    selectedIndex.value = elements.value.length - 1
  }
}

function removeElement(index: number) {
  if (selectedIndex.value === index) selectedIndex.value = null
  else if (selectedIndex.value !== null && selectedIndex.value > index) selectedIndex.value--
  const copy = [...elements.value]
  copy.splice(index, 1)
  elements.value = copy
}
</script>
