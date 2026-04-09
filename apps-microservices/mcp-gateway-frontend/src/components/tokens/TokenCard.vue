<template>
  <div class="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 shadow-theme-xs hover:shadow-theme-md transition-shadow">
    <div class="p-5">
      <!-- Main horizontal layout -->
      <div class="flex flex-col lg:flex-row lg:items-start gap-4">
        <!-- Left section: icon + name + status + token prefix -->
        <div class="flex items-start gap-3 lg:w-1/4 shrink-0">
          <div class="w-10 h-10 rounded-full bg-amber-100 dark:bg-amber-500/15 text-amber-600 dark:text-amber-400 flex items-center justify-center shrink-0">
            <i class="pi pi-lock text-lg" />
          </div>
          <div class="min-w-0">
            <div class="flex items-center gap-2 mb-1">
              <h3 class="text-sm font-semibold text-gray-900 dark:text-white truncate max-w-[200px]">
                {{ token.name }}
              </h3>
              <span
                class="text-xs px-2 py-0.5 rounded-full font-medium shrink-0"
                :class="token.is_active
                  ? 'bg-success-50 text-success-600 dark:bg-success-500/15 dark:text-success-400'
                  : 'bg-error-50 text-error-600 dark:bg-error-500/15 dark:text-error-400'"
              >
                {{ token.is_active ? 'Actif' : 'Révoqué' }}
              </span>
            </div>
            <code class="text-xs text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-white/5 px-2 py-1 rounded font-mono">
              {{ maskedPrefix }}
            </code>
          </div>
        </div>

        <!-- Center section: server badges, MCP command, expiration, created_by -->
        <div class="flex-1 min-w-0">
          <div class="flex flex-wrap items-center gap-2 mb-2">
            <!-- Server badges -->
            <span
              v-for="name in serverNames"
              :key="name"
              class="text-xs bg-brand-50 dark:bg-brand-500/10 text-brand-600 dark:text-brand-400 px-2 py-0.5 rounded font-mono"
            >
              {{ name }}
            </span>
            <!-- MCP command badge -->
            <span class="text-xs px-2 py-0.5 rounded bg-purple-100 dark:bg-purple-500/15 text-purple-700 dark:text-purple-400 font-mono">
              {{ token.mcp_command || 'npx' }}
            </span>
          </div>
          <div class="flex flex-wrap items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
            <!-- Expiration -->
            <div class="flex items-center gap-1.5">
              <i class="pi pi-calendar text-[10px]" />
              <span v-if="token.expires_at">
                Expire le {{ formatDate(token.expires_at) }}
              </span>
              <span
                v-else
                class="px-2 py-0.5 rounded-full font-medium bg-success-50 text-success-600 dark:bg-success-500/15 dark:text-success-400"
              >
                Permanent
              </span>
            </div>
            <!-- Created by -->
            <div v-if="token.created_by" class="flex items-center gap-1.5">
              <i class="pi pi-user text-[10px]" />
              <span>{{ token.created_by }}</span>
            </div>
          </div>
        </div>

        <!-- Right section: .mcp.json code block -->
        <div class="lg:w-2/5 shrink-0">
          <div class="flex items-center justify-between mb-1">
            <span class="text-xs font-medium text-gray-600 dark:text-gray-400">.mcp.json</span>
            <button
              class="text-xs text-brand-500 hover:text-brand-600"
              @click="copyMcpJson"
            >
              <i class="pi pi-copy text-[10px] mr-0.5" />
              Copier
            </button>
          </div>
          <pre
            class="text-[11px] bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-800 rounded-md p-3 font-mono overflow-x-auto max-h-[120px] overflow-y-auto whitespace-pre text-gray-800 dark:text-gray-300"
          >{{ mcpJsonDisplay }}</pre>
        </div>
      </div>

      <!-- Bottom row: action buttons -->
      <div class="flex items-center gap-1 pt-3 mt-3 border-t border-gray-100 dark:border-gray-800">
        <button
          class="p-1.5 rounded hover:bg-gray-100 dark:hover:bg-white/5 text-brand-500"
          title="Copier .mcp.json"
          @click="copyMcpJson"
        >
          <i class="pi pi-file-export text-sm" />
        </button>
        <button
          v-if="token.is_active"
          class="p-1.5 rounded hover:bg-gray-100 dark:hover:bg-white/5 text-gray-500 dark:text-gray-400"
          title="Modifier"
          @click="emit('edit', token)"
        >
          <i class="pi pi-pencil text-sm" />
        </button>
        <button
          v-if="token.is_active"
          class="p-1.5 rounded hover:bg-gray-100 dark:hover:bg-white/5 text-orange-500 dark:text-orange-400"
          title="Révoquer"
          @click="emit('revoke', token.id)"
        >
          <i class="pi pi-times text-sm" />
        </button>
        <button
          class="p-1.5 rounded hover:bg-gray-100 dark:hover:bg-white/5 text-red-500 dark:text-error-400"
          title="Supprimer"
          @click="emit('delete', token.id)"
        >
          <i class="pi pi-trash text-sm" />
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ScopeToken } from '@/types/token'
import { useClipboard } from '@/composables/useClipboard'
import { useServersStore } from '@/stores/servers'

const props = defineProps<{ token: ScopeToken }>()

const emit = defineEmits<{
  edit: [token: ScopeToken]
  revoke: [id: string]
  delete: [id: string]
}>()

const clipboard = useClipboard()
const serversStore = useServersStore()

const maskedPrefix = computed(() => {
  const prefix = props.token.token_prefix || ''
  if (prefix.length > 8) {
    return prefix.substring(0, 8) + '...' + '\u2022'.repeat(9)
  }
  return prefix + '...' + '\u2022'.repeat(9)
})

const serverNames = computed(() => {
  return props.token.server_ids
    .map(id => {
      const server = serversStore.servers.find(s => s.id === id)
      return server?.name ?? id
    })
})

const mcpJsonConfig = computed(() => {
  const command = props.token.mcp_command || 'npx'
  const serverName = 'hellopro-gateway'
  const maskedToken = props.token.token_prefix
    ? props.token.token_prefix.substring(0, 8) + '...' + '\u2022'.repeat(9)
    : '***'
  const gatewayUrl = window.location.origin

  if (command === 'custom') {
    return {
      mcpServers: {
        [serverName]: {
          command: command,
          args: [gatewayUrl + '/sse'],
          env: { MCP_TOKEN: maskedToken }
        }
      }
    }
  }

  const argsMap: Record<string, string[]> = {
    npx: ['-y', 'mcp-remote', gatewayUrl + '/sse'],
    bunx: ['mcp-remote', gatewayUrl + '/sse'],
    deno: ['run', '--allow-net', 'npm:mcp-remote', gatewayUrl + '/sse'],
    uvx: ['mcp-remote', gatewayUrl + '/sse'],
    docker: ['run', '-i', '--rm', 'mcp-remote', gatewayUrl + '/sse']
  }

  return {
    mcpServers: {
      [serverName]: {
        command: command,
        args: argsMap[command] || [gatewayUrl + '/sse'],
        env: { MCP_TOKEN: maskedToken }
      }
    }
  }
})

const mcpJsonDisplay = computed(() => {
  return JSON.stringify(mcpJsonConfig.value, null, 2)
})

function copyMcpJson() {
  clipboard.copy(mcpJsonDisplay.value, 'Configuration .mcp.json')
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('fr-FR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}
</script>
