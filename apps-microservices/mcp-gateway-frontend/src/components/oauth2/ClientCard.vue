<template>
  <div class="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 shadow-theme-xs hover:shadow-theme-md transition-shadow">
    <div class="p-5">
      <!-- Main horizontal layout -->
      <div class="flex flex-col lg:flex-row lg:items-start gap-4">
        <!-- Left section: icon + name + status badges -->
        <div class="flex items-start gap-3 lg:w-1/4 shrink-0">
          <div class="w-10 h-10 rounded-full bg-indigo-100 dark:bg-indigo-500/15 text-indigo-600 dark:text-indigo-400 flex items-center justify-center shrink-0">
            <i class="pi pi-lock text-lg" />
          </div>
          <div class="min-w-0">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white truncate max-w-[200px] mb-1">
              {{ client.name }}
            </h3>
            <div class="flex items-center gap-1.5">
              <span
                class="text-xs px-2 py-0.5 rounded-full font-medium"
                :class="client.is_active
                  ? 'bg-success-50 text-success-600 dark:bg-success-500/15 dark:text-success-400'
                  : 'bg-error-50 text-error-600 dark:bg-error-500/15 dark:text-error-400'"
              >
                {{ client.is_active ? 'Actif' : 'Révoqué' }}
              </span>
              <span
                class="text-xs px-2 py-0.5 rounded-full font-medium"
                :class="client.dynamically_registered
                  ? 'bg-purple-100 text-purple-700 dark:bg-purple-500/15 dark:text-purple-400'
                  : 'bg-gray-100 text-gray-500 dark:bg-white/5 dark:text-gray-400'"
              >
                {{ client.dynamically_registered ? 'Dynamic' : 'Manuel' }}
              </span>
            </div>
          </div>
        </div>

        <!-- Center section: client ID, secret, server badges, TTL, expiration, redirect URI -->
        <div class="flex-1 min-w-0">
          <!-- Client ID + Secret -->
          <div class="space-y-1.5 mb-3">
            <div class="flex items-center gap-2">
              <span class="text-xs text-gray-500 dark:text-gray-400 w-16 shrink-0">Client ID</span>
              <code class="text-xs bg-gray-50 dark:bg-gray-800 px-2 py-1 rounded font-mono truncate flex-1 text-gray-800 dark:text-gray-300">
                {{ maskedClientId }}
              </code>
              <button
                class="shrink-0 p-1 rounded hover:bg-gray-100 dark:hover:bg-white/5 text-brand-500"
                title="Copier le Client ID"
                @click="clipboard.copy(client.id, 'Client ID')"
              >
                <i class="pi pi-copy text-xs" />
              </button>
            </div>
            <div class="flex items-center gap-2">
              <span class="text-xs text-gray-500 dark:text-gray-400 w-16 shrink-0">Secret</span>
              <code
                v-if="client.client_secret"
                class="text-xs bg-gray-50 dark:bg-gray-800 px-2 py-1 rounded font-mono truncate flex-1 text-gray-800 dark:text-gray-300"
              >
                {{ maskedSecret }}
              </code>
              <span v-else class="text-xs text-gray-400 dark:text-gray-500 italic">Non disponible</span>
            </div>
          </div>

          <!-- Badges row -->
          <div class="flex flex-wrap items-center gap-2 mb-2">
            <!-- Server badges -->
            <span
              v-for="name in serverNames"
              :key="name"
              class="text-xs bg-brand-50 dark:bg-brand-500/10 text-brand-600 dark:text-brand-400 px-2 py-0.5 rounded font-mono"
            >
              {{ name }}
            </span>
            <!-- TTL badge -->
            <span class="text-xs px-2 py-0.5 rounded bg-indigo-100 dark:bg-indigo-500/15 text-indigo-700 dark:text-indigo-400 font-medium">
              <i class="pi pi-clock text-[10px] mr-0.5" />
              {{ formattedTtl }}
            </span>
          </div>

          <!-- Info row -->
          <div class="flex flex-wrap items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
            <!-- Expiration -->
            <div class="flex items-center gap-1.5">
              <i class="pi pi-calendar text-[10px]" />
              <span v-if="client.expires_at">
                Expire le {{ formatDate(client.expires_at) }}
              </span>
              <span
                v-else
                class="px-2 py-0.5 rounded-full font-medium bg-success-50 text-success-600 dark:bg-success-500/15 dark:text-success-400"
              >
                Permanent
              </span>
            </div>
            <!-- Created by -->
            <div v-if="client.created_by" class="flex items-center gap-1.5">
              <i class="pi pi-user text-[10px]" />
              <span>{{ client.created_by }}</span>
            </div>
            <!-- Redirect URI -->
            <div v-if="client.redirect_uris?.length" class="flex items-center gap-1.5">
              <i class="pi pi-external-link text-[10px]" />
              <span class="truncate max-w-[250px]">{{ client.redirect_uris[0] }}</span>
            </div>
          </div>
        </div>

        <!-- Right section: action buttons (vertical on large screens) -->
        <div class="flex lg:flex-col items-center gap-1 shrink-0">
          <button
            class="p-1.5 rounded hover:bg-gray-100 dark:hover:bg-white/5 text-brand-500"
            title="Copier le Client ID"
            @click="clipboard.copy(client.id, 'Client ID')"
          >
            <i class="pi pi-copy text-sm" />
          </button>
          <button
            v-if="client.is_active"
            class="p-1.5 rounded hover:bg-gray-100 dark:hover:bg-white/5 text-gray-500 dark:text-gray-400"
            title="Modifier le scope"
            @click="emit('edit', client)"
          >
            <i class="pi pi-pencil text-sm" />
          </button>
          <button
            v-if="client.is_active"
            class="p-1.5 rounded hover:bg-gray-100 dark:hover:bg-white/5 text-orange-500 dark:text-orange-400"
            title="Révoquer"
            @click="emit('revoke', client.id)"
          >
            <i class="pi pi-times text-sm" />
          </button>
          <button
            class="p-1.5 rounded hover:bg-gray-100 dark:hover:bg-white/5 text-red-500 dark:text-error-400"
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
