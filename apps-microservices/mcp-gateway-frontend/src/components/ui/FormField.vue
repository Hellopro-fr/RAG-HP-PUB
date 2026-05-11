<template>
  <div :class="wrapperClass">
    <BaseLabel v-if="label" :html-for="inputId" :required="required">{{ label }}</BaseLabel>
    <slot :id="inputId" />
    <p v-if="hint && !error" class="text-xs text-gray-500 dark:text-gray-400 mt-1">{{ hint }}</p>
    <p v-if="error" class="text-xs text-red-500 mt-1">{{ error }}</p>
  </div>
</template>

<script setup lang="ts">
import { computed, useId } from 'vue';
import BaseLabel from './BaseLabel.vue';

const props = defineProps<{
  label?: string;
  required?: boolean;
  hint?: string;
  error?: string;
  inputId?: string;
  wrapperClass?: string;
}>();

const generatedId = useId();
const inputId = computed(() => props.inputId ?? `f-${generatedId}`);
</script>
