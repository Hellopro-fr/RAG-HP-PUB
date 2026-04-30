<template>
  <div class="flex items-center gap-3">
    <button
      type="button"
      :disabled="disabled"
      class="h-10 inline-flex items-center gap-1.5 px-4 text-xs font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-white/5 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700 transition shrink-0 disabled:opacity-50 disabled:cursor-not-allowed"
      @click="emit('export')"
    >
      <i class="pi pi-download text-xs" />
      {{ exportLabel }}
    </button>
    <div
      class="h-10 flex-1 min-w-0 flex items-center justify-center gap-2 px-4 rounded-lg border-2 border-dashed transition-colors cursor-pointer"
      :class="
        dragOver
          ? 'border-brand-400 bg-brand-50/50 dark:bg-brand-500/5 text-brand-600 dark:text-brand-400'
          : 'border-gray-300 dark:border-gray-700 text-gray-500 dark:text-gray-400 hover:border-gray-400 dark:hover:border-gray-600'
      "
      @dragover.prevent="dragOver = true"
      @dragleave="dragOver = false"
      @drop.prevent="onDrop"
      @click="fileInput?.click()"
    >
      <i :class="busy ? 'pi pi-spinner pi-spin' : 'pi pi-upload'" class="text-xs" />
      <span class="text-xs font-medium">{{ importLabel }}</span>
      <input
        ref="fileInput"
        type="file"
        accept="application/json,.json"
        class="hidden"
        @change="onFilePicked"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';

withDefaults(
  defineProps<{
    exportLabel?: string;
    importLabel?: string;
    disabled?: boolean;
    busy?: boolean;
  }>(),
  {
    exportLabel: 'Exporter JSON',
    importLabel: 'Glisser un fichier JSON ici ou cliquer pour importer',
    disabled: false,
    busy: false,
  },
);

const emit = defineEmits<{
  (e: 'export'): void;
  (e: 'import-file', file: File): void;
}>();

const dragOver = ref(false);
const fileInput = ref<HTMLInputElement | null>(null);

function onDrop(event: DragEvent) {
  dragOver.value = false;
  const file = event.dataTransfer?.files?.[0];
  if (file) emit('import-file', file);
}

function onFilePicked(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = '';
  if (file) emit('import-file', file);
}
</script>
