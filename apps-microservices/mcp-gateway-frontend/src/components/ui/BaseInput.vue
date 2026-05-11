<template>
  <input
    :id="id"
    :type="type"
    :value="modelValue"
    :placeholder="placeholder"
    :disabled="disabled"
    :required="required"
    :autocomplete="autocomplete"
    :class="inputClass"
    @input="onInput"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = withDefaults(
  defineProps<{
    modelValue?: string | number;
    id?: string;
    type?: string;
    placeholder?: string;
    disabled?: boolean;
    required?: boolean;
    autocomplete?: string;
    error?: boolean;
  }>(),
  { type: 'text', disabled: false, required: false, error: false },
);

const emit = defineEmits<{
  'update:modelValue': [value: string];
}>();

function onInput(e: Event) {
  emit('update:modelValue', (e.target as HTMLInputElement).value);
}

const inputClass = computed(() => [
  'h-11 w-full rounded-lg border bg-transparent px-4 py-2.5 text-sm shadow-theme-xs',
  'text-gray-800 dark:text-white/90',
  'placeholder:text-gray-400 dark:placeholder:text-white/30',
  'focus:outline-hidden focus:ring-3',
  props.error
    ? 'border-red-400 focus:border-red-400 focus:ring-red-500/10 dark:border-red-500'
    : 'border-gray-300 focus:border-brand-300 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900',
  props.disabled ? 'opacity-50 cursor-not-allowed' : '',
]);
</script>
