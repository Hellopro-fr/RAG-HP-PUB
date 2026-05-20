<template>
  <div
    class="rounded-lg border bg-white dark:bg-gray-900 transition-all duration-200 motion-reduce:transition-none"
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
            width="28"
            height="28"
            class="h-7 w-7 object-contain"
          />
          <Server v-else class="h-5 w-5" aria-hidden="true" />
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
        :aria-expanded="expanded"
        class="mt-4 flex w-full min-h-[44px] items-center justify-between rounded-md px-3 py-2 text-sm font-medium text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-white/5 hover:text-gray-900 dark:hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/40 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-gray-900 transition-colors motion-reduce:transition-none"
        @click="$emit('toggle-expand', server.id)"
      >
        <span>Voir les outils ({{ (server.tools || []).length }})</span>
        <ChevronUp v-if="expanded" class="h-4 w-4" aria-hidden="true" />
        <ChevronDown v-else class="h-4 w-4" aria-hidden="true" />
      </button>

      <div
        v-if="expanded"
        class="mt-4 space-y-2 border-t border-gray-200 dark:border-gray-800 pt-4"
      >
        <h4 class="text-sm font-semibold text-gray-900 dark:text-white mb-2">
          Outils demandés
        </h4>
        <label
          v-for="tool in server.tools || []"
          :key="`${server.id}:${tool.name}`"
          class="flex items-start gap-3 rounded-md p-3 min-h-[44px] bg-gray-50 dark:bg-gray-800/50 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800 focus-within:ring-2 focus-within:ring-brand-500/40 transition-colors motion-reduce:transition-none"
          :class="preConfigured ? 'cursor-default' : ''"
        >
          <Check
            v-if="preConfigured"
            class="h-4 w-4 shrink-0 text-success-500 mt-0.5"
            aria-hidden="true"
          />
          <input
            v-else
            type="checkbox"
            :checked="isToolChecked(tool.name)"
            class="mt-0.5 h-4 w-4 rounded border-gray-300 text-brand-500 dark:border-gray-700 focus:ring-2 focus:ring-brand-500/40 focus:ring-offset-0"
            @change="$emit('toggle-tool', server.id, tool.name)"
          />
          <div class="flex-1 min-w-0 text-sm">
            <code
              class="text-xs font-mono bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded text-gray-900 dark:text-white"
            >
              {{ tool.name }}
            </code>
            <span v-if="tool.description" class="text-gray-600 dark:text-gray-400">
              -- {{ truncate(tool.description) }}
            </span>
          </div>
        </label>
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

function truncate(text: string): string {
  return text.length > 150 ? text.slice(0, 150) + '…' : text
}
</script>
