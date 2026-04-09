<template>
  <div class="space-y-3">
    <!-- Search -->
    <input
      v-model="search"
      type="text"
      placeholder="Rechercher un serveur ou outil..."
      class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
    />

    <!-- Summary -->
    <div class="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
      <span>{{ selectedServerCount }} serveur(s), {{ selectedToolCount }} outil(s) sélectionné(s)</span>
      <div class="flex gap-3">
        <button type="button" class="text-brand-500 hover:text-brand-600 font-medium" @click="selectAll">Tout sélectionner</button>
        <button type="button" class="text-brand-500 hover:text-brand-600 font-medium" @click="deselectAll">Tout désélectionner</button>
      </div>
    </div>

    <!-- Server list -->
    <div class="border border-gray-200 dark:border-gray-800 rounded-lg divide-y divide-gray-100 dark:divide-gray-800 max-h-[400px] overflow-y-auto">
      <div v-for="server in filteredServers" :key="server.id" class="bg-white dark:bg-gray-900">
        <!-- Server header -->
        <div class="flex items-center gap-3 px-4 py-3 hover:bg-gray-50 dark:hover:bg-white/5">
          <input
            type="checkbox"
            :checked="isServerFullySelected(server)"
            :indeterminate="isServerPartiallySelected(server)"
            class="rounded border-gray-300 text-brand-500 dark:border-gray-700 shrink-0"
            @change="toggleServer(server)"
          />
          <button
            type="button"
            class="flex items-center gap-2 flex-1 min-w-0"
            @click="toggleCollapse(server.id)"
          >
            <i
              class="pi pi-chevron-right text-xs transition-transform text-gray-400 dark:text-gray-500"
              :class="{ 'rotate-90': expanded.has(server.id) }"
            />
            <i class="pi pi-server text-sm text-gray-400 dark:text-gray-500" />
            <span class="text-sm font-medium text-gray-800 dark:text-gray-200 truncate">{{ server.name }}</span>
          </button>
          <span class="text-xs text-gray-400 dark:text-gray-500 bg-gray-100 dark:bg-white/5 px-2 py-0.5 rounded-full shrink-0">
            {{ countSelectedTools(server) }}/{{ server.tools.length }}
          </span>
        </div>

        <!-- Tools (nested) -->
        <Transition
          enter-active-class="transition-all duration-200 ease-out"
          enter-from-class="opacity-0 max-h-0 overflow-hidden"
          enter-to-class="opacity-100 max-h-[500px] overflow-hidden"
          leave-active-class="transition-all duration-150 ease-in"
          leave-from-class="opacity-100 max-h-[500px] overflow-hidden"
          leave-to-class="opacity-0 max-h-0 overflow-hidden"
        >
        <div v-show="expanded.has(server.id)" class="pl-12 pr-4 pb-2 space-y-1">
          <label
            v-for="tool in server.tools"
            :key="tool.name"
            class="flex items-center gap-2.5 px-3 py-1.5 rounded hover:bg-gray-50 dark:hover:bg-white/5 cursor-pointer"
          >
            <input
              type="checkbox"
              :checked="isToolSelected(server.id, tool.name)"
              class="rounded border-gray-300 text-brand-500 dark:border-gray-700 shrink-0"
              @change="toggleTool(server.id, tool.name)"
            />
            <i class="pi pi-wrench text-xs text-gray-400 dark:text-gray-500" />
            <div class="min-w-0">
              <span class="text-xs text-gray-700 dark:text-gray-300">{{ tool.name }}</span>
              <p v-if="tool.description" class="text-[11px] text-gray-400 dark:text-gray-500 truncate">{{ tool.description }}</p>
            </div>
          </label>
        </div>
        </Transition>
      </div>

      <div v-if="filteredServers.length === 0" class="px-4 py-8 text-center text-sm text-gray-400 dark:text-gray-500">
        Aucun serveur trouvé
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { DragDropServer } from '@/composables/useDragDrop'

const props = defineProps<{
  initialAvailable: DragDropServer[]
  initialSelected: DragDropServer[]
}>()

const emit = defineEmits<{
  'update:available': [servers: DragDropServer[]]
  'update:selected': [servers: DragDropServer[]]
}>()

// Build a flat list of all servers with all their tools
interface ServerItem {
  id: string
  name: string
  tools: { name: string; description?: string }[]
}

// Build server list once at mount — not reactive to prop changes (keeps stable order)
function buildAllServers(): ServerItem[] {
  const serverMap = new Map<string, ServerItem>()
  const order: string[] = []

  for (const s of [...props.initialAvailable, ...props.initialSelected]) {
    const existing = serverMap.get(s.id)
    if (existing) {
      for (const t of s.tools) {
        if (!existing.tools.find(et => et.name === t.name)) {
          existing.tools.push({ name: t.name, description: t.description })
        }
      }
    } else {
      order.push(s.id)
      serverMap.set(s.id, { id: s.id, name: s.name, tools: s.tools.map(t => ({ name: t.name, description: t.description })) })
    }
  }

  return order.map(id => serverMap.get(id)!)
}

const allServers = ref<ServerItem[]>(buildAllServers())

// Selection state: Set of "serverId:toolName"
const selectedTools = ref<Set<string>>(new Set())

// Initialize selection from initialSelected
console.log('[DragDropPanel] initialSelected:', props.initialSelected.length, 'servers', props.initialSelected.map(s => s.id + ':' + s.tools.length))
console.log('[DragDropPanel] initialAvailable:', props.initialAvailable.length, 'servers')
for (const s of props.initialSelected) {
  for (const t of s.tools) {
    selectedTools.value.add(`${s.id}:${t.name}`)
  }
}
console.log('[DragDropPanel] selectedTools set size:', selectedTools.value.size)

const search = ref('')
const expanded = ref<Set<string>>(new Set())

const filteredServers = computed(() => {
  if (!search.value) return allServers.value
  const q = search.value.toLowerCase()
  return allServers.value
    .map(s => ({
      ...s,
      tools: s.tools.filter(t => t.name.toLowerCase().includes(q) || (t.description?.toLowerCase().includes(q) ?? false))
    }))
    .filter(s => s.name.toLowerCase().includes(q) || s.tools.length > 0)
})

const selectedServerCount = computed(() => {
  const serverIds = new Set<string>()
  for (const key of selectedTools.value) {
    serverIds.add(key.split(':')[0] as string)
  }
  return serverIds.size
})

const selectedToolCount = computed(() => selectedTools.value.size)

function isToolSelected(serverId: string, toolName: string): boolean {
  return selectedTools.value.has(`${serverId}:${toolName}`)
}

function isServerFullySelected(server: ServerItem): boolean {
  return server.tools.length > 0 && server.tools.every(t => selectedTools.value.has(`${server.id}:${t.name}`))
}

function isServerPartiallySelected(server: ServerItem): boolean {
  const count = server.tools.filter(t => selectedTools.value.has(`${server.id}:${t.name}`)).length
  return count > 0 && count < server.tools.length
}

function countSelectedTools(server: ServerItem): number {
  return server.tools.filter(t => selectedTools.value.has(`${server.id}:${t.name}`)).length
}

function toggleServer(server: ServerItem) {
  const allSelected = isServerFullySelected(server)
  for (const tool of server.tools) {
    const key = `${server.id}:${tool.name}`
    if (allSelected) {
      selectedTools.value.delete(key)
    } else {
      selectedTools.value.add(key)
    }
  }
  // Unfold when checking, fold when unchecking all
  if (allSelected) {
    expanded.value.delete(server.id)
  } else {
    expanded.value.add(server.id)
  }
  expanded.value = new Set(expanded.value)
  selectedTools.value = new Set(selectedTools.value)
  emitChanges()
}

function toggleTool(serverId: string, toolName: string) {
  const key = `${serverId}:${toolName}`
  if (selectedTools.value.has(key)) {
    selectedTools.value.delete(key)
  } else {
    selectedTools.value.add(key)
  }
  selectedTools.value = new Set(selectedTools.value)
  emitChanges()
}

function toggleCollapse(serverId: string) {
  if (expanded.value.has(serverId)) expanded.value.delete(serverId)
  else expanded.value.add(serverId)
  expanded.value = new Set(expanded.value)
}

function selectAll() {
  for (const s of allServers.value) {
    for (const t of s.tools) {
      selectedTools.value.add(`${s.id}:${t.name}`)
    }
  }
  selectedTools.value = new Set(selectedTools.value)
  emitChanges()
}

function deselectAll() {
  selectedTools.value = new Set()
  emitChanges()
}

function emitChanges() {
  const selectedMap = new Map<string, DragDropServer>()
  const availableMap = new Map<string, DragDropServer>()

  for (const server of allServers.value) {
    const selTools = server.tools.filter(t => selectedTools.value.has(`${server.id}:${t.name}`))
    const availTools = server.tools.filter(t => !selectedTools.value.has(`${server.id}:${t.name}`))

    if (selTools.length > 0) {
      selectedMap.set(server.id, {
        id: server.id,
        name: server.name,
        tools: selTools.map(t => ({ serverId: server.id, name: t.name, description: t.description }))
      })
    }
    if (availTools.length > 0) {
      availableMap.set(server.id, {
        id: server.id,
        name: server.name,
        tools: availTools.map(t => ({ serverId: server.id, name: t.name, description: t.description }))
      })
    }
  }

  emit('update:selected', Array.from(selectedMap.values()))
  emit('update:available', Array.from(availableMap.values()))
}
</script>
