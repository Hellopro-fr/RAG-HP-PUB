<template>
  <select
    :id="id"
    :value="modelValue"
    :disabled="disabled"
    :class="selectClass"
    @change="onChange"
  >
    <slot />
  </select>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = withDefaults(
  defineProps<{
    modelValue?: string | number;
    id?: string;
    disabled?: boolean;
    error?: boolean;
  }>(),
  { disabled: false, error: false },
);

const emit = defineEmits<{
  'update:modelValue': [value: string];
}>();

function onChange(e: Event) {
  emit('update:modelValue', (e.target as HTMLSelectElement).value);
}

const selectClass = computed(() => [
  'h-11 w-full rounded-lg border bg-transparent px-4 py-2.5 text-sm shadow-theme-xs appearance-none',
  'text-gray-800 dark:text-white/90',
  'focus:outline-hidden focus:ring-3',
  props.error
    ? 'border-red-400 focus:border-red-400 focus:ring-red-500/10 dark:border-red-500'
    : 'border-gray-300 focus:border-brand-300 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900',
  props.disabled ? 'opacity-50 cursor-not-allowed' : '',
]);
</script>
