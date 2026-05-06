<template>
  <textarea
    :id="id"
    :value="modelValue"
    :placeholder="placeholder"
    :disabled="disabled"
    :rows="rows"
    :class="textareaClass"
    @input="onInput"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = withDefaults(
  defineProps<{
    modelValue?: string;
    id?: string;
    placeholder?: string;
    disabled?: boolean;
    rows?: number;
    error?: boolean;
    monospace?: boolean;
  }>(),
  { rows: 4, disabled: false, error: false, monospace: false },
);

const emit = defineEmits<{
  'update:modelValue': [value: string];
}>();

function onInput(e: Event) {
  emit('update:modelValue', (e.target as HTMLTextAreaElement).value);
}

const textareaClass = computed(() => [
  'w-full rounded-lg border bg-transparent px-4 py-2.5 text-sm shadow-theme-xs',
  'text-gray-800 dark:text-white/90',
  'placeholder:text-gray-400 dark:placeholder:text-white/30',
  'focus:outline-hidden focus:ring-3',
  props.error
    ? 'border-red-400 focus:border-red-400 focus:ring-red-500/10 dark:border-red-500'
    : 'border-gray-300 focus:border-brand-300 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900',
  props.monospace ? 'font-mono' : '',
  props.disabled ? 'opacity-50 cursor-not-allowed' : '',
]);
</script>
