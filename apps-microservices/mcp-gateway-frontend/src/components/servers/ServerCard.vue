<template>
  <div class="bg-white rounded-lg border border-gray-200 shadow-sm hover:shadow-md transition-shadow">
    <div class="p-5">
      <!-- Header -->
      <div class="flex items-center justify-between mb-4">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center shrink-0">
            <i class="pi pi-server text-lg" />
          </div>
          <div class="min-w-0">
            <div class="flex items-center gap-2">
              <h3 class="text-sm font-semibold text-gray-900 truncate max-w-[200px]">
                {{ server.name }}
              </h3>
              <span
                class="inline-block w-2.5 h-2.5 rounded-full shrink-0"
                :class="healthDotClass"
                :title="'Santé: ' + (server.health_status || 'inconnu')"
              />
            </div>
          </div>
        </div>
        <div class="flex items-center gap-1.5">
          <span
            class="text-xs px-2 py-0.5 rounded-full font-medium"
            :class="server.mcp_transport === 'stdio'
              ? 'bg-purple-100 text-purple-700'
              : 'bg-cyan-100 text-cyan-700'"
          >
            {{ server.mcp_transport === 'stdio' ? 'Stdio' : 'HTTP' }}
          </span>
          <span
            class="text-xs px-2 py-0.5 rounded-full font-medium"
            :class="server.is_active
              ? 'bg-green-100 text-green-700'
              : 'bg-gray-100 text-gray-500'"
          >
            {{ server.is_active ? 'Actif' : 'Inactif' }}
          </span>
        </div>
      </div>

      <!-- Tags -->
      <div v-if="server.tags?.length" class="flex flex-wrap gap-1 mb-3">
        <span
          v-for="tag in server.tags"
          :key="tag"
          class="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full"
        >
          {{ tag }}
        </span>
      </div>

      <!-- Stats -->
      <p class="text-xs text-gray-500 mb-3">
        {{ server.tools_count }} outils · {{ server.resources_count }} ressources · {{ server.prompts_count }} prompts
      </p>

      <!-- Error -->
      <p v-if="server.last_error && server.health_status !== 'healthy'" class="text-xs text-red-600 mb-3 truncate">
        {{ server.last_error }}
      </p>

      <!-- Actions -->
      <div class="flex items-center justify-between pt-3 border-t border-gray-100">
        <div class="flex items-center gap-1">
          <button
            class="p-1.5 rounded hover:bg-gray-100 text-gray-500"
            :title="server.is_active ? 'Désactiver' : 'Activer'"
            @click="emit('toggle', server.id, !server.is_active)"
          >
            <i :class="server.is_active ? 'pi pi-eye' : 'pi pi-eye-slash'" class="text-sm" />
          </button>
          <button
            class="p-1.5 rounded hover:bg-gray-100 text-gray-500"
            title="Modifier"
            @click="emit('edit', server)"
          >
            <i class="pi pi-pencil text-sm" />
          </button>
          <button
            class="p-1.5 rounded hover:bg-gray-100 text-gray-500"
            title="Découvrir"
            :disabled="discovering"
            @click="handleDiscover"
          >
            <i class="pi pi-refresh text-sm" :class="{ 'pi-spin': discovering }" />
          </button>
          <button
            class="p-1.5 rounded hover:bg-gray-100 text-red-500"
            title="Supprimer"
            @click="emit('delete', server.id)"
          >
            <i class="pi pi-trash text-sm" />
          </button>
        </div>
        <button
          class="text-xs text-blue-600 hover:text-blue-800 font-medium"
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

const props = defineProps<{ server: Server }>()

const emit = defineEmits<{
  toggle: [id: string, enable: boolean]
  edit: [server: Server]
  delete: [id: string]
  details: [id: string]
  discover: [id: string]
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

async function handleDiscover() {
  discovering.value = true
  emit('discover', props.server.id)
  setTimeout(() => { discovering.value = false }, 3000)
}
</script>
