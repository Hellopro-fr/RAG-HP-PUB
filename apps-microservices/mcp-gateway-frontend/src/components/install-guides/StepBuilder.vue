<template>
  <div class="flex gap-4 min-h-[400px] w-full min-w-0">
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
      <p class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-3">Etapes</p>
      <div
        ref="canvasRef"
        class="min-h-[350px] rounded-lg border-2 border-dashed transition-colors"
        :class="dragOverCanvas
          ? 'border-brand-400 bg-brand-50/50 dark:bg-brand-500/5'
          : 'border-gray-300 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-800/30'"
        @dragover.prevent="dragOverCanvas = true"
        @dragleave="dragOverCanvas = false"
        @drop="onCanvasDrop"
      >
        <div v-if="steps.length === 0" class="flex flex-col items-center justify-center h-full py-16 text-gray-400 dark:text-gray-500">
          <i class="pi pi-inbox text-3xl mb-3" />
          <p class="text-sm">Glissez des elements ici</p>
        </div>

        <div v-else class="p-3 space-y-2">
          <div
            v-for="(step, index) in steps"
            :key="step._id"
            class="group relative rounded-lg border transition-all cursor-pointer"
            :class="selectedIndex === index
              ? 'border-brand-500 bg-white dark:bg-gray-900 shadow-sm ring-2 ring-brand-500/20'
              : 'border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 hover:border-gray-300 dark:hover:border-gray-700'"
            draggable="true"
            @dragstart="onStepDragStart($event, index)"
            @dragover.prevent="onStepDragOver($event, index)"
            @drop.stop="onStepDrop($event, index)"
            @click="selectedIndex = index"
          >
            <div class="flex items-center justify-between px-3 py-2 border-b border-gray-100 dark:border-gray-800">
              <div class="flex items-center gap-2">
                <i class="pi pi-bars text-xs text-gray-400 cursor-grab" />
                <span class="inline-flex items-center justify-center w-5 h-5 rounded-full bg-brand-500 text-white text-xs font-semibold">{{ index + 1 }}</span>
                <i :class="getStepMeta(step._type).icon" class="text-xs text-brand-400" />
                <span class="text-xs font-medium text-gray-500 dark:text-gray-400">{{ getStepMeta(step._type).label }}</span>
              </div>
              <button
                type="button"
                class="p-1 rounded opacity-0 group-hover:opacity-100 text-red-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 transition-opacity"
                @click.stop="removeStep(index)"
              >
                <i class="pi pi-times text-xs" />
              </button>
            </div>
            <div class="px-3 py-2">
              <p class="text-sm font-medium text-gray-800 dark:text-gray-200 truncate">
                {{ step.title || 'Sans titre' }}
              </p>
              <p v-if="step.description" class="text-xs text-gray-500 dark:text-gray-400 truncate mt-0.5">
                {{ stripHtml(step.description) }}
              </p>
              <div v-if="step.hasExecutorSelector" class="mt-1">
                <span class="inline-flex items-center px-1.5 py-0.5 rounded text-xs bg-purple-100 text-purple-700 dark:bg-purple-500/20 dark:text-purple-300">
                  <i class="pi pi-list text-xs mr-1" /> Selecteur executeur
                </span>
              </div>
              <div v-if="step.code || step.codeField" class="mt-1">
                <span class="inline-flex items-center px-1.5 py-0.5 rounded text-xs bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300 font-mono">
                  {{ step.codeField || step.code?.substring(0, 40) || '' }}
                </span>
              </div>
              <div v-if="step.table && step.table.length" class="mt-1">
                <span class="inline-flex items-center px-1.5 py-0.5 rounded text-xs bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-300">
                  <i class="pi pi-table text-xs mr-1" /> {{ step.table.length }} ligne(s)
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Right: Properties panel -->
    <div class="w-60 shrink-0">
      <p class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-3">Proprietes</p>
      <div v-if="selectedIndex === null" class="text-sm text-gray-400 dark:text-gray-500 italic py-8 text-center">
        Selectionnez une etape
      </div>
      <div v-else-if="selectedStep" class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-4 space-y-3">
        <div class="flex items-center justify-between mb-1">
          <span class="text-xs font-semibold text-gray-600 dark:text-gray-300">
            {{ getStepMeta(selectedStep._type).label }}
          </span>
          <button type="button" class="text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300" @click="selectedIndex = null">
            <i class="pi pi-times" />
          </button>
        </div>

        <!-- Common: title + description -->
        <div>
          <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Titre</label>
          <input v-model="selectedStep.title" type="text" class="w-full rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm dark:border-gray-700 dark:bg-gray-900 dark:text-white/90" />
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Description (HTML)</label>
          <textarea v-model="selectedStep.description" rows="3" class="w-full rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm dark:border-gray-700 dark:bg-gray-900 dark:text-white/90" />
        </div>

        <!-- Step type: code -->
        <template v-if="selectedStep._type === 'step' || selectedStep._type === 'code'">
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Code (optionnel)</label>
            <textarea v-model="selectedStep.code" rows="2" class="w-full rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-mono dark:border-gray-700 dark:bg-gray-900 dark:text-white/90" />
          </div>
        </template>

        <!-- Executor selector -->
        <template v-if="selectedStep._type === 'executor-selector' || selectedStep._type === 'step'">
          <label class="flex items-center gap-2">
            <input v-model="selectedStep.hasExecutorSelector" type="checkbox" class="rounded" />
            <span class="text-xs text-gray-600 dark:text-gray-400">Selecteur d'executeur</span>
          </label>
          <div v-if="selectedStep.hasExecutorSelector">
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Champ code executeur</label>
            <select v-model="selectedStep.codeField" class="w-full rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm dark:border-gray-700 dark:bg-gray-900 dark:text-white/90">
              <option value="">Aucun</option>
              <option value="cli_add_cmd">cli_add_cmd (Claude Code)</option>
              <option value="mcp_config">mcp_config (JSON config)</option>
            </select>
          </div>
        </template>

        <!-- Table -->
        <template v-if="selectedStep._type === 'table' || selectedStep._type === 'step'">
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Tableau</label>
            <div v-if="selectedStep.table && selectedStep.table.length" class="space-y-2 mb-2">
              <div
                v-for="(row, j) in selectedStep.table"
                :key="j"
                class="rounded border border-gray-200 dark:border-gray-700 p-2 space-y-1.5"
              >
                <div class="flex items-center justify-between">
                  <span class="text-[10px] font-medium text-gray-400">Ligne {{ j + 1 }}</span>
                  <button type="button" class="p-0.5 text-gray-400 hover:text-error-500" @click="selectedStep.table!.splice(j, 1)">
                    <i class="pi pi-times text-[10px]" />
                  </button>
                </div>
                <input v-model="row.field" type="text" placeholder="Champ (ex: Server URL)" class="w-full text-xs border border-gray-300 dark:border-gray-600 rounded px-2 py-1 bg-white dark:bg-gray-800 dark:text-gray-200" />
                <input v-model="row.value" type="text" placeholder="Valeur" class="w-full text-xs border border-gray-300 dark:border-gray-600 rounded px-2 py-1 bg-white dark:bg-gray-800 dark:text-gray-200" />
              </div>
            </div>
            <button
              type="button"
              class="w-full flex items-center justify-center gap-1 px-2 py-1.5 text-xs font-medium text-brand-500 border border-dashed border-brand-300 dark:border-brand-600 rounded hover:bg-brand-50 dark:hover:bg-brand-500/10 transition"
              @click="if (!selectedStep.table) selectedStep.table = []; selectedStep.table.push({ field: '', value: '' })"
            >
              <i class="pi pi-plus text-[10px]" />
              Ajouter ligne
            </button>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { ConfigStep, ConfigStepTable } from '@/types/install-guide'

interface InternalStep extends ConfigStep {
  _id: string
  _type: string
  table?: ConfigStepTable[]
}

const props = defineProps<{
  modelValue: ConfigStep[]
}>()

const emit = defineEmits<{
  'update:modelValue': [value: ConfigStep[]]
}>()

const steps = computed({
  get: () => props.modelValue.map((s, i) => ({
    ...s,
    _id: (s as any)._id || `step-${i}-${Date.now()}`,
    _type: inferType(s),
  })) as InternalStep[],
  set: (val) => emit('update:modelValue', val.map(({ _id, _type, ...rest }) => rest as ConfigStep))
})

const selectedIndex = ref<number | null>(null)
const dragOverCanvas = ref(false)
const dragStepIndex = ref<number | null>(null)

const selectedStep = computed(() =>
  selectedIndex.value !== null ? steps.value[selectedIndex.value] || null : null
)

function inferType(step: ConfigStep): string {
  if (step.hasExecutorSelector) return 'executor-selector'
  if ((step as any).table?.length) return 'table'
  if (step.code || step.codeField) return 'code'
  return 'step'
}

const paletteElements = [
  { type: 'step', label: 'Etape', icon: 'pi pi-check-circle' },
  { type: 'code', label: 'Code', icon: 'pi pi-code' },
  { type: 'executor-selector', label: 'Selecteur exec.', icon: 'pi pi-list' },
  { type: 'table', label: 'Tableau', icon: 'pi pi-table' },
]

function getStepMeta(type: string) {
  return paletteElements.find(e => e.type === type) || { label: 'Etape', icon: 'pi pi-check-circle' }
}

function generateId() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 7)
}

function createDefaultStep(type: string): InternalStep {
  const base: InternalStep = { _id: generateId(), _type: type, title: '', description: '' }
  if (type === 'code') base.code = ''
  if (type === 'executor-selector') { base.hasExecutorSelector = true; base.codeField = 'cli_add_cmd' }
  if (type === 'table') base.table = [{ field: '', value: '' }]
  return base
}

function stripHtml(html: string): string {
  return html.replace(/<[^>]*>/g, '').substring(0, 80)
}

// ── Drag & Drop ────────────────────────────────────────────────────

function onPaletteDragStart(event: DragEvent, type: string) {
  event.dataTransfer!.setData('palette-type', type)
  event.dataTransfer!.effectAllowed = 'copy'
  dragStepIndex.value = null
}

function onStepDragStart(event: DragEvent, index: number) {
  event.dataTransfer!.setData('move-index', String(index))
  event.dataTransfer!.effectAllowed = 'move'
  dragStepIndex.value = index
}

function onStepDragOver(event: DragEvent, _index: number) {
  if (dragStepIndex.value === null) return
  event.dataTransfer!.dropEffect = 'move'
}

function onStepDrop(event: DragEvent, targetIndex: number) {
  const moveIndex = event.dataTransfer!.getData('move-index')
  if (moveIndex !== '') {
    const from = parseInt(moveIndex)
    if (from === targetIndex) return
    const copy = [...steps.value]
    const [moved] = copy.splice(from, 1)
    copy.splice(targetIndex, 0, moved!)
    steps.value = copy
    if (selectedIndex.value === from) selectedIndex.value = targetIndex
  }
  dragStepIndex.value = null
}

function onCanvasDrop(event: DragEvent) {
  dragOverCanvas.value = false
  const paletteType = event.dataTransfer!.getData('palette-type')
  if (paletteType) {
    const newStep = createDefaultStep(paletteType)
    steps.value = [...steps.value, newStep]
    selectedIndex.value = steps.value.length - 1
  }
}

function removeStep(index: number) {
  if (selectedIndex.value === index) selectedIndex.value = null
  else if (selectedIndex.value !== null && selectedIndex.value > index) selectedIndex.value--
  const copy = [...steps.value]
  copy.splice(index, 1)
  steps.value = copy
}
</script>
