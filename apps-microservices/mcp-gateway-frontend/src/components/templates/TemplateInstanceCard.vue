<template>
  <div class="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 shadow-theme-xs hover:shadow-theme-md transition-shadow">
    <div class="p-5">
      <!-- Row 1: Name + status + port + created_at -->
      <div class="flex items-start justify-between gap-4">
        <div class="flex items-center gap-3 min-w-0 flex-wrap">
          <div class="w-10 h-10 rounded-full bg-brand-50 dark:bg-brand-500/15 text-brand-500 flex items-center justify-center shrink-0">
            <i class="pi pi-box text-lg" />
          </div>
          <div class="min-w-0">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white truncate max-w-[260px]">
              {{ inst.name }}
            </h3>
            <div class="flex flex-wrap items-center gap-2 mt-1 text-xs text-gray-500 dark:text-gray-400">
              <span v-if="inst.runner_port" class="font-mono">port {{ inst.runner_port }}</span>
              <span class="flex items-center gap-1">
                <i class="pi pi-calendar text-[10px]" />
                {{ formatDate(inst.created_at) }}
              </span>
              <span v-if="inst.created_by" class="flex items-center gap-1">
                <i class="pi pi-user text-[10px]" />
                {{ inst.created_by }}
              </span>
            </div>
          </div>
        </div>
        <span
          class="text-xs px-2 py-0.5 rounded-full font-medium shrink-0"
          :class="statusClass"
        >
          {{ statusLabel }}
        </span>
      </div>

      <!-- Last error (truncated) -->
      <details
        v-if="inst.runner_last_error"
        class="mt-3 text-xs"
      >
        <summary class="cursor-pointer text-error-600 dark:text-error-400 truncate">
          <i class="pi pi-exclamation-triangle text-[10px] mr-1" />
          {{ inst.runner_last_error }}
        </summary>
        <pre class="mt-2 whitespace-pre-wrap break-words bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded p-2 text-[11px] text-gray-700 dark:text-gray-300 max-h-40 overflow-y-auto">{{ inst.runner_last_error }}</pre>
      </details>

      <!-- Action buttons -->
      <div class="flex items-center justify-end gap-1 mt-4 pt-4 border-t border-gray-100 dark:border-gray-800">
        <button
          v-if="inst.runner_status === 'failed'"
          class="px-3 py-1.5 text-xs font-medium rounded hover:bg-gray-100 dark:hover:bg-white/5 text-gray-600 dark:text-gray-400 flex items-center gap-1.5"
          title="Voir les logs"
          @click="emit('logs', inst)"
        >
          <i class="pi pi-file text-xs" />
          Voir les logs
        </button>
        <button
          class="px-3 py-1.5 text-xs font-medium rounded hover:bg-gray-100 dark:hover:bg-white/5 text-gray-600 dark:text-gray-400 flex items-center gap-1.5"
          title="Remplacer le fichier JSON de credentials"
          @click="emit('rotate', inst)"
        >
          <i class="pi pi-sync text-xs" />
          Rotate JSON
        </button>
        <button
          class="px-3 py-1.5 text-xs font-medium rounded hover:bg-gray-100 dark:hover:bg-white/5 text-gray-600 dark:text-gray-400 flex items-center gap-1.5"
          title="Redémarrer l'instance"
          @click="emit('restart', inst)"
        >
          <i class="pi pi-refresh text-xs" />
          Restart
        </button>
        <button
          class="px-3 py-1.5 text-xs font-medium rounded text-white bg-error-600 hover:bg-error-700 flex items-center gap-1.5"
          title="Supprimer l'instance"
          @click="emit('delete', inst)"
        >
          <i class="pi pi-trash text-xs" />
          Delete
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { TemplateInstance, InstanceStatus } from '@/types/templates'

const props = defineProps<{ inst: TemplateInstance }>()

const emit = defineEmits<{
  restart: [inst: TemplateInstance]
  delete: [inst: TemplateInstance]
  rotate: [inst: TemplateInstance]
  logs: [inst: TemplateInstance]
}>()

const STATUS_LABELS: Record<InstanceStatus, string> = {
  running: 'En cours',
  pending: 'En attente',
  failed: 'Échec',
  stopped: 'Arrêté'
}

const STATUS_CLASSES: Record<InstanceStatus, string> = {
  running: 'bg-success-50 text-success-600 dark:bg-success-500/15 dark:text-success-400',
  pending: 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400',
  failed: 'bg-error-50 text-error-600 dark:bg-error-500/15 dark:text-error-400',
  stopped: 'bg-gray-100 text-gray-500 dark:bg-white/5 dark:text-gray-400'
}

const statusLabel = computed(() => STATUS_LABELS[props.inst.runner_status] ?? props.inst.runner_status)
const statusClass = computed(() => STATUS_CLASSES[props.inst.runner_status] ?? STATUS_CLASSES.stopped)

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('fr-FR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}
</script>
