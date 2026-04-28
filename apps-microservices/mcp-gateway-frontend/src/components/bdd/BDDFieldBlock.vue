<template>
  <div
    class="rounded-lg border bg-white dark:bg-gray-900 transition-colors"
    :class="[
      expanded ? 'ring-1 ring-brand-500/30' : '',
      'border-gray-200 dark:border-gray-700',
    ]"
  >
    <!-- Row header (mirrors InstructionRowBuilder row header) -->
    <div
      class="flex items-center gap-2 px-3 py-2 border-b cursor-pointer"
      :class="
        expanded
          ? 'border-gray-100 dark:border-gray-800 bg-brand-50/40 dark:bg-brand-500/5'
          : 'border-transparent hover:bg-gray-50 dark:hover:bg-gray-800/50'
      "
      @click="toggleExpand"
    >
      <!-- Drag handle (admin only) -->
      <span
        v-if="isAdmin"
        class="field-drag-handle cursor-grab active:cursor-grabbing p-1 text-gray-400 hover:text-gray-600"
        title="Glisser pour reorganiser (cosmetique)"
        @click.stop
      >
        <i class="pi pi-bars text-xs" />
      </span>

      <span
        class="inline-flex items-center justify-center w-6 h-6 rounded-full bg-brand-500 text-white text-xs font-semibold shrink-0"
      >
        {{ index + 1 }}
      </span>

      <!-- Type / nullable badge -->
      <span
        class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide shrink-0"
        :class="badgeClass"
      >
        <i :class="badgeIcon" class="text-[9px]" />
        {{ badgeLabel }}
      </span>

      <div class="min-w-0 flex-1">
        <p class="text-sm font-medium text-gray-800 dark:text-gray-200 truncate">
          <code class="font-mono">{{ modelValue.field_name }}</code>
        </p>
        <p class="text-xs text-gray-500 dark:text-gray-400 mt-0.5 truncate">
          {{ previewText(modelValue.description) || 'Pas de description' }}
        </p>
      </div>

      <div class="flex items-center gap-0.5 shrink-0">
        <button
          v-if="isAdmin"
          type="button"
          class="p-1.5 rounded text-gray-400 hover:text-error-500 hover:bg-error-50 dark:hover:bg-error-500/10"
          title="Supprimer ce champ"
          @click.stop="emit('remove')"
        >
          <i class="pi pi-times text-xs" />
        </button>
        <i
          class="pi ml-1 text-xs text-gray-400 transition-transform"
          :class="expanded ? 'pi-chevron-up' : 'pi-chevron-down'"
        />
      </div>
    </div>

    <!-- Expanded body — description WYSIWYG only -->
    <div v-if="expanded" class="p-4 space-y-3" @click.stop>
      <div>
        <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
          Description (HTML)
        </label>
        <WysiwygEditor
          v-if="isAdmin"
          :model-value="modelValue.description || ''"
          placeholder="Description du champ (utilisee dans la doc LLM)"
          @update:model-value="onDescriptionChange"
        />
        <div
          v-else
          class="rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 px-3 py-2 text-sm text-gray-700 dark:text-gray-300 prose prose-sm max-w-none dark:prose-invert"
          v-html="modelValue.description || '<em class=\'text-gray-400\'>Aucune description</em>'"
        />
        <p class="text-[11px] text-gray-400 mt-1">
          Le HTML est transmis tel quel a la doc LLM associee a la table.
        </p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import WysiwygEditor from '@/components/shared/WysiwygEditor.vue';
import type { BDDUsedField, BDDCatalogField } from '@/types/bdd';

const props = defineProps<{
  modelValue: BDDUsedField;
  catalogField?: BDDCatalogField | null;
  isAdmin: boolean;
  index: number;
  defaultExpanded?: boolean;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: BDDUsedField): void;
  (e: 'remove'): void;
}>();

const expanded = ref<boolean>(props.defaultExpanded ?? false);

function toggleExpand() {
  expanded.value = !expanded.value;
}

const badgeIcon = computed(() => {
  if (props.catalogField) return 'pi pi-bolt';
  if (props.catalogField === null) return 'pi pi-exclamation-triangle';
  return 'pi pi-question-circle';
});

const badgeClass = computed(() => {
  if (props.catalogField) {
    return 'bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-200';
  }
  if (props.catalogField === null) {
    return 'bg-warning-50 text-warning-700 dark:bg-warning-500/15 dark:text-warning-300';
  }
  return 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300';
});

const badgeLabel = computed(() => {
  if (props.catalogField) {
    const t = props.catalogField.field_type || 'unknown';
    const n = props.catalogField.is_nullable ? 'null' : 'not null';
    return `${t} / ${n}`;
  }
  if (props.catalogField === null) return 'Catalogue indispo';
  return 'Hors catalogue';
});

function previewText(html: string | undefined): string {
  if (!html) return '';
  return html
    .replace(/<[^>]*>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 70);
}

function onDescriptionChange(description: string) {
  emit('update:modelValue', { ...props.modelValue, description });
}
</script>

<style scoped>
.field-ghost {
  opacity: 0.35;
  background: rgb(219 234 254);
}
</style>
