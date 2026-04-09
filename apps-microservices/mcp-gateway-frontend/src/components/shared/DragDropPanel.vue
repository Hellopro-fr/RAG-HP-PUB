<template>
  <div class="grid grid-cols-2 gap-4">
    <!-- Available panel -->
    <div class="border-2 border-brand-200 dark:border-brand-500/30 rounded-lg p-4 bg-brand-50/30 dark:bg-brand-500/5 min-h-[300px]">
      <div class="flex items-center justify-between mb-3">
        <h4 class="text-sm font-semibold text-gray-700 dark:text-gray-300">Disponible</h4>
        <button
          class="text-xs text-brand-500 hover:text-brand-600 font-medium"
          @click="dragDrop.moveAllToSelected()"
        >
          Tout ajouter
        </button>
      </div>
      <input
        v-model="dragDrop.availableSearch.value"
        type="text"
        placeholder="Rechercher..."
        class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30 mb-3"
      />
      <VueDraggable
        v-model="dragDrop.available.value"
        group="servers"
        :animation="200"
        item-key="id"
        class="space-y-2 min-h-[200px]"
      >
        <template #item="{ element: server }">
          <div
            class="bg-white dark:bg-gray-900 rounded-md border border-gray-200 dark:border-gray-800 overflow-hidden cursor-move"
            @dblclick="moveServerToSelected(server)"
          >
            <div
              class="flex items-center justify-between px-3 py-2 bg-gray-50 dark:bg-gray-800 cursor-pointer"
              @click="toggleCollapse(server.id, 'available')"
            >
              <div class="flex items-center gap-2">
                <i
                  class="pi pi-chevron-right text-xs transition-transform text-gray-500 dark:text-gray-400"
                  :class="{ 'rotate-90': isExpanded(server.id, 'available') }"
                />
                <span class="text-sm font-medium text-gray-800 dark:text-gray-200">{{ server.name }}</span>
              </div>
              <span class="text-xs text-gray-500 dark:text-gray-400 bg-gray-200 dark:bg-gray-700 px-2 py-0.5 rounded-full">
                {{ server.tools.length }} outils
              </span>
            </div>
            <div v-show="isExpanded(server.id, 'available')" class="px-3 py-2">
              <VueDraggable
                v-model="server.tools"
                group="tools"
                :animation="200"
                item-key="name"
                class="space-y-1"
              >
                <template #item="{ element: tool }">
                  <div
                    class="flex items-center gap-2 px-2 py-1 text-xs bg-gray-50 dark:bg-gray-800 rounded cursor-move hover:bg-gray-100 dark:hover:bg-white/5 text-gray-800 dark:text-gray-300"
                    @dblclick.stop="moveToolToSelected(server, tool)"
                  >
                    <i class="pi pi-wrench text-gray-400 dark:text-gray-500" />
                    <span>{{ tool.name }}</span>
                  </div>
                </template>
              </VueDraggable>
            </div>
          </div>
        </template>
      </VueDraggable>
    </div>

    <!-- Selected panel -->
    <div class="border-2 border-brand-500 dark:border-brand-500/60 rounded-lg p-4 bg-brand-50/50 dark:bg-brand-500/10 min-h-[300px]">
      <div class="flex items-center justify-between mb-3">
        <div class="flex items-center gap-2">
          <h4 class="text-sm font-semibold text-brand-800 dark:text-brand-300">Sélectionné</h4>
          <span class="text-xs text-brand-600 dark:text-brand-400 bg-brand-100 dark:bg-brand-500/20 px-2 py-0.5 rounded-full">
            ({{ dragDrop.selectedCount.value.servers }} srv, {{ dragDrop.selectedCount.value.tools }} outils)
          </span>
        </div>
        <button
          class="text-xs text-brand-500 hover:text-brand-600 font-medium"
          @click="dragDrop.moveAllToAvailable()"
        >
          Tout retirer
        </button>
      </div>
      <input
        v-model="dragDrop.selectedSearch.value"
        type="text"
        placeholder="Rechercher..."
        class="h-11 w-full rounded-lg border border-brand-300 dark:border-brand-500/40 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30 mb-3"
      />
      <VueDraggable
        v-model="dragDrop.selected.value"
        group="servers"
        :animation="200"
        item-key="id"
        class="space-y-2 min-h-[200px]"
      >
        <template #item="{ element: server }">
          <div
            class="bg-white dark:bg-gray-900 rounded-md border border-brand-200 dark:border-brand-500/30 overflow-hidden cursor-move"
            @dblclick="moveServerToAvailable(server)"
          >
            <div
              class="flex items-center justify-between px-3 py-2 bg-brand-50 dark:bg-brand-500/10 cursor-pointer"
              @click="toggleCollapse(server.id, 'selected')"
            >
              <div class="flex items-center gap-2">
                <i
                  class="pi pi-chevron-right text-xs transition-transform text-brand-500 dark:text-brand-400"
                  :class="{ 'rotate-90': isExpanded(server.id, 'selected') }"
                />
                <span class="text-sm font-medium text-brand-900 dark:text-brand-300">{{ server.name }}</span>
              </div>
              <span class="text-xs text-brand-700 dark:text-brand-400 bg-brand-100 dark:bg-brand-500/20 px-2 py-0.5 rounded-full">
                {{ server.tools.length }} outils
              </span>
            </div>
            <div v-show="isExpanded(server.id, 'selected')" class="px-3 py-2">
              <VueDraggable
                v-model="server.tools"
                group="tools"
                :animation="200"
                item-key="name"
                class="space-y-1"
              >
                <template #item="{ element: tool }">
                  <div
                    class="flex items-center gap-2 px-2 py-1 text-xs bg-brand-50 dark:bg-brand-500/10 rounded cursor-move hover:bg-brand-100 dark:hover:bg-brand-500/20 text-gray-800 dark:text-gray-300"
                    @dblclick.stop="moveToolToAvailable(server, tool)"
                  >
                    <i class="pi pi-wrench text-brand-400 dark:text-brand-500" />
                    <span>{{ tool.name }}</span>
                  </div>
                </template>
              </VueDraggable>
            </div>
          </div>
        </template>
      </VueDraggable>
      <div
        v-if="dragDrop.selected.value.length === 0"
        class="text-center text-sm text-brand-400 dark:text-brand-500 py-8"
      >
        Glissez des serveurs et outils ici
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { VueDraggable } from 'vue-draggable-plus'
import type { DragDropServer, DragDropTool } from '@/composables/useDragDrop'

const props = defineProps<{
  dragDrop: ReturnType<typeof import('@/composables/useDragDrop').useDragDrop>
}>()

const expandedAvailable = ref<Set<string>>(new Set())
const expandedSelected = ref<Set<string>>(new Set())

function isExpanded(id: string, panel: 'available' | 'selected'): boolean {
  const set = panel === 'available' ? expandedAvailable.value : expandedSelected.value
  return set.has(id)
}

function toggleCollapse(id: string, panel: 'available' | 'selected') {
  const set = panel === 'available' ? expandedAvailable.value : expandedSelected.value
  if (set.has(id)) {
    set.delete(id)
  } else {
    set.add(id)
  }
}

function moveServerToSelected(server: DragDropServer) {
  props.dragDrop.available.value = props.dragDrop.available.value.filter(s => s.id !== server.id)
  props.dragDrop.selected.value.push(server)
}

function moveServerToAvailable(server: DragDropServer) {
  props.dragDrop.selected.value = props.dragDrop.selected.value.filter(s => s.id !== server.id)
  props.dragDrop.available.value.push(server)
}

function moveToolToSelected(server: DragDropServer, tool: DragDropTool) {
  server.tools = server.tools.filter(t => t.name !== tool.name)
  let targetServer = props.dragDrop.selected.value.find(s => s.id === server.id)
  if (!targetServer) {
    targetServer = { id: server.id, name: server.name, tools: [] }
    props.dragDrop.selected.value.push(targetServer)
  }
  targetServer.tools.push(tool)
  if (server.tools.length === 0) {
    props.dragDrop.available.value = props.dragDrop.available.value.filter(s => s.id !== server.id)
  }
}

function moveToolToAvailable(server: DragDropServer, tool: DragDropTool) {
  server.tools = server.tools.filter(t => t.name !== tool.name)
  let targetServer = props.dragDrop.available.value.find(s => s.id === server.id)
  if (!targetServer) {
    targetServer = { id: server.id, name: server.name, tools: [] }
    props.dragDrop.available.value.push(targetServer)
  }
  targetServer.tools.push(tool)
  if (server.tools.length === 0) {
    props.dragDrop.selected.value = props.dragDrop.selected.value.filter(s => s.id !== server.id)
  }
}
</script>
