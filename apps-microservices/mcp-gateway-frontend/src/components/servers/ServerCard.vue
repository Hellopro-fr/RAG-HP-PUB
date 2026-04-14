<template>
  <div class="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 shadow-theme-xs hover:shadow-theme-md transition-shadow">
    <div class="p-5">
      <!-- Row 1: Icon + name + tags | transport + status -->
      <div class="flex items-start justify-between gap-4">
        <div class="flex items-center gap-3 min-w-0 flex-wrap">
          <div v-if="server.icon" class="w-10 h-10 rounded-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 flex items-center justify-center shrink-0 p-1">
            <img :src="server.icon" :alt="server.name" class="w-7 h-7 object-contain" />
          </div>
          <div v-else class="w-10 h-10 rounded-full bg-brand-50 dark:bg-brand-500/15 text-brand-500 flex items-center justify-center shrink-0">
            <i class="pi pi-server text-lg" />
          </div>
          <div class="flex items-center gap-2 min-w-0">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white truncate max-w-[250px]">
              {{ server.name }}
            </h3>
            <span
              class="inline-block w-2.5 h-2.5 rounded-full shrink-0"
              :class="healthDotClass"
              :title="'Santé: ' + (server.health_status || 'inconnu')"
            />
          </div>
          <span
            v-if="server.created_by"
            class="text-xs text-gray-400 dark:text-gray-500 truncate max-w-[200px]"
            :title="server.created_by"
          >
            par {{ server.created_by }}
          </span>
          <div v-if="server.tags?.length" class="flex flex-wrap gap-1">
            <span
              v-for="tag in server.tags"
              :key="tag"
              class="text-xs bg-gray-100 dark:bg-white/5 text-gray-600 dark:text-gray-400 px-2 py-0.5 rounded-full"
            >
              {{ tag }}
            </span>
          </div>
        </div>
        <div class="flex items-center gap-1.5 shrink-0">
          <span
            class="text-xs px-2 py-0.5 rounded-full font-medium"
            :class="server.mcp_transport === 'stdio'
              ? 'bg-purple-100 text-purple-700 dark:bg-purple-500/15 dark:text-purple-400'
              : 'bg-cyan-100 text-cyan-700 dark:bg-cyan-500/15 dark:text-cyan-400'"
          >
            {{ server.mcp_transport === 'stdio' ? 'Stdio' : 'HTTP' }}
          </span>
          <span
            class="text-xs px-2 py-0.5 rounded-full font-medium"
            :class="server.is_active
              ? 'bg-success-50 text-success-600 dark:bg-success-500/15 dark:text-success-400'
              : 'bg-gray-100 text-gray-500 dark:bg-white/5 dark:text-gray-400'"
          >
            {{ server.is_active ? 'Actif' : 'Inactif' }}
          </span>
        </div>
      </div>

      <!-- Error -->
      <p v-if="server.last_error && server.health_status !== 'healthy'" class="text-xs text-error-600 dark:text-error-400 mt-2 truncate">
        {{ server.last_error }}
      </p>

      <!-- Row 2: Tools list -->
      <div v-if="server.tool_names?.length" class="mt-4 pt-4 border-t border-gray-100 dark:border-gray-800">
        <div class="flex items-center gap-2 mb-2">
          <span class="text-xs font-medium text-gray-500 dark:text-gray-400">Outils</span>
          <span class="text-xs bg-brand-50 dark:bg-brand-500/10 text-brand-600 dark:text-brand-400 px-1.5 py-0.5 rounded-full">
            {{ activeToolsCount }}/{{ server.tool_names.length }}
          </span>
        </div>
        <div class="space-y-1 max-h-[200px] overflow-y-auto">
          <div
            v-for="tool in server.tool_names"
            :key="tool.name"
            class="flex items-center justify-between px-3 py-1.5 rounded hover:bg-gray-50 dark:hover:bg-white/5 group"
          >
            <div class="flex items-center gap-2 min-w-0 flex-1">
              <i class="pi pi-wrench text-xs" :class="tool.is_active ? 'text-brand-400' : 'text-gray-300 dark:text-gray-600'" />
              <span class="text-xs font-medium" :class="tool.is_active ? 'text-gray-700 dark:text-gray-300' : 'text-gray-400 dark:text-gray-600 line-through'">
                {{ tool.name }}
              </span>
              <span
                class="text-xs px-1.5 py-0.5 rounded-full"
                :class="tool.is_active
                  ? 'bg-success-50 text-success-600 dark:bg-success-500/15 dark:text-success-400'
                  : 'bg-gray-100 text-gray-400 dark:bg-white/5 dark:text-gray-500'"
              >
                {{ tool.is_active ? 'Actif' : 'Inactif' }}
              </span>
              <span v-if="tool.description" class="text-[11px] text-gray-400 dark:text-gray-500 truncate max-w-[300px]">
                {{ tool.description }}
              </span>
            </div>
            <button
              v-if="isAdmin"
              class="p-1 rounded opacity-0 group-hover:opacity-100 transition-opacity"
              :class="tool.is_active
                ? 'hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-500 dark:text-gray-400'
                : 'hover:bg-success-50 dark:hover:bg-success-500/15 text-success-500'"
              :title="tool.is_active ? 'Désactiver' : 'Activer'"
              @click="emit('toggleTool', server.id, tool.name, !tool.is_active)"
            >
              <i :class="tool.is_active ? 'pi pi-eye-slash' : 'pi pi-eye'" class="text-xs" />
            </button>
          </div>
        </div>
      </div>

      <!-- Row 3: Action buttons | Détails -->
      <div class="flex items-center justify-between mt-4 pt-4 border-t border-gray-100 dark:border-gray-800">
        <div class="flex items-center gap-1">
          <button
            v-if="isAdmin"
            class="p-1.5 rounded hover:bg-gray-100 dark:hover:bg-white/5 text-gray-500 dark:text-gray-400"
            :title="server.is_active ? 'Désactiver' : 'Activer'"
            @click="emit('toggle', server.id, !server.is_active)"
          >
            <i :class="server.is_active ? 'pi pi-eye' : 'pi pi-eye-slash'" class="text-sm" />
          </button>
          <button
            v-if="isAdmin"
            class="p-1.5 rounded hover:bg-gray-100 dark:hover:bg-white/5 text-gray-500 dark:text-gray-400"
            title="Modifier"
            @click="emit('edit', server)"
          >
            <i class="pi pi-pencil text-sm" />
          </button>
          <button
            v-if="isAdmin"
            class="p-1.5 rounded hover:bg-gray-100 dark:hover:bg-white/5 text-gray-500 dark:text-gray-400"
            title="Documentation"
            @click="emit('documentation', server.id)"
          >
            <i class="pi pi-book text-sm" />
          </button>
          <button
            v-if="isAdmin"
            class="p-1.5 rounded hover:bg-gray-100 dark:hover:bg-white/5 text-gray-500 dark:text-gray-400"
            title="Découvrir"
            :disabled="discovering"
            @click="handleDiscover"
          >
            <i class="pi pi-refresh text-sm" :class="{ 'pi-spin': discovering }" />
          </button>
          <button
            v-if="isAdmin"
            class="p-1.5 rounded hover:bg-gray-100 dark:hover:bg-white/5 text-red-500 dark:text-error-400"
            title="Supprimer"
            @click="emit('delete', server.id)"
          >
            <i class="pi pi-trash text-sm" />
          </button>
        </div>
        <button
          class="text-xs text-brand-500 hover:text-brand-600 font-medium"
          @click="emit('details', server.id)"
        >
          Détails →
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Server } from '@/types/server'

const props = defineProps<{ server: Server; isAdmin?: boolean }>()

const emit = defineEmits<{
  toggle: [id: string, enable: boolean]
  toggleTool: [serverId: string, toolName: string, enable: boolean]
  edit: [server: Server]
  delete: [id: string]
  details: [id: string]
  discover: [id: string]
  documentation: [id: string]
}>()

const discovering = ref(false)

const healthDotClass = computed(() => {
  switch (props.server.health_status) {
    case 'healthy': return 'bg-green-500'
    case 'unhealthy': return 'bg-red-500'
    case 'degraded': return 'bg-yellow-500'
    default: return 'bg-gray-400'
  }
})

const activeToolsCount = computed(() => {
  return (props.server.tool_names || []).filter(t => t.is_active).length
})

async function handleDiscover() {
  discovering.value = true
  emit('discover', props.server.id)
  setTimeout(() => { discovering.value = false }, 3000)
}
</script>
