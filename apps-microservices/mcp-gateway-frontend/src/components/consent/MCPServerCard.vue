<template>
  <div>
    <button
      type="button"
      :aria-expanded="expanded"
      class="flex w-full items-center gap-3 px-4 py-3 min-h-[44px] text-left bg-white dark:bg-gray-900 hover:bg-gray-50 dark:hover:bg-gray-800/50 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-500/40 transition-colors motion-reduce:transition-none"
      @click="$emit('toggle-expand', server.id)"
    >
      <div
        class="flex h-8 w-8 shrink-0 items-center justify-center rounded-md overflow-hidden bg-gray-100 dark:bg-gray-800"
      >
        <img
          v-if="server.icon"
          :src="server.icon"
          :alt="server.name"
          width="24"
          height="24"
          class="h-6 w-6 object-contain"
        />
        <Server v-else class="h-4 w-4 text-gray-600 dark:text-gray-400" aria-hidden="true" />
      </div>

      <div class="flex-1 min-w-0 flex items-center gap-2">
        <span class="font-medium text-gray-900 dark:text-white truncate">{{ server.name }}</span>
        <Badge v-if="preConfigured" color="primary" size="sm">Requis</Badge>
        <span class="text-xs text-gray-500 dark:text-gray-400">
          ({{ (server.tools || []).length }} outil{{ (server.tools || []).length !== 1 ? 's' : '' }})
        </span>
      </div>

      <ChevronUp v-if="expanded" class="h-4 w-4 text-gray-500 dark:text-gray-400 shrink-0" aria-hidden="true" />
      <ChevronDown v-else class="h-4 w-4 text-gray-500 dark:text-gray-400 shrink-0" aria-hidden="true" />
    </button>

    <div
      v-if="expanded"
      class="px-4 pb-3 pt-1 bg-gray-50/50 dark:bg-gray-800/30 space-y-1"
    >
      <label
        v-for="tool in server.tools || []"
        :key="`${server.id}:${tool.name}`"
        class="flex items-start gap-3 px-3 py-2 min-h-[44px] rounded-md cursor-pointer hover:bg-white dark:hover:bg-gray-800 focus-within:ring-2 focus-within:ring-brand-500/40 transition-colors motion-reduce:transition-none"
        :class="preConfigured ? 'cursor-default' : ''"
      >
        <Check
          v-if="preConfigured"
          class="h-4 w-4 shrink-0 text-success-500 mt-1"
          aria-hidden="true"
        />
        <input
          v-else
          type="checkbox"
          :checked="isToolChecked(tool.name)"
          class="mt-1 h-4 w-4 rounded border-gray-300 text-brand-500 dark:border-gray-700 focus:ring-2 focus:ring-brand-500/40 focus:ring-offset-0"
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
</template>

<script setup lang="ts">
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

function isToolChecked(toolName: string): boolean {
  return !!props.selectedTools && props.selectedTools.has(toolName)
}

function truncate(text: string): string {
  return text.length > 150 ? text.slice(0, 150) + '…' : text
}
</script>
