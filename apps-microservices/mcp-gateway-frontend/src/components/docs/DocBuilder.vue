<template>
  <div class="flex gap-4 min-h-[500px] w-full min-w-0">
    <!-- Left: Element palette -->
    <div class="w-40 shrink-0">
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
      <p class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-3">Contenu</p>
      <div
        ref="canvasRef"
        class="min-h-[400px] rounded-lg border-2 border-dashed transition-colors"
        :class="dragOverCanvas
          ? 'border-brand-400 bg-brand-50/50 dark:bg-brand-500/5'
          : 'border-gray-300 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-800/30'"
        @dragover.prevent="dragOverCanvas = true"
        @dragleave="dragOverCanvas = false"
        @drop="onCanvasDrop"
      >
        <!-- Empty state -->
        <div v-if="elements.length === 0" class="flex flex-col items-center justify-center h-full py-16 text-gray-400 dark:text-gray-500">
          <i class="pi pi-inbox text-3xl mb-3" />
          <p class="text-sm">Glissez des elements ici</p>
        </div>

        <!-- Elements list -->
        <div v-else class="p-3 space-y-2">
          <div
            v-for="(el, index) in elements"
            :key="el.id"
            class="group relative rounded-lg border transition-all cursor-pointer"
            :class="selectedId === el.id
              ? 'border-brand-500 bg-white dark:bg-gray-900 shadow-sm ring-2 ring-brand-500/20'
              : 'border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 hover:border-gray-300 dark:hover:border-gray-700'"
            draggable="true"
            @dragstart="onElementDragStart($event, index)"
            @dragover.prevent="onElementDragOver($event, index)"
            @drop.stop="onElementDrop($event, index)"
            @click="selectedId = el.id"
          >
            <!-- Element header bar -->
            <div class="flex items-center justify-between px-3 py-2 border-b border-gray-100 dark:border-gray-800">
              <div class="flex items-center gap-2">
                <i class="pi pi-bars text-xs text-gray-400 cursor-grab" />
                <i :class="getElementMeta(el.type).icon" class="text-xs text-brand-400" />
                <span class="text-xs font-medium text-gray-500 dark:text-gray-400">{{ getElementMeta(el.type).label }}</span>
              </div>
              <button
                type="button"
                class="p-1 rounded opacity-0 group-hover:opacity-100 text-red-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 transition-opacity"
                @click.stop="removeElement(index)"
              >
                <i class="pi pi-times text-xs" />
              </button>
            </div>

            <!-- Element preview -->
            <div class="px-3 py-2">
              <template v-if="el.type === 'step'">
                <p class="text-sm font-medium text-gray-800 dark:text-gray-200 truncate">
                  {{ el.props.title || 'Etape sans titre' }}
                </p>
                <p v-if="el.props.description" class="text-xs text-gray-500 dark:text-gray-400 truncate mt-0.5">
                  {{ el.props.description }}
                </p>
              </template>
              <template v-else-if="el.type === 'text'">
                <p class="text-sm text-gray-700 dark:text-gray-300 line-clamp-2">
                  {{ el.props.content || 'Bloc de texte vide' }}
                </p>
              </template>
              <template v-else-if="el.type === 'image'">
                <div class="flex items-center gap-2">
                  <img v-if="el.props.src" :src="el.props.src" class="w-12 h-8 object-cover rounded" />
                  <i v-else class="pi pi-image text-xl text-gray-300 dark:text-gray-600" />
                  <span class="text-xs text-gray-500 dark:text-gray-400 truncate">{{ el.props.src || 'Aucune image' }}</span>
                </div>
              </template>
              <template v-else-if="el.type === 'divider'">
                <hr class="border-gray-200 dark:border-gray-700" />
              </template>
              <template v-else-if="el.type === 'link'">
                <div class="flex items-center gap-2">
                  <i class="pi pi-external-link text-xs text-brand-400" />
                  <span class="text-sm text-brand-500 truncate">{{ el.props.url || 'Aucun lien' }}</span>
                </div>
              </template>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Right: Properties panel -->
    <div class="w-56 shrink-0">
      <p class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-3">Proprietes</p>
      <div v-if="!selectedElement" class="text-sm text-gray-400 dark:text-gray-500 italic py-8 text-center">
        Selectionnez un element
      </div>
      <div v-else class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-4 space-y-3">
        <div class="flex items-center justify-between mb-1">
          <span class="text-xs font-semibold text-gray-600 dark:text-gray-300">
            {{ getElementMeta(selectedElement.type).label }}
          </span>
          <button
            type="button"
            class="text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
            @click="selectedId = null"
          >
            <i class="pi pi-times" />
          </button>
        </div>

        <!-- Step properties -->
        <template v-if="selectedElement.type === 'step'">
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Titre</label>
            <input v-model="selectedElement.props.title" type="text" placeholder="Titre de l'etape" class="w-full rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-800 placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30" />
          </div>
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Description</label>
            <textarea v-model="selectedElement.props.description" rows="3" placeholder="Description" class="w-full rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-800 placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30" />
          </div>
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Lien</label>
            <input v-model="selectedElement.props.link" type="url" placeholder="https://..." class="w-full rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-800 placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30" />
          </div>
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Image</label>
            <input v-model="selectedElement.props.image" type="text" placeholder="URL de l'image" class="w-full rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-800 placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30" />
          </div>
        </template>

        <!-- Text properties -->
        <template v-else-if="selectedElement.type === 'text'">
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Contenu</label>
            <textarea v-model="selectedElement.props.content" rows="5" placeholder="Texte libre..." class="w-full rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-800 placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30" />
          </div>
        </template>

        <!-- Image properties -->
        <template v-else-if="selectedElement.type === 'image'">
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">URL</label>
            <input v-model="selectedElement.props.src" type="text" placeholder="https://... ou /uploads/..." class="w-full rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-800 placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30" />
          </div>
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Texte alternatif</label>
            <input v-model="selectedElement.props.alt" type="text" placeholder="Description de l'image" class="w-full rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-800 placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30" />
          </div>
          <div v-if="selectedElement.props.src" class="mt-2">
            <img :src="selectedElement.props.src" :alt="selectedElement.props.alt" class="w-full rounded border border-gray-200 dark:border-gray-700" />
          </div>
        </template>

        <!-- Link properties -->
        <template v-else-if="selectedElement.type === 'link'">
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">URL</label>
            <input v-model="selectedElement.props.url" type="url" placeholder="https://..." class="w-full rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-800 placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30" />
          </div>
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Libelle</label>
            <input v-model="selectedElement.props.label" type="text" placeholder="Texte du lien" class="w-full rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-800 placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30" />
          </div>
        </template>

        <!-- Divider has no properties -->
        <template v-else-if="selectedElement.type === 'divider'">
          <p class="text-xs text-gray-400 dark:text-gray-500 italic">Aucune propriete</p>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

export type DocElementType = 'step' | 'text' | 'image' | 'divider' | 'link'

export interface DocElement {
  id: string
  type: DocElementType
  props: Record<string, string>
}

const props = defineProps<{
  modelValue: DocElement[]
}>()

const emit = defineEmits<{
  'update:modelValue': [value: DocElement[]]
}>()

const elements = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const selectedId = ref<string | null>(null)
const dragOverCanvas = ref(false)
const dragElementIndex = ref<number | null>(null)
const canvasRef = ref<HTMLElement | null>(null)

const paletteElements = [
  { type: 'step' as DocElementType, label: 'Etape', icon: 'pi pi-check-circle' },
  { type: 'text' as DocElementType, label: 'Texte', icon: 'pi pi-align-left' },
  { type: 'image' as DocElementType, label: 'Image', icon: 'pi pi-image' },
  { type: 'link' as DocElementType, label: 'Lien', icon: 'pi pi-external-link' },
  { type: 'divider' as DocElementType, label: 'Separateur', icon: 'pi pi-minus' },
]

function getElementMeta(type: DocElementType) {
  return paletteElements.find(e => e.type === type) || { label: type, icon: 'pi pi-question' }
}

const selectedElement = computed(() => {
  if (!selectedId.value) return null
  return elements.value.find(e => e.id === selectedId.value) || null
})

function generateId() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 7)
}

function createDefaultProps(type: DocElementType): Record<string, string> {
  switch (type) {
    case 'step': return { title: '', description: '', link: '', image: '' }
    case 'text': return { content: '' }
    case 'image': return { src: '', alt: '' }
    case 'link': return { url: '', label: '' }
    case 'divider': return {}
  }
}

function onPaletteDragStart(event: DragEvent, type: DocElementType) {
  event.dataTransfer!.setData('palette-type', type)
  event.dataTransfer!.effectAllowed = 'copy'
  dragElementIndex.value = null
}

function onElementDragStart(event: DragEvent, index: number) {
  event.dataTransfer!.setData('move-index', String(index))
  event.dataTransfer!.effectAllowed = 'move'
  dragElementIndex.value = index
}

function onElementDragOver(event: DragEvent, _index: number) {
  if (dragElementIndex.value === null) return
  event.dataTransfer!.dropEffect = 'move'
}

function onElementDrop(event: DragEvent, targetIndex: number) {
  const moveIndex = event.dataTransfer!.getData('move-index')
  if (moveIndex !== '') {
    const from = parseInt(moveIndex)
    if (from === targetIndex) return
    const copy = [...elements.value]
    const [moved] = copy.splice(from, 1)
    copy.splice(targetIndex, 0, moved!)
    elements.value = copy
  }
  dragElementIndex.value = null
}

function onCanvasDrop(event: DragEvent) {
  dragOverCanvas.value = false
  const paletteType = event.dataTransfer!.getData('palette-type') as DocElementType
  if (paletteType) {
    const newEl: DocElement = {
      id: generateId(),
      type: paletteType,
      props: createDefaultProps(paletteType)
    }
    elements.value = [...elements.value, newEl]
    selectedId.value = newEl.id
    return
  }
  // Move within canvas is handled by onElementDrop
}

function removeElement(index: number) {
  const el = elements.value[index]
  if (el && selectedId.value === el.id) {
    selectedId.value = null
  }
  const copy = [...elements.value]
  copy.splice(index, 1)
  elements.value = copy
}
</script>

