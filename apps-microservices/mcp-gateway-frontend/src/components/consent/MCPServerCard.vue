<template>
  <div
    class="rounded-lg border bg-white dark:bg-gray-900 transition-all duration-200"
    :class="enabled ? 'border-brand-500/50 shadow-sm' : 'border-gray-200 dark:border-gray-800'"
  >
    <div class="p-5">
      <div class="flex items-start gap-4">
        <div
          class="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg overflow-hidden"
          :class="
            enabled
              ? 'bg-brand-100 dark:bg-brand-500/20 text-brand-700 dark:text-brand-300'
              : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400'
          "
        >
          <img
            v-if="server.icon"
            :src="server.icon"
            :alt="server.name"
            class="h-7 w-7 object-contain"
          />
          <Server v-else class="h-5 w-5" />
        </div>
        <div class="space-y-1.5 flex-1">
          <div class="flex flex-wrap items-center gap-2">
            <h3 class="font-semibold text-gray-900 dark:text-white">{{ server.name }}</h3>
            <Badge v-if="preConfigured" color="primary" size="sm">Requis</Badge>
          </div>
        </div>
      </div>

      <button
        type="button"
        class="mt-4 flex w-full items-center justify-between rounded-md px-3 py-2 text-sm font-medium text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-white/5 hover:text-gray-900 dark:hover:text-white transition-colors"
        @click="$emit('toggle-expand', server.id)"
      >
        <span>Voir les outils ({{ (server.tools || []).length }})</span>
        <ChevronUp v-if="expanded" class="h-4 w-4" />
        <ChevronDown v-else class="h-4 w-4" />
      </button>

      <div
        v-if="expanded"
        class="mt-4 space-y-2 border-t border-gray-200 dark:border-gray-800 pt-4"
      >
        <h4 class="text-sm font-semibold text-gray-900 dark:text-white mb-2">
          Outils demandés
        </h4>
        <div
          v-for="tool in server.tools || []"
          :key="`${server.id}:${tool.name}`"
          class="flex items-start gap-3 rounded-md p-3 bg-gray-50 dark:bg-gray-800/50"
        >
          <Check
            v-if="preConfigured"
            class="h-4 w-4 shrink-0 text-success-500 mt-0.5"
          />
          <input
            v-else
            type="checkbox"
            :checked="isToolChecked(tool.name)"
            class="mt-0.5 rounded border-gray-300 text-brand-500 dark:border-gray-700"
            @change="$emit('toggle-tool', server.id, tool.name)"
          />
          <div class="flex-1 min-w-0">
            <code
              class="text-xs font-mono bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded text-gray-900 dark:text-white"
            >
              {{ tool.name }}
            </code>
            <p
              v-if="tool.description"
              class="text-sm text-gray-600 dark:text-gray-400 mt-1"
            >
              {{ tool.description }}
            </p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Server, ChevronDown, ChevronUp, Check } from 'lucide-vue-next'
import Badge from '@/components/ui/Badge.vue'
import type { AuthorizeServer } from '@/types/oauth2'

const props = defineProps<{
  server: AuthorizeServer
  preConfigured: boolean
  expanded: boolean
  selectedTools: Set<string> | undefined
}>()

defineEmits<{
  'toggle-tool': [serverId: string, toolName: string]
  'toggle-expand': [serverId: string]
}>()

const enabled = computed(() => {
  if (props.preConfigured) return true
  const tools = props.server.tools || []
  const selected = props.selectedTools
  return !!selected && selected.size > 0 && selected.size === tools.length
})

function isToolChecked(toolName: string): boolean {
  return !!props.selectedTools && props.selectedTools.has(toolName)
}
</script>
