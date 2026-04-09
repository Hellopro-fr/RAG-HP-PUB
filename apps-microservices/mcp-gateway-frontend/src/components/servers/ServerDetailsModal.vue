<template>
  <div class="fixed inset-0 bg-black/50 z-40 flex items-center justify-center" @click.self="emit('close')">
    <div class="bg-white dark:bg-gray-900 rounded-lg shadow-theme-xl p-6 max-w-2xl w-full max-h-[90vh] overflow-y-auto">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-semibold text-gray-900 dark:text-white">Détails du serveur</h2>
        <button class="p-1.5 rounded hover:bg-gray-100 dark:hover:bg-white/5 text-gray-500 dark:text-gray-400" @click="emit('close')">
          <i class="pi pi-times" />
        </button>
      </div>

      <!-- Loading -->
      <div v-if="loading" class="text-center py-8">
        <i class="pi pi-spinner pi-spin text-2xl text-brand-500" />
      </div>

      <!-- Error state -->
      <div v-else-if="error" class="bg-error-50 dark:bg-error-500/15 border border-error-200 dark:border-error-500/30 rounded-md p-4 text-sm text-error-600 dark:text-error-400">
        <i class="pi pi-exclamation-triangle mr-1" />
        {{ error }}
      </div>

      <template v-else-if="detail">
        <!-- Unhealthy alert -->
        <div
          v-if="detail.health_status === 'unhealthy'"
          class="bg-error-50 dark:bg-error-500/15 border border-error-200 dark:border-error-500/30 rounded-md p-3 mb-4 text-sm text-error-600 dark:text-error-400"
        >
          <i class="pi pi-exclamation-triangle mr-1" />
          Serveur inaccessible
          <span v-if="detail.last_error"> — {{ detail.last_error }}</span>
        </div>

        <!-- Info grid -->
        <div class="grid grid-cols-2 gap-3 mb-6">
          <div>
            <span class="text-xs text-gray-500 dark:text-gray-400">ID</span>
            <p class="text-sm font-mono text-gray-800 dark:text-gray-300 truncate">{{ detail.id }}</p>
          </div>
          <div>
            <span class="text-xs text-gray-500 dark:text-gray-400">Santé</span>
            <p>
              <span
                class="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium"
                :class="healthBadgeClass"
              >
                <span class="w-1.5 h-1.5 rounded-full" :class="healthDotClass" />
                {{ detail.health_status }}
              </span>
            </p>
          </div>
          <div v-if="detail.url">
            <span class="text-xs text-gray-500 dark:text-gray-400">URL</span>
            <p class="text-sm text-gray-800 dark:text-gray-300 truncate">{{ detail.url }}</p>
          </div>
          <div v-if="detail.message_url">
            <span class="text-xs text-gray-500 dark:text-gray-400">Message URL</span>
            <p class="text-sm text-gray-800 dark:text-gray-300 truncate">{{ detail.message_url }}</p>
          </div>
          <div>
            <span class="text-xs text-gray-500 dark:text-gray-400">Transport</span>
            <p class="text-sm text-gray-800 dark:text-gray-300">{{ detail.mcp_transport }} ({{ detail.transport_preference }})</p>
          </div>
          <div>
            <span class="text-xs text-gray-500 dark:text-gray-400">Serveur</span>
            <p class="text-sm text-gray-800 dark:text-gray-300">
              {{ detail.server_name || '—' }}
              <span v-if="detail.server_version" class="text-gray-500 dark:text-gray-400">v{{ detail.server_version }}</span>
            </p>
          </div>
        </div>

        <!-- MCP JSON -->
        <div class="mb-6">
          <div class="flex items-center justify-between mb-2">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Configuration MCP JSON</h3>
            <button
              class="text-xs text-brand-500 hover:text-brand-600"
              @click="copyMcpJson"
            >
              <i class="pi pi-copy mr-1" />
              Copier
            </button>
          </div>
          <pre class="bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-800 rounded-md p-3 text-xs font-mono overflow-x-auto max-h-48 text-gray-800 dark:text-gray-300">{{ mcpJsonString }}</pre>
        </div>

        <!-- Tools -->
        <div class="mb-6">
          <div class="flex items-center gap-2 mb-3">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Outils</h3>
            <span class="text-xs bg-brand-100 dark:bg-brand-500/20 text-brand-700 dark:text-brand-400 px-2 py-0.5 rounded-full">
              {{ activeToolsCount }}/{{ detail.tools.length }} actifs
            </span>
          </div>
          <div v-if="detail.tools.length === 0" class="text-sm text-gray-500 dark:text-gray-400">Aucun outil découvert</div>
          <div v-else class="space-y-2 max-h-64 overflow-y-auto">
            <div
              v-for="tool in detail.tools"
              :key="tool.name"
              class="flex items-center justify-between p-2 rounded border border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-800"
            >
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-2">
                  <span class="text-sm font-medium text-gray-800 dark:text-gray-200">{{ tool.name }}</span>
                  <span
                    class="text-xs px-1.5 py-0.5 rounded-full"
                    :class="tool.is_active
                      ? 'bg-success-50 text-success-600 dark:bg-success-500/15 dark:text-success-400'
                      : 'bg-gray-100 text-gray-500 dark:bg-white/5 dark:text-gray-400'"
                  >
                    {{ tool.is_active ? 'Actif' : 'Inactif' }}
                  </span>
                </div>
                <p v-if="tool.description" class="text-xs text-gray-500 dark:text-gray-400 truncate mt-0.5">{{ tool.description }}</p>
              </div>
              <button
                class="ml-2 p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-500 dark:text-gray-400 text-xs"
                :title="tool.is_active ? 'Désactiver' : 'Activer'"
                @click="toggleTool(tool.name, tool.is_active)"
              >
                <i :class="tool.is_active ? 'pi pi-eye' : 'pi pi-eye-slash'" class="text-sm" />
              </button>
            </div>
          </div>
        </div>

        <!-- Resources -->
        <div class="mb-6">
          <div class="flex items-center gap-2 mb-3">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Ressources</h3>
            <span class="text-xs bg-brand-100 dark:bg-brand-500/20 text-brand-700 dark:text-brand-400 px-2 py-0.5 rounded-full">
              {{ detail.resources.length }}
            </span>
          </div>
          <div v-if="detail.resources.length === 0" class="text-sm text-gray-500 dark:text-gray-400">Aucune ressource</div>
          <div v-else class="space-y-2 max-h-48 overflow-y-auto">
            <div
              v-for="resource in detail.resources"
              :key="resource.uri"
              class="p-2 rounded border border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-800"
            >
              <span class="text-sm font-medium text-gray-800 dark:text-gray-200">{{ resource.name }}</span>
              <p class="text-xs font-mono text-gray-500 dark:text-gray-400 truncate">{{ resource.uri }}</p>
              <p v-if="resource.description" class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{{ resource.description }}</p>
            </div>
          </div>
        </div>

        <!-- Prompts -->
        <div>
          <div class="flex items-center gap-2 mb-3">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Prompts</h3>
            <span class="text-xs bg-brand-100 dark:bg-brand-500/20 text-brand-700 dark:text-brand-400 px-2 py-0.5 rounded-full">
              {{ detail.prompts.length }}
            </span>
          </div>
          <div v-if="detail.prompts.length === 0" class="text-sm text-gray-500 dark:text-gray-400">Aucun prompt</div>
          <div v-else class="space-y-2 max-h-48 overflow-y-auto">
            <div
              v-for="prompt in detail.prompts"
              :key="prompt.name"
              class="p-2 rounded border border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-800"
            >
              <span class="text-sm font-medium text-gray-800 dark:text-gray-200">{{ prompt.name }}</span>
              <p v-if="prompt.description" class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{{ prompt.description }}</p>
              <div v-if="prompt.arguments?.length" class="mt-1">
                <span class="text-xs text-gray-400 dark:text-gray-500">Arguments :</span>
                <ul class="list-disc list-inside ml-1">
                  <li
                    v-for="arg in prompt.arguments"
                    :key="arg.name"
                    class="text-xs text-gray-600 dark:text-gray-400"
                  >
                    {{ arg.name }}
                    <span v-if="arg.is_required" class="text-red-500">*</span>
                    <span v-if="arg.description" class="text-gray-400 dark:text-gray-500"> — {{ arg.description }}</span>
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { serversApi } from '@/api/servers'
import { useClipboard } from '@/composables/useClipboard'
import { useToast } from '@/composables/useToast'
import type { ServerDetail } from '@/types/server'

const props = defineProps<{ serverId: string }>()
const emit = defineEmits<{ close: [] }>()

const clipboard = useClipboard()
const toast = useToast()

const detail = ref<ServerDetail>()
const loading = ref(true)
const error = ref('')

onMounted(async () => {
  try {
    detail.value = await serversApi.get(props.serverId)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Impossible de charger les détails du serveur'
  } finally {
    loading.value = false
  }
})

const activeToolsCount = computed(() =>
  detail.value?.tools.filter(t => t.is_active).length ?? 0
)

const healthDotClass = computed(() => {
  switch (detail.value?.health_status) {
    case 'healthy': return 'bg-green-500'
    case 'unhealthy': return 'bg-red-500'
    case 'degraded': return 'bg-yellow-500'
    default: return 'bg-gray-400'
  }
})

const healthBadgeClass = computed(() => {
  switch (detail.value?.health_status) {
    case 'healthy': return 'bg-success-50 text-success-600 dark:bg-success-500/15 dark:text-success-400'
    case 'unhealthy': return 'bg-error-50 text-error-600 dark:bg-error-500/15 dark:text-error-400'
    case 'degraded': return 'bg-warning-50 text-warning-600 dark:bg-warning-500/15 dark:text-warning-400'
    default: return 'bg-gray-100 text-gray-500 dark:bg-white/5 dark:text-gray-400'
  }
})

const mcpJsonString = computed(() => {
  if (!detail.value) return ''
  const config: Record<string, unknown> = {}
  if (detail.value.mcp_transport === 'stdio') {
    config.command = detail.value.mcp_command
    if (detail.value.mcp_args?.length) config.args = detail.value.mcp_args
    if (detail.value.mcp_env && Object.keys(detail.value.mcp_env).length) config.env = detail.value.mcp_env
  } else {
    config.url = detail.value.url
    if (detail.value.transport_preference !== 'auto') config.transport = detail.value.transport_preference
  }
  return JSON.stringify({ mcpServers: { [detail.value.name]: config } }, null, 2)
})

function copyMcpJson() {
  clipboard.copy(mcpJsonString.value, 'Configuration MCP')
}

async function toggleTool(toolName: string, isActive: boolean) {
  if (!detail.value) return
  try {
    if (isActive) {
      await serversApi.disableTool(props.serverId, toolName)
    } else {
      await serversApi.enableTool(props.serverId, toolName)
    }
    // Refresh detail
    detail.value = await serversApi.get(props.serverId)
  } catch (err) {
    toast.error(err instanceof Error ? err.message : 'Erreur lors du basculement de l\'outil')
  }
}
</script>
