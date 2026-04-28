<template>
  <div
    class="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 transition-colors"
  >
    <!-- Header line -->
    <div class="flex items-center gap-2 px-3 py-2 border-b border-transparent">
      <!-- Drag handle (admin only) -->
      <span
        v-if="isAdmin"
        class="field-drag-handle cursor-grab active:cursor-grabbing p-1 text-gray-400 hover:text-gray-600"
        title="Glisser pour reorganiser (cosmetique)"
      >
        <i class="pi pi-bars text-xs" />
      </span>

      <code
        class="px-2 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-xs font-mono text-gray-800 dark:text-gray-200 shrink-0"
      >
        {{ modelValue.field_name }}
      </code>

      <small class="text-xs text-gray-500 dark:text-gray-400 truncate min-w-0 flex-1">
        <template v-if="catalogField">
          <span class="font-mono">{{ catalogField.field_type || 'unknown' }}</span>
          <span class="mx-1">/</span>
          <span>{{ catalogField.is_nullable ? 'nullable' : 'not null' }}</span>
        </template>
        <template v-else-if="catalogField === null">
          <span class="italic text-gray-400">Catalogue indisponible</span>
        </template>
        <template v-else>
          <span class="italic text-gray-400">Hors catalogue</span>
        </template>
      </small>

      <button
        v-if="isAdmin"
        type="button"
        class="p-1.5 rounded text-gray-400 hover:text-error-500 hover:bg-error-50 dark:hover:bg-error-500/10 shrink-0"
        title="Supprimer ce champ"
        @click="emit('remove')"
      >
        <i class="pi pi-trash text-xs" />
      </button>
    </div>

    <!-- Description body -->
    <div class="p-3">
      <WysiwygEditor
        :model-value="modelValue.description || ''"
        :placeholder="'Description du champ (utilisee dans la doc LLM)'"
        @update:model-value="onDescriptionChange"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import WysiwygEditor from '@/components/shared/WysiwygEditor.vue';
import type { BDDUsedField, BDDCatalogField } from '@/types/bdd';

const props = defineProps<{
  modelValue: BDDUsedField;
  catalogField?: BDDCatalogField | null;
  isAdmin: boolean;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: BDDUsedField): void;
  (e: 'remove'): void;
}>();

function onDescriptionChange(description: string) {
  emit('update:modelValue', { ...props.modelValue, description });
}
</script>
