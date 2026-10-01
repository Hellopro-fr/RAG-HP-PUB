<template>
  <button :type="type" :disabled="disabled || loading" :class="buttonClass" @click="onClick">
    <i v-if="loading" class="pi pi-spinner pi-spin" :class="$slots.default ? 'mr-1' : ''" />
    <slot />
  </button>
</template>

<script setup lang="ts">
import { computed } from 'vue';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';
type Size = 'sm' | 'md';

const props = withDefaults(
  defineProps<{
    type?: 'button' | 'submit' | 'reset';
    variant?: Variant;
    size?: Size;
    disabled?: boolean;
    loading?: boolean;
    fullWidth?: boolean;
  }>(),
  { type: 'button', variant: 'primary', size: 'md', disabled: false, loading: false, fullWidth: false },
);

const emit = defineEmits<{ click: [e: MouseEvent] }>();
function onClick(e: MouseEvent) {
  emit('click', e);
}

const buttonClass = computed(() => {
  const base = [
    'inline-flex items-center justify-center font-medium rounded-md',
    'transition-colors disabled:opacity-50 disabled:cursor-not-allowed',
    props.fullWidth ? 'w-full' : '',
  ];
  const sizes: Record<Size, string> = {
    sm: 'h-9 px-3 text-xs',
    md: 'h-10 px-4 text-sm',
  };
  const variants: Record<Variant, string> = {
    primary: 'text-white bg-brand-500 hover:bg-brand-600',
    secondary: 'text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-white/5 hover:bg-gray-200 dark:hover:bg-gray-700',
    ghost: 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white',
    danger: 'text-white bg-red-500 hover:bg-red-600',
  };
  return [...base, sizes[props.size], variants[props.variant]];
});
</script>
