<template>
  <label
    :for="htmlFor"
    class="block text-sm font-medium text-gray-700 dark:text-gray-300"
    :class="[mb]"
  >
    <slot />
    <span v-if="required" class="text-red-500">*</span>
  </label>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    htmlFor?: string;
    required?: boolean;
    mb?: string;
  }>(),
  { mb: 'mb-1' },
);
</script>
