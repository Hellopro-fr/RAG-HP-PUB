<template>
  <div class="bg-white rounded-lg border border-gray-200 shadow-sm hover:shadow-md transition-shadow">
    <div class="p-4">
      <!-- Header -->
      <div class="flex items-start justify-between mb-3">
        <div class="flex items-center gap-2">
          <i class="pi pi-lock text-gray-400 text-sm" />
          <h3 class="text-sm font-semibold text-gray-900 truncate max-w-[200px]">
            {{ token.name }}
          </h3>
        </div>
        <div class="flex items-center gap-1.5">
          <span
            class="text-xs px-2 py-0.5 rounded-full font-medium"
            :class="token.is_active
              ? 'bg-green-100 text-green-700'
              : 'bg-red-100 text-red-700'"
          >
            {{ token.is_active ? 'Actif' : 'Révoqué' }}
          </span>
        </div>
      </div>

      <!-- Token prefix -->
      <div class="mb-3">
        <code class="text-xs text-gray-600 bg-gray-100 px-2 py-1 rounded font-mono">
          {{ maskedPrefix }}
        </code>
      </div>

      <!-- Server badges -->
      <div v-if="serverNames.length" class="flex flex-wrap gap-1 mb-3">
        <span
          v-for="name in serverNames"
          :key="name"
          class="text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded font-mono"
        >
          {{ name }}
        </span>
      </div>

      <!-- Info row -->
      <div class="space-y-1.5 mb-3">
        <!-- Expiration -->
        <div class="flex items-center gap-2 text-xs text-gray-500">
          <i class="pi pi-calendar text-[10px]" />
          <span v-if="token.expires_at">
            Expire le {{ formatDate(token.expires_at) }}
          </span>
          <span
            v-else
            class="text-xs px-2 py-0.5 rounded-full font-medium bg-green-100 text-green-700"
          >
            Permanent
          </span>
        </div>

        <!-- Created by -->
        <div v-if="token.created_by" class="flex items-center gap-2 text-xs text-gray-500">
          <i class="pi pi-user text-[10px]" />
          <span>{{ token.created_by }}</span>
        </div>

        <!-- MCP command -->
        <div class="flex items-center gap-2 text-xs text-gray-500">
          <i class="pi pi-code text-[10px]" />
          <span class="px-2 py-0.5 rounded bg-purple-100 text-purple-700 font-mono text-[11px]">
            {{ token.mcp_command || 'npx' }}
          </span>
        </div>
      </div>

      <!-- .mcp.json display -->
      <div class="mb-3">
        <div class="flex items-center justify-between mb-1">
          <span class="text-xs font-medium text-gray-600">.mcp.json</span>
          <button
            class="text-xs text-blue-600 hover:text-blue-800"
            @click="copyMcpJson"
          >
            <i class="pi pi-copy text-[10px] mr-0.5" />
            Copier
          </button>
        </div>
        <pre
          class="text-[11px] bg-gray-50 border border-gray-200 rounded-md p-3 font-mono overflow-x-auto max-h-[120px] overflow-y-auto whitespace-pre"
        >{{ mcpJsonDisplay }}</pre>
      </div>

      <!-- Actions -->
      <div class="flex items-center justify-between pt-3 border-t border-gray-100">
        <div class="flex items-center gap-1">
          <button
            class="p-1.5 rounded hover:bg-gray-100 text-blue-500"
            title="Copier .mcp.json"
            @click="copyMcpJson"
          >
            <i class="pi pi-file-export text-sm" />
          </button>
          <button
            v-if="token.is_active"
            class="p-1.5 rounded hover:bg-gray-100 text-gray-500"
            title="Modifier"
            @click="emit('edit', token)"
          >
            <i class="pi pi-pencil text-sm" />
          </button>
          <button
            v-if="token.is_active"
            class="p-1.5 rounded hover:bg-gray-100 text-orange-500"
            title="Révoquer"
            @click="emit('revoke', token.id)"
          >
            <i class="pi pi-times text-sm" />
          </button>
          <button
            class="p-1.5 rounded hover:bg-gray-100 text-red-500"
            title="Supprimer"
            @click="emit('delete', token.id)"
          >
            <i class="pi pi-trash text-sm" />
          </button>
        </div>
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
