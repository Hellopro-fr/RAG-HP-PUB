<template>
  <div class="bg-white rounded-lg border border-gray-200 shadow-sm hover:shadow-md transition-shadow">
    <div class="p-4">
      <!-- Header -->
      <div class="flex items-start justify-between mb-3">
        <div class="flex items-center gap-2">
          <i class="pi pi-lock text-gray-400 text-sm" />
          <h3 class="text-sm font-semibold text-gray-900 truncate max-w-[200px]">
            {{ client.name }}
          </h3>
        </div>
        <div class="flex items-center gap-1.5">
          <span
            class="text-xs px-2 py-0.5 rounded-full font-medium"
            :class="client.is_active
              ? 'bg-green-100 text-green-700'
              : 'bg-red-100 text-red-700'"
          >
            {{ client.is_active ? 'Actif' : 'Révoqué' }}
          </span>
          <span
            class="text-xs px-2 py-0.5 rounded-full font-medium"
            :class="client.dynamically_registered
              ? 'bg-purple-100 text-purple-700'
              : 'bg-gray-100 text-gray-500'"
          >
            {{ client.dynamically_registered ? 'Dynamic' : 'Manuel' }}
          </span>
        </div>
      </div>

      <!-- Secret prefix -->
      <div class="mb-3">
        <code class="text-xs text-gray-600 bg-gray-100 px-2 py-1 rounded font-mono">
          {{ maskedSecret }}
        </code>
      </div>

      <!-- Client ID / Secret display -->
      <div class="space-y-2 mb-3">
        <div class="flex items-center gap-2">
          <span class="text-xs text-gray-500 w-16 shrink-0">Client ID</span>
          <code class="text-xs bg-gray-50 px-2 py-1 rounded font-mono truncate flex-1">
            {{ maskedClientId }}
          </code>
          <button
            class="shrink-0 p-1 rounded hover:bg-gray-100 text-blue-500"
            title="Copier le Client ID"
            @click="clipboard.copy(client.id, 'Client ID')"
          >
            <i class="pi pi-copy text-xs" />
          </button>
        </div>
        <div class="flex items-center gap-2">
          <span class="text-xs text-gray-500 w-16 shrink-0">Secret</span>
          <code
            v-if="client.client_secret"
            class="text-xs bg-gray-50 px-2 py-1 rounded font-mono truncate flex-1"
          >
            {{ maskedSecret }}
          </code>
          <span v-else class="text-xs text-gray-400 italic">Non disponible</span>
        </div>
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
        <!-- TTL -->
        <div class="flex items-center gap-2 text-xs text-gray-500">
          <i class="pi pi-clock text-[10px]" />
          <span class="px-2 py-0.5 rounded bg-indigo-100 text-indigo-700 font-medium">
            {{ formattedTtl }}
          </span>
        </div>

        <!-- Expiration -->
        <div class="flex items-center gap-2 text-xs text-gray-500">
          <i class="pi pi-calendar text-[10px]" />
          <span v-if="client.expires_at">
            Expire le {{ formatDate(client.expires_at) }}
          </span>
          <span
            v-else
            class="text-xs px-2 py-0.5 rounded-full font-medium bg-green-100 text-green-700"
          >
            Permanent
          </span>
        </div>

        <!-- Created by -->
        <div v-if="client.created_by" class="flex items-center gap-2 text-xs text-gray-500">
          <i class="pi pi-user text-[10px]" />
          <span>{{ client.created_by }}</span>
        </div>

        <!-- Redirect URI -->
        <div v-if="client.redirect_uris?.length" class="flex items-center gap-2 text-xs text-gray-500">
          <i class="pi pi-external-link text-[10px]" />
          <span class="truncate">{{ client.redirect_uris[0] }}</span>
        </div>
      </div>

      <!-- Actions -->
      <div class="flex items-center justify-between pt-3 border-t border-gray-100">
        <div class="flex items-center gap-1">
          <button
            class="p-1.5 rounded hover:bg-gray-100 text-blue-500"
            title="Copier le Client ID"
            @click="clipboard.copy(client.id, 'Client ID')"
          >
            <i class="pi pi-copy text-sm" />
          </button>
          <button
            v-if="client.is_active"
            class="p-1.5 rounded hover:bg-gray-100 text-gray-500"
            title="Modifier le scope"
            @click="emit('edit', client)"
          >
            <i class="pi pi-pencil text-sm" />
          </button>
          <button
            v-if="client.is_active"
            class="p-1.5 rounded hover:bg-gray-100 text-orange-500"
            title="Révoquer"
            @click="emit('revoke', client.id)"
          >
            <i class="pi pi-times text-sm" />
          </button>
          <button
            class="p-1.5 rounded hover:bg-gray-100 text-red-500"
            title="Supprimer"
            @click="emit('delete', client.id)"
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
import type { OAuth2Client } from '@/types/oauth2'
import { useClipboard } from '@/composables/useClipboard'
import { useServersStore } from '@/stores/servers'

const props = defineProps<{ client: OAuth2Client }>()

const emit = defineEmits<{
  edit: [client: OAuth2Client]
  revoke: [id: string]
  delete: [id: string]
}>()

const clipboard = useClipboard()
const serversStore = useServersStore()

const maskedClientId = computed(() => {
  const id = props.client.id || ''
  if (id.length > 8) {
    return id.substring(0, 8) + '\u2022'.repeat(8)
  }
  return id
})

const maskedSecret = computed(() => {
  const prefix = props.client.secret_prefix || ''
  if (prefix.length > 12) {
    return prefix.substring(0, 12) + '...' + '\u2022'.repeat(11)
  }
  return prefix + '...' + '\u2022'.repeat(11)
})

const serverNames = computed(() => {
  return props.client.server_ids
    .map(id => {
      const server = serversStore.servers.find(s => s.id === id)
      return server?.name ?? id
    })
})

const TTL_MAP: Record<number, string> = {
  3600: '1h',
  21600: '6h',
  86400: '24h',
  604800: '7j',
  2592000: '30j'
}

const formattedTtl = computed(() => {
  return TTL_MAP[props.client.access_token_ttl] || `${props.client.access_token_ttl}s`
})

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
