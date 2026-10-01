<template>
  <div
    class="rounded-lg border bg-white dark:bg-gray-900 transition-colors"
    :class="[
      expanded ? 'ring-1 ring-brand-500/30' : '',
      'border-gray-200 dark:border-gray-700',
    ]"
  >
    <!-- Row header -->
    <div
      class="flex items-center gap-2 px-3 py-2 border-b cursor-pointer"
      :class="
        expanded
          ? 'border-gray-100 dark:border-gray-800 bg-brand-50/40 dark:bg-brand-500/5'
          : 'border-transparent hover:bg-gray-50 dark:hover:bg-gray-800/50'
      "
      @click="toggleExpand"
    >
      <span
        class="inline-flex items-center justify-center w-6 h-6 rounded-full bg-brand-500 text-white text-xs font-semibold shrink-0"
      >
        {{ index + 1 }}
      </span>

      <span
        class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide shrink-0"
        :class="badgeClass"
      >
        <i :class="badgeIcon" class="text-[9px]" />
        {{ badgeLabel }}
      </span>

      <div class="min-w-0 flex-1">
        <p class="text-sm font-medium text-gray-800 dark:text-gray-200 truncate font-mono">
          <template v-if="isComplete">
            <code>{{ selfTableName }}.{{ modelValue.self_col }}</code>
            <i class="pi pi-arrow-right text-gray-400 text-[10px] mx-1" />
            <code>{{ modelValue.target_table }}.{{ modelValue.target_col }}</code>
          </template>
          <template v-else>
            <span class="text-gray-400 text-xs italic">
              Relation incomplete — completer dans le bloc
            </span>
          </template>
        </p>
      </div>

      <div class="flex items-center gap-0.5 shrink-0">
        <button
          v-if="isAdmin"
          type="button"
          class="p-1.5 rounded text-gray-400 hover:text-error-500 hover:bg-error-50 dark:hover:bg-error-500/10"
          title="Supprimer cette relation"
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

    <!-- Expanded body — 3 selects -->
    <div v-if="expanded" class="p-4" @click.stop>
      <div class="grid grid-cols-1 md:grid-cols-12 gap-2 items-end">
        <div class="md:col-span-4">
          <label class="block text-[10px] uppercase text-gray-400 mb-0.5">
            Champ de cette table
          </label>
          <Select
            :model-value="modelValue.self_col"
            :options="fields"
            option-label="field_name"
            option-value="field_name"
            :disabled="!isAdmin"
            filter
            show-clear
            placeholder="— champ —"
            class="w-full"
            @update:model-value="onSelfColChange"
          />
        </div>
        <div class="md:col-span-1 flex items-center justify-center pb-1">
          <i class="pi pi-arrow-right text-gray-400 text-xs" />
        </div>
        <div class="md:col-span-4">
          <label class="block text-[10px] uppercase text-gray-400 mb-0.5">
            Table cible (active)
          </label>
          <Select
            :model-value="modelValue.target_table"
            :options="availableTargetTables"
            option-label="table_name"
            option-value="table_name"
            :disabled="!isAdmin"
            filter
            show-clear
            placeholder="— table —"
            class="w-full"
            @update:model-value="onTargetTableChange"
          />
        </div>
        <div class="md:col-span-3">
          <label class="block text-[10px] uppercase text-gray-400 mb-0.5">
            Champ cible
          </label>
          <Select
            :model-value="modelValue.target_col"
            :options="targetColOptions"
            :disabled="!isAdmin || !modelValue.target_table"
            filter
            show-clear
            placeholder="— champ —"
            class="w-full"
            @update:model-value="onTargetColChange"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import Select from 'primevue/select';
import type { BDDUsedField, BDDUsedTable } from '@/types/bdd';

export interface BDDRelationDraft {
  self_col: string;
  target_table: string;
  target_col: string;
}

const props = defineProps<{
  modelValue: BDDRelationDraft;
  selfTableName: string;
  fields: BDDUsedField[];
  availableTargetTables: BDDUsedTable[];
  isAdmin: boolean;
  index: number;
  defaultExpanded?: boolean;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: BDDRelationDraft): void;
  (e: 'remove'): void;
}>();

const expanded = ref<boolean>(props.defaultExpanded ?? !isCompleteValue(props.modelValue));

function toggleExpand() {
  expanded.value = !expanded.value;
}

const isComplete = computed(() => isCompleteValue(props.modelValue));

function isCompleteValue(v: BDDRelationDraft): boolean {
  return Boolean(v.self_col && v.target_table && v.target_col);
}

const badgeIcon = computed(() =>
  isComplete.value ? 'pi pi-link' : 'pi pi-pencil',
);

const badgeClass = computed(() =>
  isComplete.value
    ? 'bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-200'
    : 'bg-warning-50 text-warning-700 dark:bg-warning-500/15 dark:text-warning-300',
);

const badgeLabel = computed(() =>
  isComplete.value ? 'Relation' : 'A completer',
);

const targetColOptions = computed<string[]>(() => {
  const name = props.modelValue.target_table;
  if (!name) return [];
  const t = props.availableTargetTables.find((x) => x.table_name === name);
  if (!t) return [];
  return t.fields.map((f) => f.field_name).slice().sort();
});

function onSelfColChange(value: string | null) {
  emit('update:modelValue', { ...props.modelValue, self_col: value ?? '' });
}

function onTargetTableChange(value: string | null) {
  // Reset target_col when the target table changes — old col may not
  // exist on the new table.
  emit('update:modelValue', {
    ...props.modelValue,
    target_table: value ?? '',
    target_col: '',
  });
}

function onTargetColChange(value: string | null) {
  emit('update:modelValue', { ...props.modelValue, target_col: value ?? '' });
}
</script>
