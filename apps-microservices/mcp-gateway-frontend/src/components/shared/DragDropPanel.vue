<template>
  <div class="grid grid-cols-2 gap-4">
    <!-- Available panel -->
    <div class="border-2 border-blue-200 rounded-lg p-4 bg-blue-50/30 min-h-[300px]">
      <div class="flex items-center justify-between mb-3">
        <h4 class="text-sm font-semibold text-gray-700">Disponible</h4>
        <button
          class="text-xs text-blue-600 hover:text-blue-800 font-medium"
          @click="dragDrop.moveAllToSelected()"
        >
          Tout ajouter
        </button>
      </div>
      <input
        v-model="dragDrop.availableSearch.value"
        type="text"
        placeholder="Rechercher..."
        class="w-full mb-3 px-3 py-1.5 text-sm border border-gray-300 rounded-md"
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
            class="bg-white rounded-md border border-gray-200 overflow-hidden cursor-move"
            @dblclick="moveServerToSelected(server)"
          >
            <div
              class="flex items-center justify-between px-3 py-2 bg-gray-50 cursor-pointer"
              @click="toggleCollapse(server.id, 'available')"
            >
              <div class="flex items-center gap-2">
                <i
                  class="pi pi-chevron-right text-xs transition-transform"
                  :class="{ 'rotate-90': isExpanded(server.id, 'available') }"
                />
                <span class="text-sm font-medium">{{ server.name }}</span>
              </div>
              <span class="text-xs text-gray-500 bg-gray-200 px-2 py-0.5 rounded-full">
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
                    class="flex items-center gap-2 px-2 py-1 text-xs bg-gray-50 rounded cursor-move hover:bg-gray-100"
                    @dblclick.stop="moveToolToSelected(server, tool)"
                  >
                    <i class="pi pi-wrench text-gray-400" />
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
    <div class="border-2 border-blue-500 rounded-lg p-4 bg-blue-50/50 min-h-[300px]">
      <div class="flex items-center justify-between mb-3">
        <div class="flex items-center gap-2">
          <h4 class="text-sm font-semibold text-blue-800">Sélectionné</h4>
          <span class="text-xs text-blue-600 bg-blue-100 px-2 py-0.5 rounded-full">
            ({{ dragDrop.selectedCount.value.servers }} srv, {{ dragDrop.selectedCount.value.tools }} outils)
          </span>
        </div>
        <button
          class="text-xs text-blue-600 hover:text-blue-800 font-medium"
          @click="dragDrop.moveAllToAvailable()"
        >
          Tout retirer
        </button>
      </div>
      <input
        v-model="dragDrop.selectedSearch.value"
        type="text"
        placeholder="Rechercher..."
        class="w-full mb-3 px-3 py-1.5 text-sm border border-blue-300 rounded-md"
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
            class="bg-white rounded-md border border-blue-200 overflow-hidden cursor-move"
            @dblclick="moveServerToAvailable(server)"
          >
            <div
              class="flex items-center justify-between px-3 py-2 bg-blue-50 cursor-pointer"
              @click="toggleCollapse(server.id, 'selected')"
            >
              <div class="flex items-center gap-2">
                <i
                  class="pi pi-chevron-right text-xs transition-transform"
                  :class="{ 'rotate-90': isExpanded(server.id, 'selected') }"
                />
                <span class="text-sm font-medium text-blue-900">{{ server.name }}</span>
              </div>
              <span class="text-xs text-blue-700 bg-blue-100 px-2 py-0.5 rounded-full">
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
                    class="flex items-center gap-2 px-2 py-1 text-xs bg-blue-50 rounded cursor-move hover:bg-blue-100"
                    @dblclick.stop="moveToolToAvailable(server, tool)"
                  >
                    <i class="pi pi-wrench text-blue-400" />
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
        class="text-center text-sm text-blue-400 py-8"
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
